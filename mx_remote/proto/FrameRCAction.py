##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Protocol frame for remote control action events received by a bay.'''

from functools import cached_property
from .FrameBase import FrameBase
from .Constants import RCAction
from ..Interface import BayBase, DeviceRegistry
import logging

_LOGGER = logging.getLogger(__name__)

class FrameRCAction(FrameBase):
    '''Remote control action received by a bay.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:BayBase, action:RCAction) -> FrameBase|None:
        '''Build an RC action frame for transmission.'''
        payload = target.device.remote_id.byte_value
        payload += bytes([(target.port & 0xFF), ((target.port >> 8) & 0xFF), (int(action.value) & 0xFF), ((int(action.value) >> 8) & 0xFF)])
        return FrameBase.construct_base(mxr=mxr, opcode=0x0E, payload=payload)

    @cached_property
    def bay(self) -> BayBase|None:
        '''Bay that received the action.'''
        return self.payload_bay(device=self.remote_device, idx=0, u16=(self.device_protocol >= 6))

    @cached_property
    def action(self) -> RCAction|None:
        '''Remote control action type.'''
        pl = self.payload_u8(2)
        if (pl is None):
            return None
        return RCAction(pl)

    def process(self) -> None:
        '''Update the local device cache with the RC action.'''
        if ((bay := self.bay) is not None) and ((action := self.action) is not None):
            bay.on_mxr_update(action)

    def __str__(self) -> str:
        return f"{self.bay} action receive: {self.action}"
