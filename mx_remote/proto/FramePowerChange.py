##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Protocol frame for power status change notifications.'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import BayBase, PowerStatus

class FramePowerChange(FrameBase):
    '''Power status changed of a device connected to a bay.'''
    @cached_property
    def bay(self) -> BayBase|None:
        '''Bay whose connected device changed power state.'''
        return self.payload_bay(device=self.remote_device, idx=0)

    @cached_property
    def power(self) -> bool|None:
        '''New power status.'''
        return self.payload_bool(1)

    def process(self) -> None:
        '''Update the local device cache with the new power status.'''
        if ((bay := self.bay) is not None) and (self.power is not None):
            bay.on_mxr_update(PowerStatus.ON if self.power else PowerStatus.OFF)

    def __str__(self) -> str:
        return f"{self.bay} power status: {self.power}"