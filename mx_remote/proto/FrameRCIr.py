##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import BayBase
import logging

_LOGGER = logging.getLogger(__name__)

class FrameRCIr(FrameBase):
    ''' IR key press '''
    @cached_property
    def bay(self) -> BayBase|None:
        return self.payload_bay(device=self.remote_device, idx=0, u16=True)

    @cached_property
    def timestamp(self) -> int|None:
        return self.payload_u32(idx=2)

    def __str__(self) -> str:
        return f"IR key press bay {self.bay} timestamp {self.timestamp}"
