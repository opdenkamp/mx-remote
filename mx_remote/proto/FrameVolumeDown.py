######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for volume down button press events.'''

from functools import cached_property
from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import BayBase

class FrameVolumeDown(FrameBase):
    '''Volume down button pressed on a bay.'''
    @cached_property
    def bay(self) -> BayBase|None:
        '''Bay on which volume down was pressed.'''
        return self.payload_bay(device=self.remote_device, idx=0)

    def process(self) -> None:
        '''No-op; volume down events are handled elsewhere.'''
        pass

    def __str__(self) -> str:
        return f"volume down bay: {self.bay}"
