##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Protocol frame for EDID (Extended Display Identification Data) content.'''

from functools import cached_property
from .FrameBase import FrameBase

class FrameEDID(FrameBase):
    '''EDID data frame containing display identification information.'''
    @cached_property
    def port(self) -> str|None:
        '''Port direction: "Input" or "Output".'''
        pl = self.payload_bool(0)
        if (pl is None):
            return None
        return "Output" if pl else "Input"

    def __str__(self) -> str:
        return f"EDID data {self.port}"
