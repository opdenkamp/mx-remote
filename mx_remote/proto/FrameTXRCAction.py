##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
import warnings
from .FrameBase import FrameBase
from .Constants import RCAction
from ..Interface import BayBase, DeviceBase, DeviceRegistry
from ..Uid import MxrDeviceUid

class FrameTXRCAction(FrameBase):
    @staticmethod
    def construct(mxr:DeviceRegistry, target:BayBase, action:RCAction) -> FrameBase|None:
        payload = target.device.remote_id.byte_value
        payload += bytes([(target.port & 0xFF), ((target.port >> 8) & 0xFF), (int(action.value) & 0xFF), ((int(action.value) >> 8) & 0xFF)])
        return FrameBase.construct_base(mxr=mxr, opcode=0x0E, payload=payload)

    @cached_property
    def target_device(self) -> DeviceBase|None:
        return self.mxr.get_by_uid(self.target_uid)

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        return self.payload_uuid(0)

    @cached_property
    def bay(self) -> BayBase|None:
        # bay that received the key press
        return self.payload_bay(device=self.target_device, idx=16, u16=True)

    @cached_property
    def action(self) -> RCAction|None:
        pl = self.payload_u8(idx=20)
        if (pl is None):
            return None
        return RCAction(pl)

    def process(self) -> None:
        if ((bay := self.bay) is not None):
            bay.on_mxr_update(self.action)

    def __str__(self) -> str:
        return f"{self.bay} action receive: {self.action}"

def constructFrameTXRCAction(mxr:DeviceRegistry, target:BayBase, action:RCAction) -> FrameBase|None:
    warnings.warn("use FrameTXRCAction.construct() instead", DeprecationWarning)
    return FrameTXRCAction.construct(mxr=mxr, target=target, action=action)
