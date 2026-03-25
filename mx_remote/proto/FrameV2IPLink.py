##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase

class FrameV2IPLinkStatus(FrameBase):
    def __str__(self) -> str:
        return f"v2ip r/c link status"
