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

The opcode is served by the v2ipmesh module, so a unit without it answers
nothing.'''

from functools import cached_property
import struct, zlib
from typing import Iterable
from ..compat import override
from .FrameBase import FrameBase
from .Constants import MESH_CONFIG_MAX
from ..Interface import DeviceRegistry, MeshConfigDigest, MeshSetting
from ..Uid import MxrDeviceUid


VERSION = 1
'''The payload version every frame opens with; a unit drops any other.'''
HEADER_SIZE = 32

KIND_HELLO = 0
KIND_REQUEST = 1
KIND_DUMP = 2
KIND_SET = 3

FLAG_COPY = 1 << 0
'''The dump flag: the settings are a copy the sender keeps of the unit named,
not its own.'''

FRAME_MAX = 1024
'''The most settings bytes one frame carries.'''

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
    def construct_pages(mxr:DeviceRegistry, kind:int, flags:int, subject:MxrDeviceUid, encoded:bytes,
                        to:object=None) -> list[FrameBase]:
        '''The frames of a dump (KIND_DUMP) or set (KIND_SET), in order: each the
        header, with the offset of its bytes, then at most FRAME_MAX bytes of
        encoded, which comes from encode_settings(). Settings of no bytes are
        one frame.'''
        crc = crc32(encoded)
        frames:list[FrameBase] = []
        for offset in range(0, max(len(encoded), 1), FRAME_MAX):
            p = _header(kind, subject, flags, offset, len(encoded), crc) + encoded[offset:offset + FRAME_MAX]
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
        return MeshConfigDigest(length=self.total, crc32=self.crc)

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
        if (kind in (KIND_DUMP, KIND_SET)):
            what = 'dump' if (kind == KIND_DUMP) else 'set'
            return (f"mesh config {what} of {self.subject}: {len(self.chunk)} bytes at {self.offset} "
                    f"of {self.total}{' (copy)' if (self.flags & FLAG_COPY) else ''}")
        return "mesh config <dropped>"
