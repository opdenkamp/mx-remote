##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import BayBase

class FrameVolumeUp(FrameBase):
    ''' volume up pressed frame '''
    @cached_property
    def bay(self) -> BayBase|None:
        return self.payload_bay(device=self.remote_device, idx=0)

    def process(self):
        pass

    def __str__(self):
        return f"volume up bay: {self.bay}"
