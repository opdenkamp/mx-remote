##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader

class FrameEDID(FrameBase):
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    @property
    def port(self):
        return "Output" if self.payload[0] == 1 else "Input"

    def __str__(self) -> str:
        return f"EDID data {self.port}"
