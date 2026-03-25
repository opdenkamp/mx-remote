##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################

import warnings
from .FrameBase import FrameBase
from ..Interface import DeviceRegistry

class FrameDiscover(FrameBase):
    ''' Discovery, ask all devices on the network to send their info '''
    @staticmethod
    def construct(mxr:DeviceRegistry) -> FrameBase|None:
        return FrameBase.construct_base(mxr=mxr, opcode=1, protocol=1)

    def __str__(self) -> str:
        return "discover devices"

def constructFrameDiscover(mxr:DeviceRegistry) -> FrameBase|None:
    warnings.warn("use FrameHello.construct() instead", DeprecationWarning)
    return FrameDiscover.construct(mxr=mxr)