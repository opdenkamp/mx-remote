##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
from .Constants import MXR_PROTOCOL_VERSION
from .FrameHeader import FrameHeader
from ..Interface import DeviceBase, DeviceRegistry, BayBase
from ..Uid import MxrDeviceUid

def append_payload_str(payload:list[int], value:str, sz:int) -> list[int]:
    value = value[0:16]
    return payload + list(value.encode('ascii')) + [ 0 for _ in range(sz - len(value))]

class FrameBase:
    ''' Base class for decoded mx_remote frames '''
    def __init__(self, header:FrameHeader):
        assert(isinstance(header, FrameHeader))
        self.header = header

    @staticmethod
    def construct_base(mxr:DeviceRegistry, opcode:int, protocol:int=MXR_PROTOCOL_VERSION, payload:bytes=bytes([]), size:int|None=None) -> 'FrameBase|None':
        header = FrameHeader.construct(mxr=mxr, opcode=opcode, protocol=protocol)
        if (header is None):
            return None
        rv = FrameBase(header)
        if (size is not None):
            if len(payload) > size:
                payload = payload[:size]
            elif len(payload) < size:
                payload += bytes([0 for _ in range(size - len(rv))])
        rv.payload = payload
        return rv

    @property
    def mxr(self) -> DeviceRegistry:
        # remote instance
        return self.header.mxr

    @property
    def address(self) -> str:
        # address that sent this frame
        (addr, _) = self.header.addr
        return addr

    @property
    def protocol(self) -> int:
        # frame protocol version
        return self.header.protocol

    @property
    def device_protocol(self) -> int:
        if ((dev := self.remote_device) is not None):
            return dev.protocol
        return self.protocol

    @property
    def remote_id(self) -> MxrDeviceUid:
        # unique id of the device that sent this frame
        return self.header.remote_id

    @cached_property
    def remote_device(self) -> DeviceBase|None:
        # device instance for the device that sent this frame
        return self.mxr.get_by_uid(self.remote_id)

    @property
    def payload(self) -> bytes|None:
        # frame payload bytes
        return self.header.payload

    def payload_idx(self, start:int=0, end:int=-1) -> bytes|None:
        if (self.payload is None):
            return None
        l = len(self.payload)
        if (start >= l):
            return None
        if (end < start) or (end > l):
            end = l
        return self.payload[start:end]

    def payload_bay(self, device:DeviceBase|None, idx:int, u16:bool=False) -> BayBase|None:
        if (device is None):
            return None
        portnum = self.payload_u16(idx=idx) if u16 else self.payload_u8(idx=idx)
        if (portnum is None):
            return None
        return device.get_by_portnum(portnum)

    def payload_device(self, idx:int) -> DeviceBase|None:
        if (self.remote_device is None):
            return None
        return self.remote_device.registry.get_by_uid(self.payload_uuid(idx=idx))

    def payload_u8(self, idx:int) -> int|None:
        return self.header.payload_u8(idx=idx)

    def payload_bool(self, idx:int) -> bool|None:
        return self.header.payload_bool(idx=idx)

    def payload_u16(self, idx:int=0) -> int|None:
        return self.header.payload_u16(idx=idx)

    def payload_u32(self, idx:int=0) -> int|None:
        return self.header.payload_u32(idx=idx)

    def payload_str(self, idx:int, length:int=-1) -> str|None:
        return self.header.payload_str(idx=idx, length=length)

    def payload_uuid(self, idx:int=0) -> MxrDeviceUid|None:
        return self.header.payload_uuid(idx=idx)

    @payload.setter
    def payload(self, val:bytes) -> None:
        self.header.payload = val

    @property
    def frame(self) -> bytes:
        return self.header.data

    def process(self) -> None:
        # update the local cache with the new data that was received in this frame
        pass

    def __len__(self) -> int:
        # number of payload bytes
        return self.header.payload_len

    def __str__(self) -> str:
        return f"generic frame opcode {self.header.opcode:X}"
