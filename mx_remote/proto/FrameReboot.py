##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Protocol frame for device reboot commands.'''

import warnings
from .FrameBase import FrameBase
from ..Interface import DeviceBase, DeviceRegistry

class FrameReboot(FrameBase):
    '''Reboot command for a target device.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:DeviceBase) -> FrameBase|None:
        '''Build a reboot frame for transmission to the target device.'''
        return FrameBase.construct_base(mxr=mxr, opcode=0x28, payload=target.remote_id.byte_value)
    
    def __str__(self) -> str:
        return "reboot"
