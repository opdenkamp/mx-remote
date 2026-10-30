######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for SETUP_STATUS (opcode 0x35).

The mesh controller broadcasts the setup-completed status of a peer. Peers
mirror MXR_FEATURE_SETUP_COMPLETED based on this bit so the UI can show
"setup complete" consistently across the mesh.
'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import DeviceRegistry

class FrameSetupStatus(FrameBase):
    '''Setup-completed status announcement.

    Wire layout (mxr_dev_tx_setup_status):
        0     uint8_t status   sent as 1 = setup complete, 0 = not complete
    '''

    @staticmethod
    def construct(mxr:DeviceRegistry, completed:bool) -> FrameBase|None:
        '''Mark the setup of every unit that hears it completed, or not.'''
        return FrameBase.construct_base(mxr=mxr, opcode=0x35, payload=bytes([int(completed)]))

    @cached_property
    def setup_completed(self) -> bool | None:
        '''Read as a unit reads it: anything but 0 is completed.'''
        value = self.payload_u8(0)
        return None if (value is None) else (value != 0)

    def __str__(self) -> str:
        return f"setup status from {self.remote_device}: completed={self.setup_completed}"
