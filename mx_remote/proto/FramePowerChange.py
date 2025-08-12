##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import BayBase, PowerStatus

class FramePowerChange(FrameBase):
    ''' power status changed of a device connected to a bay '''
    @cached_property
    def bay(self) -> BayBase|None:
        return self.payload_bay(device=self.remote_device, idx=0)

    @cached_property
    def power(self) -> bool|None:
        # new power status
        return self.payload_bool(1)

    def process(self) -> None:
        if ((bay := self.bay) is not None) and (self.power is not None):
            bay.on_mxr_update(PowerStatus.ON if self.power else PowerStatus.OFF)

    def __str__(self):
        return f"{self.bay} power status: {self.power}"