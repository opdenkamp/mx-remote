######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for MESH_CONFIG (opcode 0x57): the settings each unit keeps
for its mesh.

Every frame opens with a 32-byte header: u8 payload version, u8 kind, u8 flags,
a reserved byte, u16 offset of this frame's bytes in the settings, u16 length
of the settings, u32 crc32 of them, four reserved bytes, and at 16 the unit the
settings belong to. A hello and a request are the header alone; a dump or a set
carries at most FRAME_MAX bytes of the settings behind it.

The settings are carried as pairs: a u8 name length, the name, a u8 value
length and the value, none terminated.

A controller's numbering travels the same way: a bays request is the header
alone, and a bays answer carries at most BAYS_PER_FRAME entries of 24 bytes,
each u8 mode (1 an input, 0 an output), a reserved byte, the u16 bay number,
the owning unit's u32 features and its uid.

A setup frame marks one member's setup completed, or not: the header alone,
naming the member, the mark in the length field.

Port metadata names its port by the subject and FLAG_INPUT. A metadata frame
carries one port's fields as "key NUL value NUL" pairs, the length and crc32 of
them in the header, both 0 for none, which removes the port's. An index carries
a u32 generation, then at most INDEX_PER_FRAME entries of 24 bytes, each the
port's unit, u8 mode (1 an input, 0 an output), three reserved bytes and the
u32 crc32 of its metadata; its offset and length count entries, and its crc32
is over every entry. A metadata request is the header alone.

The opcode is served by the v2ipmesh module, so a unit without it answers
nothing.'''

from functools import cached_property
import struct, zlib
from typing import Iterable
from ..compat import override
from .FrameBase import FrameBase
from .Constants import MESH_CONFIG_MAX, DeviceFeature
from .Constants import PORT_METADATA_FIELDS_MAX, PORT_METADATA_KEY_MAX, PORT_METADATA_MAX, PORT_METADATA_VALUE_MAX
from ..Interface import DeviceRegistry, MeshBay, MeshConfigDigest, MeshPort, MeshSetting, PortMetadataField
from ..Uid import MxrDeviceUid


VERSION = 1
'''The payload version every frame opens with; a unit drops any other.'''
HEADER_SIZE = 32

KIND_HELLO = 0
KIND_REQUEST = 1
KIND_DUMP = 2
KIND_SET = 3
KIND_BAYS_REQUEST = 4
KIND_BAYS = 5
KIND_METADATA = 6
KIND_METADATA_INDEX = 7
KIND_METADATA_REQUEST = 8
KIND_SETUP = 9

FLAG_COPY = 1 << 0
'''The dump flag: the settings are a copy the sender keeps of the unit named,
not its own.'''
FLAG_LOST = 1 << 1
'''The flag of a hello, or of a dump of the sender's own settings: the sender
lost its settings and holds defaults. A controller that keeps a record of it
sends that record back as a set.'''
FLAG_INPUT = 1 << 2
'''The flag of a port's metadata or a request for it: the port is the unit's
input, and without it its output.'''

FRAME_MAX = 1024
'''The most settings bytes one frame carries.'''

BAYS_ENTRY_SIZE = 24
'''Width of one entry of a controller's numbering.'''
BAYS_PER_FRAME = 42
'''The most numbering entries one frame carries.'''
_BAYS_INPUT = 1

INDEX_ENTRY_SIZE = 24
'''Width of one metadata index entry.'''
INDEX_PER_FRAME = 48
'''The most entries one metadata index frame carries.'''
INDEX_GENERATION_SIZE = 4
'''The width of the generation every metadata index frame's body opens with.'''
_INDEX_INPUT = 1

def crc32(data:bytes) -> int:
    '''The crc32 a unit checks its kept settings against: the zlib one.'''
    return zlib.crc32(data) & 0xFFFFFFFF

def encode_settings(settings:Iterable[MeshSetting]) -> bytes|None:
    '''Settings as a unit carries them, None for a name or value over 255 bytes
    or holding a NUL, which a unit cannot store, and for settings over
    MESH_CONFIG_MAX bytes, which no unit takes.'''
    p = bytearray()
    for setting in settings:
        for text in (setting.name, setting.value):
            b = text.encode('utf-8')
            if (len(b) > 0xFF) or (b'\0' in b):
                return None
            p += bytes([len(b)]) + b
    return bytes(p) if (len(p) <= MESH_CONFIG_MAX) else None

