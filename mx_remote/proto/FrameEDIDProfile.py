##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import DeviceRegistry, DeviceBase, EdidProfile

class FrameEDIDProfile(FrameBase):
    ''' Change an EDID profile '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    def construct(mxr:DeviceRegistry, target:DeviceBase, profile:EdidProfile) -> FrameBase:
        payload = target.remote_id.byte_value + \
            bytes([(profile.value >> 0) & 0xFF, (profile.value >> 8) & 0xFF]) + \
            bytes([0 for _ in range(6)])
        return FrameBase.construct_frame(mxr=mxr, opcode=0x34, payload=payload)

    def __str__(self) -> str:
        return f"EDID profile change"
