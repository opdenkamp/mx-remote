######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for MESH_REPLACE (opcode 0x56): a unit outside any mesh
replacing an offline unit of one.

Every frame opens with an 8-byte header: u8 payload version, u8 kind, and for a
list of units the u16 index of its first record, the u16 length of the whole
list and u8 flags, then a reserved byte.

  query    the header alone
  units    the header, then records of 56 bytes: the uid, u32 features, u16
           first input bay, u16 first output bay, and each bay's 16-byte name
  request  the header, the uid of the unit to replace, a zero result and
  result   seven reserved bytes: 32 bytes; a result carries the answer

The opcode is served by the v2ipmesh module, so a unit without it answers
nothing.'''

from functools import cached_property
import struct
from ..compat import override
from .FrameBase import FrameBase
from .Constants import MeshReplaceResult, DeviceFeature
from ..Interface import DeviceRegistry, MeshReplaceUnit
from ..Uid import MxrDeviceUid


VERSION = 1
'''The payload version every frame opens with; a unit drops any other.'''
HEADER_SIZE = 8

KIND_QUERY = 0
KIND_UNITS = 1
KIND_REQUEST = 2
KIND_RESULT = 3

FLAG_CONTROLLER = 1 << 0
'''The list flag: the units listed are the sender's offline controller.'''

UNIT_SIZE = 56
NAME_LEN = 16
TARGET_SIZE = 32
'''Width of a request or result.'''

UNITS_PER_FRAME = 24
'''The most records one frame of a list carries.'''

KEPT = 30.0
'''How long a unit outside a mesh keeps a list after its last frame, and how
recently a unit has to have been listed for a request to replace it, in
seconds.'''

def _header(kind:int, first:int=0, total:int=0, flags:int=0) -> bytes:
    return struct.pack('<BBHHBx', VERSION, kind, first, total, flags)

def _name(text:str) -> bytes:
    return text.encode('utf-8')[:NAME_LEN].ljust(NAME_LEN, b'\0')

def _cstr(data:bytes) -> str:
    return data.split(b'\0', 1)[0].decode('utf-8', errors='replace')

def _record(b:bytes) -> MeshReplaceUnit:
    features, first_in, first_out = struct.unpack_from('<IHH', b, 16)
    return MeshReplaceUnit(uid=MxrDeviceUid(bytes(b[:16])), features=DeviceFeature(features),
                           input=first_in, output=first_out,
                           input_name=_cstr(b[24:24 + NAME_LEN]), output_name=_cstr(b[24 + NAME_LEN:24 + 2 * NAME_LEN]))

class FrameMeshReplace(FrameBase):
    '''A query for replaceable units, a list of them, a request to replace one,
    or the answer to it.'''

    @staticmethod
    def construct_query(mxr:DeviceRegistry) -> FrameBase|None:
        '''A query to every device: the header alone.'''
        return FrameBase.construct_base(mxr=mxr, opcode=0x56, payload=_header(KIND_QUERY))

    @staticmethod
    def construct_units(mxr:DeviceRegistry, units:tuple[MeshReplaceUnit, ...]|list[MeshReplaceUnit],
                        offline_controller:bool, to:object=None) -> list[FrameBase]:
        '''The frames of a list, in order: each the header, with the index of its
        first record and the length of the whole list, then at most
        UNITS_PER_FRAME records. An empty list is one frame of no records. A
        name longer than its field is cut, so the caller keeps names to
        MESH_REPLACE_NAME_MAX bytes.'''
        flags = FLAG_CONTROLLER if offline_controller else 0
        frames:list[FrameBase] = []
        for first in range(0, max(len(units), 1), UNITS_PER_FRAME):
            p = _header(KIND_UNITS, first, len(units), flags)
            for unit in units[first:first + UNITS_PER_FRAME]:
                p += (unit.uid.byte_value + struct.pack('<IHH', int(unit.features), unit.input, unit.output)
                      + _name(unit.input_name) + _name(unit.output_name))
            if ((frame := FrameBase.construct_base(mxr=mxr, opcode=0x56, payload=p, target=to)) is not None):
                frames.append(frame)
        return frames

    @staticmethod
    def construct_target(mxr:DeviceRegistry, kind:int, unit:MxrDeviceUid,
                         result:MeshReplaceResult|int=MeshReplaceResult.REPLACED, to:object=None) -> FrameBase|None:
        '''A request (KIND_REQUEST) or result (KIND_RESULT) naming unit: the
        header, the unit, the result, 0 in a request, and seven reserved
        bytes.'''
        p = _header(kind) + unit.byte_value + bytes([int(result)])
        return FrameBase.construct_base(mxr=mxr, opcode=0x56, payload=p.ljust(TARGET_SIZE, b'\0'), target=to)

    @cached_property
    def kind(self) -> int|None:
        '''The kind, None for a frame a unit drops: shorter than its header or
        its kind, or of a payload version other than VERSION.'''
        p = self.payload or b''
        if (len(p) < HEADER_SIZE) or (p[0] != VERSION):
            return None
        if (p[1] in (KIND_REQUEST, KIND_RESULT)) and (len(p) < TARGET_SIZE):
            return None
        return p[1]

    @cached_property
    def first(self) -> int:
        '''The index of a list frame's first record.'''
        return struct.unpack_from('<H', self.payload or bytes(HEADER_SIZE), 2)[0]

    @cached_property
    def total(self) -> int:
        '''How many units the whole list holds.'''
        return struct.unpack_from('<H', self.payload or bytes(HEADER_SIZE), 4)[0]

    @cached_property
    def offline_controller(self) -> bool:
        '''The units listed are the sender's offline controller.'''
        return bool((self.payload or bytes(HEADER_SIZE))[6] & FLAG_CONTROLLER)

    @cached_property
    def units(self) -> tuple[MeshReplaceUnit, ...]:
        '''The whole records of a list frame; a part record is not read.'''
        if (self.kind != KIND_UNITS):
            return ()
        p = (self.payload or b'')[HEADER_SIZE:]
        return tuple(_record(p[i:i + UNIT_SIZE]) for i in range(0, len(p) - UNIT_SIZE + 1, UNIT_SIZE))

    @cached_property
    def unit(self) -> MxrDeviceUid|None:
        '''The unit a request or result names.'''
        if (self.kind not in (KIND_REQUEST, KIND_RESULT)):
            return None
        return self.payload_uuid(HEADER_SIZE)

    @cached_property
    def result(self) -> MeshReplaceResult|int|None:
        '''A result's answer, a plain int where it has no name.'''
        if (self.kind != KIND_RESULT):
            return None
        value = (self.payload or b'')[HEADER_SIZE + 16]
        try:
            return MeshReplaceResult(value)
        except ValueError:
            return value

    @override
    def process(self) -> None:
        '''Hand the frame to the registry, which keeps lists and answers.'''
        if (self.kind is not None) and (self.remote_device is not None):
            self.mxr.on_mxr_update(self)

    def __str__(self) -> str:
        kind = self.kind
        if (kind == KIND_QUERY):
            return "mesh replace query"
        if (kind == KIND_UNITS):
            what = 'its offline controller' if self.offline_controller else 'offline units'
            return f"mesh replace list of {what}: {len(self.units)} from {self.first} of {self.total}"
        if (kind == KIND_REQUEST):
            return f"mesh replace request for {self.unit}"
        if (kind == KIND_RESULT):
            return f"mesh replace result for {self.unit}: {self.result}"
        return "mesh replace <dropped>"
