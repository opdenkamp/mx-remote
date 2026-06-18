######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for V2IP_UPGRADE_FPGA (opcode 0x2C).

A mesh controller broadcasts this to ask peers to upgrade their V2IP FPGA
to the version currently active on the controller. Payload is empty.
'''

from .FrameBase import FrameBase

class FrameUpgradeFPGA(FrameBase):
    '''Request to upgrade the V2IP FPGA on receiving peers.'''

    def __str__(self) -> str:
        return f"v2ip fpga upgrade request from {self.remote_device}"
