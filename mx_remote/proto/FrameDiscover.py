######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for network device discovery.'''

import warnings
from .FrameBase import FrameBase
from ..Interface import DeviceRegistry

class FrameDiscover(FrameBase):
    '''Discovery frame that asks all devices on the network to send their info.'''
    @staticmethod
    def construct(mxr:DeviceRegistry) -> FrameBase|None:
        '''Build a discovery broadcast frame for transmission.'''
        return FrameBase.construct_base(mxr=mxr, opcode=1, protocol=1)

    def __str__(self) -> str:
        return "discover devices"

def constructFrameDiscover(mxr:DeviceRegistry) -> FrameBase|None:
    warnings.warn("use FrameDiscover.construct() instead", DeprecationWarning)
    return FrameDiscover.construct(mxr=mxr)