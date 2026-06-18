######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################

'''MX Remote frame header parsing and construction.'''

from functools import cached_property
from ..Uid import MxrDeviceUid
from ..Interface import DeviceRegistry

class FrameHeader:
    ''' Header of an mx_remote frame '''
    def __init__(self, mxr:DeviceRegistry, data: bytes, addr: tuple[str, int]):
        self._mxr = mxr
        self.data = data
        self.addr = addr
        if len(data) < 24:
            raise Exception(f'invalid mx_remote frame (length = {len(data)})')
        if (data[0] != 80) or (data[1] != 56):
            raise Exception(f'invalid mx_remote frame (header = {int(data[0])}:{int(data[1])})')

    @staticmethod
    def construct(mxr:DeviceRegistry, opcode:int, protocol:int=1) -> 'FrameHeader|None':
        '''Create a new MX Remote frame header for transmission.'''
        if (mxr.uid_raw is None):
            return None
        pkt = [80, 56, protocol, 0 ]
        pkt.extend(mxr.uid_raw)
        pkt.extend([(opcode & 0xFF), ((opcode >> 8) & 0xFF)])
        pkt.extend([0, 0])
        return FrameHeader(mxr, bytes(pkt), ("", 0))

    @property
    def mxr(self) -> DeviceRegistry:
        return self._mxr

    def data_u8(self, idx:int) -> int|None:
        if (self.data is None):
            return None
        if (idx >= len(self.data)):
            return None
        return self.data[idx]

    def data_bool(self, idx:int) -> bool|None:
        pl = self.data_u8(idx)
        return (pl is not None) and (pl == 1)

    def data_u16(self, idx:int=0) -> int|None:
        if (self.data is None):
            return None
        if (idx + 1 >= len(self.data)):
            return None
        return int.from_bytes(self.data[idx:idx+2], "little")

    def data_u32(self, idx:int=0) -> int|None:
        if (self.data is None):
            return None
        if (idx + 3 >= len(self.data)):
            return None
        return int.from_bytes(self.data[idx:idx+4], "little")

    def data_str(self, idx:int, length:int=-1) -> str|None:
        if (self.data is None):
            return None
        if (idx > len(self.data)):
            return None
        if (length > 0) and ((idx + length) > len(self.data)):
            return None
        pl = self.data[idx:idx+length] if (length > 0) else self.data[idx:]
        return pl.split(b'\0',1)[0].decode('ascii')

    def data_uuid(self, idx:int=0) -> MxrDeviceUid|None:
        if (self.data is None) or ((idx + 16) > len(self.data)):
            return None
        return MxrDeviceUid(self.data[idx:idx+16])

    def data_bytes(self, idx:int=0) -> bytes|None:
        if (self.data is None):
            return None
        if (idx >= len(self.data)):
            return None
        return self.data[idx:]

    def payload_u8(self, idx:int) -> int|None:
        return self.data_u8(idx=(idx + 24))

    def payload_bool(self, idx:int) -> bool|None:
        return self.data_bool(idx=(idx + 24))

    def payload_u16(self, idx:int) -> int|None:
        return self.data_u16(idx=(idx + 24))

    def payload_u32(self, idx:int) -> int|None:
        return self.data_u32(idx=(idx + 24))

    def payload_str(self, idx:int, length:int=-1) -> str|None:
        return self.data_str(idx=(idx + 24), length=length)

    def payload_uuid(self, idx:int) -> MxrDeviceUid|None:
        return self.data_uuid(idx=(idx + 24))

    def payload_bytes(self, idx:int) -> bytes|None:
        return self.data_bytes(idx=(idx + 24))

    @cached_property
    def protocol(self) -> int:
        '''Frame protocol version.'''
        protocol = self.data_u16(2)
        return protocol if (protocol is not None) else 255

    @cached_property
    def remote_id(self) -> MxrDeviceUid:
        '''Unique id of the device that sent this frame.'''
        uid = self.data_uuid(4)
        if (uid is None):
            raise Exception("invalid frame size")
        return uid

    @cached_property
    def remote_id_raw(self) -> bytes:
        '''Unique id of the device that sent this frame as raw bytes.'''
        return self.remote_id.byte_value

    @cached_property
    def opcode(self) -> int:
        '''Command opcode.'''
        opcode = self.data_u16(20)
        return opcode if (opcode is not None) else 0

    @cached_property
    def payload_len(self) -> int:
        '''Number of payload bytes.'''
        length = self.data_u16(22)
        return length if (length is not None) else 0

    @property
    def payload(self) -> bytes|None:
        '''Frame payload bytes.'''
        if len(self) < 25:
            return None
        return self.data[24:]

    @payload.setter
    def payload(self, val:bytes) -> None:
        data = list(self.data[0:24])
        if (val is None) or (len(val) == 0):
            data[22] = 0
            data[23] = 0
        else:
            l = len(val)
            data[22] = (l & 0xFF)
            data[23] = ((l >> 8) & 0xFF)
            data += val
        self.data = bytes(data)

    def __len__(self) -> int:
        '''Number of bytes in this frame.'''
        return len(self.data)

    def __str__(self) -> str:
        return f"proto: {self.protocol} op: {self.opcode} len: {self.payload_len}"
