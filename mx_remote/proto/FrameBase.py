##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .Constants import MXR_PROTOCOL_VERSION
from .FrameHeader import FrameHeader
from ..Interface import DeviceBase, DeviceRegistry
from ..Uid import MxrDeviceUid

def append_payload_str(payload:list[int], value:str, sz:int) -> list[int]:
    value = value[0:16]
    return payload + list(value.encode('ascii')) + [ 0 for _ in range(sz - len(value))]
class FrameBase:
    ''' Base class for decoded mx_remote frames '''
    def __init__(self, header:FrameHeader):
        assert(isinstance(header, FrameHeader))
        self.header = header

    def construct_frame(mxr:DeviceRegistry, opcode:int, protocol:int=MXR_PROTOCOL_VERSION, payload:bytes=bytes([]), size:int|None=None) -> 'FrameBase':
        rv = FrameBase(FrameHeader.construct(mxr=mxr, opcode=opcode, protocol=protocol))
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
    def remote_id(self) -> MxrDeviceUid:
        # unique id of the device that sent this frame
        return self.header.remote_id

    @property
    def remote_device(self) -> DeviceBase:
        # device instance for the device that sent this frame
        return self.mxr.get_by_uid(self.remote_id)

    @property
    def payload(self) -> bytes:
        # frame payload bytes
        return self.header.payload

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
