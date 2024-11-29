##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import DeviceRegistry

class FrameDiscover(FrameBase):
    ''' Discovery, ask all devices on the network to send their info '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    def construct(mxr:DeviceRegistry) -> FrameBase:
        return FrameBase.construct_frame(mxr=mxr, opcode=1, protocol=1)

    def __str__(self) -> str:
        return "discover devices"
