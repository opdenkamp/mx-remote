######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''The port metadata a mesh keeps, over MESH_CONFIG (0x57) kinds 6 to 8: fields
an installer recorded about the device on each port.

Every unit holds the metadata of every port of its mesh, and a generation. The
controller sends a port's metadata to every unit when it changes, and an index
of every port's crc32 under its generation periodically and 1 s after a change.
A unit taking an index asks its sender for each port it lacks or holds
differently, and once the whole index has arrived drops every port it does not
name and takes its generation.

A member takes its controller's index when it names the member's own
generation or a newer one, and answers an older one with its own index, sent to
the controller; the controller takes a member's index only when it names a
newer generation, which is how a new controller learns the mesh's metadata.
Metadata is taken from the unit's own controller at any time, from the sender
of the index it last took for 30 s after the index started, and from a holder
asked for a port for 30 s after asking. Every unit answers a request for a
port's metadata.'''

from dataclasses import dataclass, field
import random
from typing import Callable
from ..Interface import MeshPort, PortMetadata, PortMetadataField, PortMetadataStore
from ..proto.Constants import PORT_METADATA_MAX
from ..proto.FrameMeshConfig import (crc32, decode_metadata_index, decode_port_metadata, encode_port_metadata,
                                     metadata_index_payloads, port_metadata_payload, port_metadata_request_payload)
from ..Uid import MxrDeviceUid

PULL_WINDOW = 30.0
'''How long metadata is taken from the sender of an index, from when its first
frame was taken, and from a holder asked for a port, in seconds.'''
OFFER_EVERY = 60.0
'''How often a member answers an older index of its controller's with its own,
at most, in seconds.'''
INDEX_AFTER_CHANGE = 1.0
'''How long after a change of its metadata the controller sends its index.'''
INDEX_EVERY_MIN = 45.0
INDEX_EVERY_SPREAD = 15.0

def next_index_interval() -> float:
    '''The interval to the controller's next periodic index, 45 to 60 s, drawn
    so the controllers of several meshes do not fall into step.'''
    return INDEX_EVERY_MIN + random.random() * INDEX_EVERY_SPREAD

def _sort_key(port:MeshPort) -> tuple[bytes, bool]:
    return (port.unit.byte_value, port.input)

class MetadataRefused(ValueError):
    '''Metadata no unit takes: an invalid field, too many or too long, a key
    set twice, or a port listed twice in a store.'''

INVALID = ('port metadata is at most 16 fields of at most 1024 bytes together, each key 1-31 characters of A-Z, '
           'a-z, 0-9, _ and -, each value 1-255 bytes of UTF-8 without control characters, " or \\')

@dataclass
class _IndexPull:
    '''The index this client is taking, from its first frame on.'''
    sender: MxrDeviceUid
    generation: int
    total: int
    crc: int
    started: float
    '''When its first frame was taken: metadata is taken from its sender for
    PULL_WINDOW after.'''
    taken: int = 0
    '''Entries taken so far, which the next frame has to start at.'''
    named: set[MeshPort] = field(default_factory=set)
    complete: bool = False

Changed = tuple[MxrDeviceUid, PortMetadata]
'''A change to report: the device it came from, and the port's metadata.'''

