######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for V2IP_UPGRADE_FPGA (opcode 0x2C).

A mesh controller broadcasts this to have every unit flash the latest OneIP video
processor image it holds. Payload is empty, so it carries no force: a unit flashes
only when its running image differs, and takes the request only from management.
'''

from .FrameBase import FrameBase
from ..Interface import DeviceRegistry

class FrameUpgradeFPGA(FrameBase):
    '''Request to upgrade the OneIP video processor on every unit.'''
    @staticmethod
    def construct(mxr:DeviceRegistry) -> FrameBase|None:
        '''Build the request for transmission.'''
        return FrameBase.construct_base(mxr=mxr, opcode=0x2C)

    def __str__(self) -> str:
        return f"v2ip fpga upgrade request from {self.remote_device}"
