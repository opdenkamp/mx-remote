##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################

import warnings
from .FrameBase import FrameBase
from ..Interface import DeviceBase, DeviceRegistry

class FrameReboot(FrameBase):
    ''' remote control key press or action '''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:DeviceBase) -> FrameBase|None:
        return FrameBase.construct_base(mxr=mxr, opcode=0x28, payload=target.remote_id.byte_value)
    
    def __str__(self) -> str:
        return "reboot"
