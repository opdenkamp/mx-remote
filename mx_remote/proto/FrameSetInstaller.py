##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Protocol frame for SET_INSTALLER (opcode 0x37).

The mesh controller broadcasts the installer id to align peers' PMS
attribution. Payload is a single little-endian uint16.
'''

from functools import cached_property
from .FrameBase import FrameBase

class FrameSetInstaller(FrameBase):
    '''Installer id propagation.'''

    @cached_property
    def installer_id(self) -> int | None:
        return self.payload_u16(0)

    def __str__(self) -> str:
        return f"set installer id={self.installer_id} from {self.remote_device}"