def decode_settings(p:bytes) -> tuple[MeshSetting, ...]|None:
    '''Settings as a unit carries them, None for bytes that end inside a pair. A
    name or value is read as UTF-8, a sequence that is not replaced.'''
    settings:list[MeshSetting] = []
    texts:list[str] = []
    i = 0
    while (i < len(p)):
        n = p[i]
        if (i + 1 + n > len(p)):
            return None
        texts.append(p[i + 1:i + 1 + n].decode('utf-8', errors='replace'))
        i += 1 + n
        if (len(texts) == 2):
            settings.append(MeshSetting(name=texts[0], value=texts[1]))
            texts = []
    return None if texts else tuple(settings)

def encode_bays(bays:Iterable[MeshBay]) -> bytes:
    '''A numbering's entries as a unit carries them.'''
    return b''.join(struct.pack('<BxHI', _BAYS_INPUT if bay.input else 0, bay.bay, int(bay.features))
                    + bay.unit.byte_value for bay in bays)

def decode_bays(p:bytes) -> tuple[MeshBay, ...]|None:
    '''A numbering's entries, None for bytes that end inside one.'''
    if (len(p) % BAYS_ENTRY_SIZE):
        return None
    bays:list[MeshBay] = []
    for i in range(0, len(p), BAYS_ENTRY_SIZE):
        mode, bay, features = struct.unpack_from('<BxHI', p, i)
        bays.append(MeshBay(input=(mode == _BAYS_INPUT), bay=bay, features=DeviceFeature(features),
                            unit=MxrDeviceUid(bytes(p[i + 8:i + BAYS_ENTRY_SIZE]))))
    return tuple(bays)

