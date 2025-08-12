##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from ..Interface import DeviceRegistry, DeviceBase, EdidProfile

class FrameEDIDProfile(FrameBase):
    ''' Change an EDID profile '''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:DeviceBase, profile:EdidProfile) -> FrameBase|None:
        payload = target.remote_id.byte_value + \
            bytes([(profile.value >> 0) & 0xFF, (profile.value >> 8) & 0xFF]) + \
            bytes([0 for _ in range(6)])
        return FrameBase.construct_base(mxr=mxr, opcode=0x34, payload=payload)

    def __str__(self) -> str:
        return f"EDID profile change"
