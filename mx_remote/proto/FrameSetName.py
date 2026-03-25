##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from ..Interface import DeviceRegistry, BayBase

class FrameSetName(FrameBase):
    ''' Change a bay name '''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:BayBase, name:str) -> FrameBase|None:
        if len(name) > 16:
            name = name[:16]
        name_bytes = name.encode(encoding='ascii')
        payload = target.device.remote_id.byte_value + \
            bytes([(target.port >> 0) & 0xFF, (target.port >> 8) & 0xFF]) + \
            name_bytes
        return FrameBase.construct_base(mxr=mxr, opcode=0x22, payload=payload, size=40)

    def __str__(self) -> str:
        return f"Name change"
