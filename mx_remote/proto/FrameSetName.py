######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for changing a bay name on a device.'''

from .FrameBase import FrameBase
from ..Interface import DeviceRegistry, BayBase

class FrameSetName(FrameBase):
    '''Change a bay name.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:BayBase, name:str) -> FrameBase|None:
        '''Build a bay name change frame for transmission.'''
        if len(name) > 16:
            name = name[:16]
        name_bytes = name.encode(encoding='ascii').ljust(16, b'\x00')
        payload = target.device.remote_id.byte_value + \
            bytes([(target.port >> 0) & 0xFF, (target.port >> 8) & 0xFF]) + \
            name_bytes
        return FrameBase.construct_base(mxr=mxr, opcode=0x22, protocol=0x11, payload=payload)

    def __str__(self) -> str:
        return f"Name change"
