##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Protocol frame for hiding or showing a bay in the device UI.'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import BayBase, DeviceRegistry, DeviceBase, HiddenStatus
import logging

_LOGGER = logging.getLogger(__name__)

class FrameBayHide(FrameBase):
    '''Bay hide/show command and notification.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:BayBase, hidden:bool) -> FrameBase|None:
        '''Build a bay hide/show frame for transmission.'''
        payload = target.device.remote_id.byte_value + \
            bytes([(target.port >> 0) & 0xFF, (target.port >> 8) & 0xFF]) + \
            bytes([1 if hidden else 0]) + \
            bytes([0 for _ in range(5)])
        return FrameBase.construct_base(mxr=mxr, opcode=0x27, payload=payload)

    @cached_property
    def target(self) -> DeviceBase|None:
        '''Target device.'''
        return self.payload_device(idx=0)

    @cached_property
    def bay(self)  -> BayBase|None:
        '''Bay whose visibility is being changed.'''
        return self.payload_bay(device=self.target, idx=16, u16=True)

    @cached_property
    def hidden(self) -> HiddenStatus:
        '''New hidden/visible status.'''
        pl = self.payload_bool(18)
        if (pl is None):
            return HiddenStatus.UNKNOWN
        return HiddenStatus.HIDDEN if pl else HiddenStatus.VISIBLE

    def process(self) -> None:
        '''Update the local device cache with the bay hidden status.'''
        if ((bay := self.bay) is None):
            return
        bay.on_mxr_update(self.hidden)

    def __str__(self) -> str:
        return f"bay hide {self.bay} hidden={self.hidden}"
