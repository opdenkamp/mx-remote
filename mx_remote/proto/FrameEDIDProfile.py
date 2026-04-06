##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Protocol frame for EDID profile change commands.'''

from .FrameBase import FrameBase
from ..Interface import DeviceRegistry, DeviceBase, EdidProfile

class FrameEDIDProfile(FrameBase):
    '''Change an EDID profile on a target device.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:DeviceBase, profile:EdidProfile) -> FrameBase|None:
        '''Build an EDID profile change frame for transmission.'''
        payload = target.remote_id.byte_value + \
            bytes([(profile.value >> 0) & 0xFF, (profile.value >> 8) & 0xFF]) + \
            bytes([0 for _ in range(6)])
        return FrameBase.construct_base(mxr=mxr, opcode=0x34, payload=payload)

    def __str__(self) -> str:
        return f"EDID profile change"
