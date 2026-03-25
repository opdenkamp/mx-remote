##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
from .FrameBase import FrameBase

class FrameEDID(FrameBase):
    @cached_property
    def port(self) -> str|None:
        pl = self.payload_bool(0)
        if (pl is None):
            return None
        return "Output" if pl else "Input"

    def __str__(self) -> str:
        return f"EDID data {self.port}"