class MetadataKeeper:
    '''The port metadata this client holds, where it stands in taking more,
    and the frames it has to send.

    Changes and generation changes queue in changes and generations, frames in
    outbox, each to one device or, with None, to every unit, for the caller to
    report and send.'''

    def __init__(self) -> None:
        self.generation = 0
        self._ports:dict[MeshPort, tuple[tuple[PortMetadataField, ...], int]] = {}
        self._pull:_IndexPull|None = None
        self._asked:tuple[MxrDeviceUid, float]|None = None
        self._offered:float|None = None
        self.index_due:float|None = None
        '''When the controller's index is next due, None until this client
        first runs as controller.'''
        self.outbox:list[tuple[MxrDeviceUid|None, bytes]] = []
        self.changes:list[Changed] = []
        self.generations:list[tuple[MxrDeviceUid, int]] = []

    def get(self, port:MeshPort) -> tuple[PortMetadataField, ...]|None:
        '''The fields of port, None when it holds none.'''
        held = self._ports.get(port)
        return None if (held is None) else held[0]

    def store(self) -> PortMetadataStore:
        '''All the metadata held, with the generation.'''
        return PortMetadataStore(generation=self.generation,
                                 ports=tuple(PortMetadata(port=port, fields=self._ports[port][0])
                                             for port in sorted(self._ports, key=_sort_key)))

    def restore(self, store:PortMetadataStore) -> None:
        '''Replace everything held with store, as a unit loads what it
        persisted. A port of no fields is left out. Raises MetadataRefused,
        holding what it held, for a port listed twice or a field no unit
        takes.'''
        ports:dict[MeshPort, tuple[tuple[PortMetadataField, ...], int]] = {}
        for p in store.ports:
            if ((encoded := encode_port_metadata(p.fields)) is None):
                raise MetadataRefused(INVALID)
            if not p.fields:
                continue
            if (p.port in ports):
                raise MetadataRefused('a port listed twice')
            ports[p.port] = (tuple(p.fields), crc32(encoded))
        self._ports = ports
        self.generation = store.generation
        self._pull = None

    def asked_now(self, holder:MxrDeviceUid, now:float) -> None:
        '''Record that holder was just asked for a port's metadata, whose answer
        is then taken from it for PULL_WINDOW.'''
        self._asked = (holder, now)

    def _entries(self) -> list[tuple[MeshPort, int]]:
        return [(port, self._ports[port][1]) for port in sorted(self._ports, key=_sort_key)]

    def _index(self, own:MxrDeviceUid) -> list[bytes]:
        return metadata_index_payloads(own, self.generation, self._entries())

    def _put(self, source:MxrDeviceUid, port:MeshPort, fields:tuple[PortMetadataField, ...], crc:int) -> bool:
        '''Set port to fields, none removing its metadata, reporting a change as
        from source. Whether anything changed.'''
        if not fields:
            changed = self._ports.pop(port, None) is not None
        else:
            old = self._ports.get(port)
            self._ports[port] = (fields, crc)
            changed = (old is None) or (old[0] != fields)
        if changed:
            self.changes.append((source, PortMetadata(port=port, fields=fields)))
        return changed

    def _set_generation(self, source:MxrDeviceUid, generation:int) -> None:
        if (self.generation != generation):
            self.generation = generation
            self.generations.append((source, generation))

    def set(self, own:MxrDeviceUid, controls:bool, port:MeshPort, fields:tuple[PortMetadataField, ...],
            now:float) -> None:
        '''Set port's metadata through this client's own API, as a controller
        or a unit in no mesh does: raise the generation when it changed, and as
        controller (controls) send the port's metadata to every unit at once
        and the index INDEX_AFTER_CHANGE later. No fields removes the port's
        metadata. Raises MetadataRefused for a field no unit takes, and for a
        key set twice, which a unit's API refuses though it takes one on the
        wire.'''
        if ((encoded := encode_port_metadata(fields)) is None):
            raise MetadataRefused(INVALID)
        keys = [f.key for f in fields]
        if (len(set(keys)) != len(keys)):
            raise MetadataRefused('a port metadata key set twice')
        if not self._put(own, port, fields, crc32(encoded)):
            return
        self._set_generation(own, (self.generation + 1) & 0xFFFFFFFF)
        if controls:
            self.outbox.append((None, port_metadata_payload(port, encoded)))
            self.index_due = now + INDEX_AFTER_CHANGE

    def check_index(self, own:MxrDeviceUid, controls:bool, now:float, period:Callable[[], float]) -> None:
        '''Queue the controller's index when it is due, and schedule the next
        one period() later. Nothing while this client controls no mesh.'''
        if not controls or ((self.index_due is not None) and (now < self.index_due)):
            return
        self.outbox.extend((None, p) for p in self._index(own))
        self.index_due = now + period()

    def on_request(self, sender:MxrDeviceUid, port:MeshPort) -> None:
        '''Take a request for port's metadata: every unit answers the requester
        with what it holds, no fields when it holds none.'''
        held = self._ports.get(port)
        encoded = (encode_port_metadata(held[0]) or b'') if (held is not None) else b''
        self.outbox.append((sender, port_metadata_payload(port, encoded)))

    def _takes_from(self, sender:MxrDeviceUid, own:MxrDeviceUid, controller:MxrDeviceUid|None, now:float) -> bool:
        '''Whether metadata from sender is taken as of now: from this client's
        controller, other than itself, at any time; from the sender of the
        index it last took, and the holder it last asked, for PULL_WINDOW.'''
        def within(at:float) -> bool:
            return (now - at) < PULL_WINDOW
        return ((controller is not None) and (sender == controller) and (sender != own)) \
            or ((self._pull is not None) and (self._pull.sender == sender) and within(self._pull.started)) \
            or ((self._asked is not None) and (self._asked[0] == sender) and within(self._asked[1]))

    def on_metadata(self, sender:MxrDeviceUid, own:MxrDeviceUid, controller:MxrDeviceUid|None, port:MeshPort,
                    total:int, crc:int, body:bytes, now:float) -> None:
        '''Take a port's metadata, body its fields as carried, total and crc as
        its header gives them. Dropped from a sender it is not taken from, and
        when the body is not total bytes, fails the crc32, or holds a field a
        unit would refuse.'''
        if not self._takes_from(sender, own, controller, now):
            return
        if (len(body) != total) or (len(body) > PORT_METADATA_MAX) or (crc32(body) != crc):
            return
        if ((fields := decode_port_metadata(body)) is None):
            return
        self._put(sender, port, fields, crc)

    def on_index(self, sender:MxrDeviceUid, own:MxrDeviceUid, controller:MxrDeviceUid|None,
                 is_member:Callable[[MxrDeviceUid], bool], first:int, total:int, crc:int, body:bytes,
                 now:float) -> None:
        '''Take a frame of an index from sender: first the index of its first
        entry, total the entries of the whole index and crc their crc32, body
        the generation and this frame's entries. is_member says whether a
        device has reported this client as its controller.

        A first frame starts a new index, in place of one under way, when it
        is taken at all: a member takes its controller's when it names the
        member's generation or a newer one, and answers an older one with its
        own index, at most every OFFER_EVERY; the controller takes a member's
        when it names a newer generation. A later frame is taken only from the
        same sender, with the same crc32, starting at the first entry not yet
        taken.'''
        if ((decoded := decode_metadata_index(body)) is None):
            return
        generation, entries = decoded
        if (first == 0):
            if not self._starts_pull(sender, own, controller, is_member, generation, now):
                return
            self._pull = _IndexPull(sender=sender, generation=generation, total=total, crc=crc, started=now)
        pull = self._pull
        if (pull is None) or pull.complete or (pull.sender != sender) or (pull.crc != crc) or (pull.taken != first):
            return
        pull.taken += len(entries)
        for port, entry_crc in entries:
            pull.named.add(port)
            held = self._ports.get(port)
            if (held is None) or (held[1] != entry_crc):
                self.outbox.append((sender, port_metadata_request_payload(port)))
        if (pull.taken < pull.total):
            return
        pull.complete = True
        named, pull.named = pull.named, set()
        for port in sorted((p for p in self._ports if (p not in named)), key=_sort_key):
            self._put(sender, port, (), 0)
        self._set_generation(sender, pull.generation)

    def _starts_pull(self, sender:MxrDeviceUid, own:MxrDeviceUid, controller:MxrDeviceUid|None,
                     is_member:Callable[[MxrDeviceUid], bool], generation:int, now:float) -> bool:
        '''Whether a first index frame from sender naming generation starts an
        index this client takes, queuing its own index for its controller when
        the controller's names an older generation.'''
        if (controller is None) or (sender == own):
            return False
        if (controller == own):
            return is_member(sender) and (generation > self.generation)
        if (sender != controller):
            return False
        if (generation >= self.generation):
            return True
        if (self._offered is None) or ((now - self._offered) >= OFFER_EVERY):
            self._offered = now
            self.outbox.extend((controller, p) for p in self._index(own))
        return False
