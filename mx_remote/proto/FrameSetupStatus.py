##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Protocol frame for SETUP_STATUS (opcode 0x35).

The mesh controller broadcasts the setup-completed status of a peer. Peers
mirror MXR_FEATURE_SETUP_COMPLETED based on this bit so the UI can show
"setup complete" consistently across the mesh.
'''

from functools import cached_property
from .FrameBase import FrameBase

class FrameSetupStatus(FrameBase):
    '''Setup-completed status announcement.

    Wire layout (per mxr_dev_tx_setup_status, mxr_device.c:818):
        0     uint8_t status   1 = setup complete, 0 = not complete
    '''

    @cached_property
    def setup_completed(self) -> bool | None:
        return self.payload_bool(0)

    def __str__(self) -> str:
        return f"setup status from {self.remote_device}: completed={self.setup_completed}"
