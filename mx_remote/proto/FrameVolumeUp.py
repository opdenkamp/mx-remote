##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Protocol frame for volume up button press events.'''

from functools import cached_property
from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import BayBase

class FrameVolumeUp(FrameBase):
    '''Volume up button pressed on a bay.'''
    @cached_property
    def bay(self) -> BayBase|None:
        '''Bay on which volume up was pressed.'''
        return self.payload_bay(device=self.remote_device, idx=0)

    def process(self) -> None:
        '''No-op; volume up events are handled elsewhere.'''
        pass

    def __str__(self) -> str:
        return f"volume up bay: {self.bay}"
