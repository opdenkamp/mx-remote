######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''What this client keeps of replacing a mesh unit (0x56) and of the settings a
mesh keeps of its units (0x57).

A unit outside any mesh asks which offline units it can replace. Each
controller lists its own, and a member whose controller is offline lists that
controller. The unit then asks the device that listed one to replace it, and
the device answers.

Every unit in a mesh keeps its own settings, and announces their length and
crc32. The controller keeps a copy of every member's, and every member one of
its controller's, so the settings of a unit that fails pass to the unit that
replaces it. Any device may ask for a unit's settings, from the unit itself or
from a device keeping a copy.'''

from dataclasses import dataclass, field
from ..Interface import MeshConfig, MeshReplaceable, MeshReplaceUnit, MeshReplaceUnits, MeshSetting
from ..proto.Constants import MESH_CONFIG_MAX, MESH_REPLACE_UNITS_MAX
from ..proto.FrameMeshConfig import FLAG_COPY, KIND_DUMP, FrameMeshConfig, crc32, decode_settings
from ..proto.FrameMeshReplace import KEPT, FrameMeshReplace
from ..Uid import MxrDeviceUid

QUERY_INTERVAL = 2.0
'''How often a unit asks which units it can replace, at most, in seconds.'''

def _kept(at:float, now:float) -> bool:
    return (now - at) < KEPT

@dataclass
class _Transfer:
    '''The settings of one unit a sender is part way through sending: every
    frame names the same kind, flags, unit, length and crc32, and brings the
    bytes that follow the ones already here.'''
    key: tuple[int, int, MxrDeviceUid|None, int, int]
    data: bytearray = field(default_factory=bytearray)

class MeshKeeper:
    '''The replace lists, kept settings and pending requests this client holds.'''

    def __init__(self) -> None:
        self._lists:dict[MxrDeviceUid, tuple[MeshReplaceUnits, float]] = {}
        self._transfers:dict[MxrDeviceUid, _Transfer] = {}
        self.configs:dict[MxrDeviceUid, MeshConfig] = {}
        '''The kept settings of each unit, by that unit, as a device last sent
        them whole.'''
        self.pending:tuple[MxrDeviceUid, MxrDeviceUid]|None = None
        '''The lister and the unit of this client's last request to replace
        one, until it is answered.'''
        self._queried:float|None = None

    def query_due(self, now:float) -> bool:
        '''Whether a query may go out now, which then counts as sent.'''
        if (self._queried is not None) and ((now - self._queried) < QUERY_INTERVAL):
            return False
        self._queried = now
        return True

    def take_units(self, sender:MxrDeviceUid, frame:FrameMeshReplace, now:float) -> MeshReplaceUnits:
        '''Keep a frame of the sender's list, as a unit outside a mesh keeps it:
        a frame starting at the first record replaces what the sender listed
        before, and a later one adds to it, and no more units are kept of every
        sender together than a controller lists. Returns the sender's whole
        list.'''
        elsewhere = sum(len(units.units) for uid, (units, at) in self._lists.items()
                        if (uid != sender) and _kept(at, now))
        held:tuple[MeshReplaceUnit, ...] = ()
        if (frame.first != 0) and ((earlier := self._lists.get(sender)) is not None) and _kept(earlier[1], now):
            held = earlier[0].units
        room = max(MESH_REPLACE_UNITS_MAX - elsewhere - len(held), 0)
        units = MeshReplaceUnits(offline_controller=frame.offline_controller,
                                 units=held + frame.units[:room], total=frame.total)
        self._lists[sender] = (units, now)
        return units

    def replaceable(self, now:float) -> list[MeshReplaceable]:
        '''The units listed in the last KEPT seconds, each with the device that
        listed it, once each.'''
        found:list[MeshReplaceable] = []
        seen:set[MxrDeviceUid] = set()
        for lister, (units, at) in sorted(self._lists.items(), key=lambda item: item[0].byte_value):
            if not _kept(at, now):
                continue
            for unit in units.units:
                if (unit.uid not in seen):
                    seen.add(unit.uid)
                    found.append(MeshReplaceable(lister=lister, offline_controller=units.offline_controller,
                                                 unit=unit))
        return found

    def listed(self, lister:MxrDeviceUid, unit:MxrDeviceUid, now:float) -> MeshReplaceUnit|None:
        '''The record of unit as lister listed it in the last KEPT seconds.'''
        if ((kept := self._lists.get(lister)) is None) or not _kept(kept[1], now):
            return None
        return next((u for u in kept[0].units if (u.uid == unit)), None)

    def answered(self, unit:MxrDeviceUid|None) -> bool:
        '''Whether a result names the unit of this client's last request, which
        it then answers.'''
        if (self.pending is None) or (self.pending[1] != unit):
            return False
        self.pending = None
        return True

    def take_settings(self, sender:MxrDeviceUid, frame:FrameMeshConfig) -> tuple[MeshSetting, ...]|None:
        '''Add one frame of settings to what its sender has sent, returning the
        settings once they are whole, in order and matching their crc32. A dump
        is then kept as its unit's settings. A frame out of order drops what
        that sender had sent.'''
        key = (frame.kind or 0, frame.flags, frame.subject, frame.total, frame.crc)
        earlier = self._transfers.pop(sender, None)
        if (frame.offset == 0):
            transfer = _Transfer(key)
        elif (earlier is not None) and (earlier.key == key) and (len(earlier.data) == frame.offset):
            transfer = earlier
        else:
            return None
        if (frame.total > MESH_CONFIG_MAX):
            return None
        transfer.data += frame.chunk
        if (len(transfer.data) < frame.total):
            self._transfers[sender] = transfer
            return None
        # Bytes past the length fail the crc32 like any other wrong bytes.
        if (crc32(bytes(transfer.data)) != frame.crc):
            return None
        if ((settings := decode_settings(bytes(transfer.data))) is None):
            return None
        if (frame.kind == KIND_DUMP) and (frame.subject is not None):
            self.configs[frame.subject] = MeshConfig(subject=frame.subject, holder=sender,
                                                     copy=bool(frame.flags & FLAG_COPY), settings=settings)
        return settings
