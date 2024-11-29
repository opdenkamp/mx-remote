##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from .Constants import RCAction
from ..Interface import BayBase, DeviceBase, DeviceRegistry
from ..Uid import MxrDeviceUid
import logging

_LOGGER = logging.getLogger(__name__)

class FrameTXRCAction(FrameBase):
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    def construct(mxr:DeviceRegistry, target:BayBase, action:RCAction) -> FrameBase:
        payload = target.device.remote_id.byte_value
        payload += bytes([(target.port & 0xFF), ((target.port >> 8) & 0xFF), (int(action.value) & 0xFF), ((int(action.value) >> 8) & 0xFF)])
        frame:FrameBase = FrameBase.construct_frame(mxr=mxr, opcode=0x0E)
        frame.payload = payload
        return frame

    @property
    def target_device(self) -> DeviceBase:
        return self.mxr.get_by_uid(self.target_uid)

    @property
    def target_uid(self) -> MxrDeviceUid:
        return MxrDeviceUid(self.payload[0:16])

    @property
    def bay(self) -> BayBase:
        # bay that received the key press
        dev = self.remote_device
        if dev is None:
            return None
        portnum = ((int(self.payload[17]) << 8) | int(self.payload[16]))
        return dev.get_by_portnum(portnum)

    @property
    def action(self) -> RCAction:
        dev = self.remote_device
        if dev is None:
            return None
        return RCAction(int(self.payload[20]))

    def process(self) -> None:
        bay = self.bay
        if bay is not None:
            bay.on_action_received(self.action)

    def __str__(self) -> str:
        return f"{self.bay} action receive: {self.action}"
