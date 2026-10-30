######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for SET_INSTALLER (opcode 0x37).

The mesh controller broadcasts the installer id to align peers' PMS
attribution. Payload is a single little-endian uint16.
'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import DeviceRegistry
import struct

class FrameSetInstaller(FrameBase):
    '''Installer id propagation.'''

    @staticmethod
    def construct(mxr:DeviceRegistry, installer:int) -> FrameBase|None:
        '''Set the installer id of every unit that hears it.'''
        return FrameBase.construct_base(mxr=mxr, opcode=0x37, payload=struct.pack('<H', installer))

    @cached_property
    def installer_id(self) -> int | None:
        return self.payload_u16(0)

    def __str__(self) -> str:
        return f"set installer id={self.installer_id} from {self.remote_device}"
