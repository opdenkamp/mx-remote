##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader

class FrameV2IPLinkStatus(FrameBase):
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    def __str__(self) -> str:
        return f"v2ip r/c link status"
