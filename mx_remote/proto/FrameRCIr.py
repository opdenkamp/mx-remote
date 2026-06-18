######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for infrared (IR) remote control key press events.'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import BayBase
import logging

_LOGGER = logging.getLogger(__name__)

class FrameRCIr(FrameBase):
    '''IR key press event received by a bay.'''
    @cached_property
    def bay(self) -> BayBase|None:
        '''Bay that received the IR key press.'''
        return self.payload_bay(device=self.remote_device, idx=0, u16=True)

    @cached_property
    def timestamp(self) -> int|None:
        '''Timestamp of the IR key press event.'''
        return self.payload_u32(idx=2)

    def __str__(self) -> str:
        return f"IR key press bay {self.bay} timestamp {self.timestamp}"
