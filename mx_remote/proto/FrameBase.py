######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################

'''Base class and utilities for decoded MX Remote protocol frames.'''

from functools import cached_property
import time
from .Constants import MXR_PROTOCOL_VERSION
from .FrameHeader import FrameHeader
from ..Interface import DeviceBase, DeviceRegistry, BayBase
from ..Uid import MxrDeviceUid

def append_payload_str(payload:list[int], value:str, sz:int) -> list[int]:
    '''Append a fixed-size ASCII string to a payload byte list, zero-padded to sz.'''
    value = value[0:16]
    return payload + list(value.encode('ascii')) + [ 0 for _ in range(sz - len(value))]

class FrameBase:
    ''' Base class for decoded mx_remote frames '''
    def __init__(self, header:FrameHeader, timestamp:float|None=None) -> None:
        assert(isinstance(header, FrameHeader))
        self.header = header
        self.timestamp = timestamp if (timestamp is not None) else time.time()

    @staticmethod
    def construct_base(mxr:DeviceRegistry, opcode:int, protocol:int=MXR_PROTOCOL_VERSION, payload:bytes=bytes([]), size:int|None=None) -> 'FrameBase|None':
        '''Construct a new frame for transmission with the given opcode and payload.'''
        header = FrameHeader.construct(mxr=mxr, opcode=opcode, protocol=protocol)
        if (header is None):
            return None
        rv = FrameBase(header)
        if (size is not None):
            if len(payload) > size:
                payload = payload[:size]
            elif len(payload) < size:
                payload += bytes([0 for _ in range(size - len(payload))])
        rv.payload = payload
        return rv

    @property
    def mxr(self) -> DeviceRegistry:
        '''Remote instance.'''
        return self.header.mxr

    @property
    def address(self) -> str:
        '''Address that sent this frame.'''
        (addr, _) = self.header.addr
        return addr

    @property
    def protocol(self) -> int:
        '''Frame protocol version.'''
        return self.header.protocol

    @property
    def device_protocol(self) -> int:
        if ((dev := self.remote_device) is not None):
            return dev.protocol
        return self.protocol

    @property
    def remote_id(self) -> MxrDeviceUid:
        '''Unique id of the device that sent this frame.'''
        return self.header.remote_id

    @cached_property
    def remote_device(self) -> DeviceBase|None:
        '''Device instance for the device that sent this frame.'''
        return self.mxr.get_by_uid(self.remote_id)

    @property
    def payload(self) -> bytes|None:
        '''Frame payload bytes.'''
        return self.header.payload

    def payload_idx(self, start:int=0, end:int=-1) -> bytes|None:
        '''Return a slice of the payload from start to end.'''
        if (self.payload is None):
            return None
        l = len(self.payload)
        if (start >= l):
            return None
        if (end < start) or (end > l):
            end = l
        return self.payload[start:end]

    def payload_bay(self, device:DeviceBase|None, idx:int, u16:bool=False) -> BayBase|None:
        '''Look up a bay by port number extracted from the payload at idx.'''
        if (device is None):
            return None
        portnum = self.payload_u16(idx=idx) if u16 else self.payload_u8(idx=idx)
        if (portnum is None):
            return None
        return device.get_by_portnum(portnum)

    def payload_device(self, idx:int) -> DeviceBase|None:
        '''Look up a device by UUID extracted from the payload at idx.'''
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

    def payload_bytes(self, idx:int) -> bytes|None:
        return self.header.payload_bytes(idx=idx)

    @payload.setter
    def payload(self, val:bytes) -> None:
        self.header.payload = val

    @property
    def frame(self) -> bytes:
        return self.header.data

    def process(self) -> None:
        '''Update the local cache with the new data that was received in this frame.'''
        pass

    def uid_to_user_string(self, uid:str|MxrDeviceUid|bytes|None) -> str:
        '''Convert a device UID to a human-readable name via the device registry.'''
        if (uid is None):
            return '<none>'
        if not isinstance(uid, MxrDeviceUid):
            uid = MxrDeviceUid(uid)
        if (self.remote_device is None):
            return str(uid)
        return self.remote_device.registry.uid_to_user_string(uid)

    def __len__(self) -> int:
        '''Number of payload bytes.'''
        return self.header.payload_len

    def __str__(self) -> str:
        return f"generic frame opcode {self.header.opcode:X}"
