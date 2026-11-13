######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for CONTROLLER_STATE (opcode 0x58), which dedicated mesh
controllers, such as routers, use between themselves, and with which one marks
itself as dedicated.

Every frame opens with a 20-byte header: u8 payload version, u8 kind, u8 part,
a reserved byte, then the u32 generation, offset, length and crc32.

  hello    the header, then u8 role, u8 part count, two reserved bytes, the
           primary's uid and 12 bytes per part: u8 part, three reserved bytes,
           u32 length, u32 crc32
  request  the header alone: the part and generation, and the offset and
           length of the window asked for, at most WINDOW_MAX bytes
  data     the header, with this frame's offset and the whole part's length
           and crc32, then at most DATA_MAX bytes of the part

Only dedicated controllers send or take the opcode.'''

from dataclasses import dataclass
from functools import cached_property
import struct
from ..compat import override
from .FrameBase import FrameBase
from .Constants import CONTROLLER_PARTS_MAX, ControllerRole
from ..Interface import ControllerHello, ControllerPart, DeviceRegistry
from ..Uid import MxrDeviceUid


VERSION = 1
'''The payload version every frame opens with; any other is dropped.'''
HEADER_SIZE = 20
HELLO_MIN = 40
'''The shortest hello a unit takes: the header, role, part count, reserved
bytes and primary, without any part.'''
PART_SIZE = 12
'''Width of one part entry of a hello.'''

KIND_HELLO = 0
KIND_REQUEST = 1
KIND_DATA = 2

WINDOW_MAX = 8192
'''The most bytes one request asks for.'''
DATA_MAX = 1024
'''The most part bytes one data frame carries.'''

_NO_PRIMARY = bytes(16)

@dataclass(frozen=True)
class StateHeader:
    '''The header every CONTROLLER_STATE frame opens with.'''
    kind: int
    part: int = 0
    generation: int = 0
    offset: int = 0
    length: int = 0
    crc: int = 0

    def encode(self) -> bytes:
        return struct.pack('<BBBxIIII', VERSION, self.kind, self.part, self.generation, self.offset,
                           self.length, self.crc)

    @staticmethod
    def decode(p:bytes) -> 'StateHeader|None':
        '''A header of payload version 1, None for a shorter payload or
        another version.'''
        if (len(p) < HEADER_SIZE) or (p[0] != VERSION):
            return None
        version, kind, part, generation, offset, length, crc = struct.unpack_from('<BBBxIIII', p)
        return StateHeader(kind=kind, part=part, generation=generation, offset=offset, length=length, crc=crc)

def _role(value:int) -> ControllerRole|int:
    try:
        return ControllerRole(value)
    except ValueError:
        return value

class FrameControllerState(FrameBase):
    '''A dedicated controller's hello.'''

    @staticmethod
    def construct_hello(mxr:DeviceRegistry, hello:ControllerHello) -> FrameBase|None:
        '''A hello to every device. Only the first CONTROLLER_PARTS_MAX parts
        are listed.'''
        parts = hello.parts[:CONTROLLER_PARTS_MAX]
        p = StateHeader(kind=KIND_HELLO, generation=hello.generation).encode()
        p += struct.pack('<BBxx', int(hello.role), len(parts))
        p += hello.primary.byte_value if (hello.primary is not None) else _NO_PRIMARY
        for part in parts:
            p += struct.pack('<BxxxII', part.part, part.length, part.crc)
        return FrameBase.construct_base(mxr=mxr, opcode=0x58, payload=p)

    @staticmethod
    def construct(mxr:DeviceRegistry, header:StateHeader, data:bytes=b'', to:object=None) -> FrameBase|None:
        '''A request, or a data frame carrying data, to one device.'''
        return FrameBase.construct_base(mxr=mxr, opcode=0x58, payload=header.encode() + data, target=to)

    @cached_property
    def state_header(self) -> StateHeader|None:
        return StateHeader.decode(self.payload or b'')

    @cached_property
    def hello(self) -> ControllerHello|None:
        '''A hello: version 1, kind 0, at least HELLO_MIN bytes. Only the part
        entries the payload holds whole are read, up to the count it gives.'''
        header = self.state_header
        p = self.payload or b''
        if (header is None) or (header.kind != KIND_HELLO) or (len(p) < HELLO_MIN):
            return None
        primary = bytes(p[24:40])
        entries = p[HELLO_MIN:]
        count = min(p[21], len(entries) // PART_SIZE)
        parts = tuple(ControllerPart(*struct.unpack_from('<BxxxII', entries, i * PART_SIZE)) for i in range(count))
        return ControllerHello(role=_role(p[20]), generation=header.generation,
                               primary=None if (primary == _NO_PRIMARY) else MxrDeviceUid(primary), parts=parts)

    @property
    def data(self) -> bytes:
        '''A data frame's bytes of the part.'''
        return bytes((self.payload or b'')[HEADER_SIZE:])

    @override
    def process(self) -> None:
        '''Record a hello against its sender, which a unit from protocol 0x34
        on then knows as a dedicated controller, and hand a request or data to
        the registry.'''
        if ((header := self.state_header) is None) or ((dev := self.remote_device) is None):
            return
        if ((hello := self.hello) is not None):
            dev.on_mxr_update(hello)
        elif (header.kind in (KIND_REQUEST, KIND_DATA)):
            self.mxr.on_mxr_update(self)

    def __str__(self) -> str:
        if ((hello := self.hello) is not None):
            role = hello.role.name if isinstance(hello.role, ControllerRole) else hello.role
            return (f"controller hello: {role}, generation {hello.generation}, primary {hello.primary}, "
                    f"{len(hello.parts)} parts")
        header = self.state_header
        if (header is not None) and (header.kind == KIND_REQUEST):
            return (f"controller state request: part {header.part} of generation {header.generation}, "
                    f"{header.length} bytes at {header.offset}")
        if (header is not None) and (header.kind == KIND_DATA):
            return (f"controller state data: part {header.part} of generation {header.generation}, "
                    f"{len(self.data)} bytes at {header.offset} of {header.length}")
        return "controller state <dropped>"
