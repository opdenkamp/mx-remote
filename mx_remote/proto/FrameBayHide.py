##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .Constants import BayStatusMask
from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import BayBase, DeviceRegistry, DeviceBase, MxrDeviceUid
import logging
import struct

_LOGGER = logging.getLogger(__name__)

class FrameBayHide(FrameBase):
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    def construct(mxr:DeviceRegistry, target:BayBase, hidden:bool) -> FrameBase:
        payload = target.device.remote_id.byte_value + \
            bytes([(target.port >> 0) & 0xFF, (target.port >> 8) & 0xFF]) + \
            bytes([0 for _ in range(6)]) + \
            bytes([1 if hidden else 0]) + \
            bytes([0 for _ in range(7)])
        return FrameBase.construct_frame(mxr=mxr, opcode=0x27, payload=payload)

    @property
    def target_uid(self) -> DeviceBase:
        return MxrDeviceUid(self.payload[0:16])

    @property
    def target(self) -> DeviceBase:
        return self.remote_device.registry.get_by_uid(self.target_uid)

    @property
    def bay(self)  -> BayBase:
        target = self.target
        if target is None:
            return None
        portnum = ((self.payload[17] << 8) | self.payload[18])
        return target.get_by_portnum(portnum)

    @property
    def hidden(self) -> bool:
        return (self.payload[24] == 1)

    def process(self) -> None:
        pass

    def __str__(self) -> str:
        return f"bay hide {self.bay} hidden={self.hidden}"