_KEY_BYTES = frozenset(b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-')

def valid_metadata_key(key:str) -> bool:
    '''Whether key is one a unit takes for port metadata: 1 to
    PORT_METADATA_KEY_MAX characters of A-Z, a-z, 0-9, _ and -.'''
    b = key.encode('utf-8')
    return (1 <= len(b) <= PORT_METADATA_KEY_MAX) and all(c in _KEY_BYTES for c in b)

def valid_metadata_value(value:str) -> bool:
    '''Whether value is one a unit takes for port metadata: 1 to
    PORT_METADATA_VALUE_MAX bytes of UTF-8, with no control character, " or \\.'''
    b = value.encode('utf-8')
    return (1 <= len(b) <= PORT_METADATA_VALUE_MAX) \
        and all((c >= 0x20) and (c not in (0x7F, 0x22, 0x5C)) for c in b)

def encode_port_metadata(fields:Iterable[PortMetadataField]) -> bytes|None:
    '''A port's metadata as a unit carries it: each field its key, a NUL, its
    value and a NUL, in the order given. Order counts, as the crc32 is taken
    over these bytes; a repeated key is carried as it is.

    None for an invalid key or value, more than PORT_METADATA_FIELDS_MAX
    fields, or more than PORT_METADATA_MAX bytes, none of which a unit takes.'''
    fields = tuple(fields)
    if (len(fields) > PORT_METADATA_FIELDS_MAX):
        return None
    p = bytearray()
    for f in fields:
        if not valid_metadata_key(f.key) or not valid_metadata_value(f.value):
            return None
        p += f.key.encode('utf-8') + b'\0' + f.value.encode('utf-8') + b'\0'
    return bytes(p) if (len(p) <= PORT_METADATA_MAX) else None

def decode_port_metadata(p:bytes) -> tuple[PortMetadataField, ...]|None:
    '''A port's metadata as a unit carries it, None for anything a unit would
    refuse: bytes not ending in a field's NUL, a key without a value, text that
    is not UTF-8, an invalid key or value, or more fields or bytes than a unit
    takes.'''
    if (len(p) > PORT_METADATA_MAX):
        return None
    if not p:
        return ()
    if (p[-1] != 0):
        return None
    parts = bytes(p[:-1]).split(b'\0')
    if (len(parts) % 2):
        return None
    fields:list[PortMetadataField] = []
    for i in range(0, len(parts), 2):
        try:
            key, value = parts[i].decode('utf-8'), parts[i + 1].decode('utf-8')
        except UnicodeDecodeError:
            return None
        if not valid_metadata_key(key) or not valid_metadata_value(value):
            return None
        fields.append(PortMetadataField(key=key, value=value))
    return tuple(fields) if (len(fields) <= PORT_METADATA_FIELDS_MAX) else None

def encode_metadata_index(entries:Iterable[tuple[MeshPort, int]]) -> bytes:
    '''A metadata index's entries, each a port and the crc32 of its metadata,
    as a unit carries them.'''
    return b''.join(port.unit.byte_value + struct.pack('<B3xI', _INDEX_INPUT if port.input else 0, crc)
                    for port, crc in entries)

def decode_metadata_index(p:bytes) -> tuple[int, tuple[tuple[MeshPort, int], ...]]|None:
    '''The body of a metadata index frame: its generation, then its entries,
    each a port and the crc32 of its metadata. None for a body that is not the
    generation and whole entries.'''
    if (len(p) < INDEX_GENERATION_SIZE) or ((len(p) - INDEX_GENERATION_SIZE) % INDEX_ENTRY_SIZE):
        return None
    generation = struct.unpack_from('<I', p, 0)[0]
    entries:list[tuple[MeshPort, int]] = []
    for i in range(INDEX_GENERATION_SIZE, len(p), INDEX_ENTRY_SIZE):
        mode, crc = struct.unpack_from('<B3xI', p, i + 16)
        entries.append((MeshPort(MxrDeviceUid(bytes(p[i:i + 16])), mode == _INDEX_INPUT), crc))
    return generation, tuple(entries)

def _port_flags(port:MeshPort) -> int:
    return FLAG_INPUT if port.input else 0

def port_metadata_payload(port:MeshPort, encoded:bytes) -> bytes:
    '''A metadata frame's payload: the header naming the port, with the length
    and crc32 of encoded, from encode_port_metadata(), then encoded itself.
    Metadata of no fields, which removes the port's, has length and crc 0.'''
    return _header(KIND_METADATA, port.unit, _port_flags(port), total=len(encoded), crc=crc32(encoded)) + encoded

def port_metadata_request_payload(port:MeshPort) -> bytes:
    '''A metadata request's payload: the header alone, naming the port.'''
    return _header(KIND_METADATA_REQUEST, port.unit, _port_flags(port))

def metadata_index_payloads(sender:MxrDeviceUid, generation:int,
                            entries:Iterable[tuple[MeshPort, int]]) -> list[bytes]:
    '''The payloads of a metadata index from sender, in order: each the header,
    with the index of its first entry, the number of entries and the crc32 of
    them all, then the generation and at most INDEX_PER_FRAME entries. An index
    of no ports is one frame of no entries, with crc 0.'''
    encoded = encode_metadata_index(entries)
    total = len(encoded) // INDEX_ENTRY_SIZE
    crc = crc32(encoded)
    page = INDEX_PER_FRAME * INDEX_ENTRY_SIZE
    return [_header(KIND_METADATA_INDEX, sender, 0, offset // INDEX_ENTRY_SIZE, total, crc)
            + struct.pack('<I', generation) + encoded[offset:offset + page]
            for offset in range(0, max(len(encoded), 1), page)]

def _header(kind:int, subject:MxrDeviceUid, flags:int=0, offset:int=0, total:int=0, crc:int=0) -> bytes:
    return struct.pack('<BBBxHHI4x', VERSION, kind, flags, offset, total, crc) + subject.byte_value

class FrameMeshConfig(FrameBase):
    '''A unit's announcement of its kept settings, a request for a unit's, or
    one frame of them, sent as an answer or to be taken.'''

    @staticmethod
    def construct_hello(mxr:DeviceRegistry, own:MxrDeviceUid, encoded:bytes) -> FrameBase|None:
        '''A hello to every device: the length and crc32 of the sender's own
        settings, encoded, which name the sender as their unit.'''
        return FrameBase.construct_base(mxr=mxr, opcode=0x57,
                                        payload=_header(KIND_HELLO, own, total=len(encoded), crc=crc32(encoded)))

    @staticmethod
    def construct_request(mxr:DeviceRegistry, subject:MxrDeviceUid, to:object=None) -> FrameBase|None:
        '''A request for the settings of subject: the header alone, with no
        offset, length or crc.'''
        return FrameBase.construct_base(mxr=mxr, opcode=0x57, payload=_header(KIND_REQUEST, subject), target=to)

    @staticmethod
    def construct_bays_request(mxr:DeviceRegistry, subject:MxrDeviceUid, to:object=None) -> FrameBase|None:
        '''A request for the numbering of controller subject: the header
        alone.'''
        return FrameBase.construct_base(mxr=mxr, opcode=0x57, payload=_header(KIND_BAYS_REQUEST, subject),
                                        target=to)

    @staticmethod
    def construct_setup(mxr:DeviceRegistry, member:MxrDeviceUid, completed:bool, to:object=None) -> FrameBase|None:
        '''A setup frame marking member's setup completed, or not.'''
        return FrameBase.construct_base(mxr=mxr, opcode=0x57, payload=_header(KIND_SETUP, member, total=int(completed)),
                                        target=to)

    @staticmethod
    def construct_payload(mxr:DeviceRegistry, payload:bytes, to:object=None) -> FrameBase|None:
        '''A frame of a payload built here, such as port_metadata_payload().'''
        return FrameBase.construct_base(mxr=mxr, opcode=0x57, payload=payload, target=to)

    @staticmethod
    def construct_pages(mxr:DeviceRegistry, kind:int, flags:int, subject:MxrDeviceUid, encoded:bytes,
                        to:object=None) -> list[FrameBase]:
        '''The frames of a dump (KIND_DUMP), set (KIND_SET) or numbering
        (KIND_BAYS), in order: each the header, with the offset of its bytes,
        then at most FRAME_MAX bytes of encoded, from encode_settings(), or
        BAYS_PER_FRAME entries, from encode_bays(). No bytes are one frame.'''
        crc = crc32(encoded)
        page = (BAYS_PER_FRAME * BAYS_ENTRY_SIZE) if (kind == KIND_BAYS) else FRAME_MAX
        frames:list[FrameBase] = []
        for offset in range(0, max(len(encoded), 1), page):
            p = _header(kind, subject, flags, offset, len(encoded), crc) + encoded[offset:offset + page]
            if ((frame := FrameBase.construct_base(mxr=mxr, opcode=0x57, payload=p, target=to)) is not None):
                frames.append(frame)
        return frames

    @cached_property
    def kind(self) -> int|None:
        '''The kind, None for a frame a unit drops: shorter than the header, or
        of a payload version other than VERSION.'''
        p = self.payload or b''
        if (len(p) < HEADER_SIZE) or (p[0] != VERSION):
            return None
        return p[1]

    @cached_property
    def flags(self) -> int:
        return (self.payload or bytes(HEADER_SIZE))[2]

    @cached_property
    def offset(self) -> int:
        '''Where this frame's bytes start in the settings.'''
        return struct.unpack_from('<H', self.payload or bytes(HEADER_SIZE), 4)[0]

    @cached_property
    def total(self) -> int:
        '''The settings' length in bytes.'''
        return struct.unpack_from('<H', self.payload or bytes(HEADER_SIZE), 6)[0]

    @cached_property
    def crc(self) -> int:
        '''The crc32 of the whole settings.'''
        return struct.unpack_from('<I', self.payload or bytes(HEADER_SIZE), 8)[0]

    @cached_property
    def subject(self) -> MxrDeviceUid|None:
        '''The unit the settings belong to.'''
        return self.payload_uuid(16) if (self.kind is not None) else None

    @cached_property
    def port(self) -> MeshPort|None:
        '''The port a metadata frame or request names.'''
        subject = self.subject
        return None if (subject is None) else MeshPort(subject, bool(self.flags & FLAG_INPUT))

    @property
    def chunk(self) -> bytes:
        '''This frame's bytes of the settings.'''
        return bytes((self.payload or b'')[HEADER_SIZE:])

    @cached_property
    def digest(self) -> MeshConfigDigest|None:
        '''What a hello announces, None for any other kind and for a hello that
        does not name its sender, which a unit ignores.'''
        if (self.kind != KIND_HELLO) or (self.subject != self.remote_id):
            return None
        return MeshConfigDigest(length=self.total, crc32=self.crc, lost=bool(self.flags & FLAG_LOST))

    @override
    def process(self) -> None:
        '''Record a hello against its sender, and hand every other kind to the
        registry, which puts settings together and answers.'''
        if (self.kind is None) or ((dev := self.remote_device) is None):
            return
        if ((digest := self.digest) is not None):
            dev.on_mxr_update(digest)
        elif (self.kind != KIND_HELLO):
            self.mxr.on_mxr_update(self)

    def __str__(self) -> str:
        kind = self.kind
        if (kind == KIND_HELLO):
            return f"mesh config hello: {self.total} bytes, crc32 {self.crc:08x}"
        if (kind == KIND_REQUEST):
            return f"mesh config request for {self.subject}"
        if (kind == KIND_BAYS_REQUEST):
            return f"mesh config bays request for {self.subject}"
        if (kind == KIND_SETUP):
            return f"mesh config setup of {self.subject}: {'completed' if self.total else 'not completed'}"
        if (kind == KIND_METADATA):
            return f"mesh config metadata of {self.port}: {len(self.chunk)} bytes, crc32 {self.crc:08x}"
        if (kind == KIND_METADATA_INDEX):
            return (f"mesh config metadata index: {len(self.chunk) // INDEX_ENTRY_SIZE} entries at {self.offset} "
                    f"of {self.total}")
        if (kind == KIND_METADATA_REQUEST):
            return f"mesh config metadata request for {self.port}"
        if (kind in (KIND_DUMP, KIND_SET, KIND_BAYS)):
            what = {KIND_DUMP: 'dump', KIND_SET: 'set', KIND_BAYS: 'bays'}[kind]
            return (f"mesh config {what} of {self.subject}: {len(self.chunk)} bytes at {self.offset} "
                    f"of {self.total}{' (copy)' if (self.flags & FLAG_COPY) else ''}")
        return "mesh config <dropped>"
