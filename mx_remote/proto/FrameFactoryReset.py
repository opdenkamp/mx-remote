##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Protocol frame for SYS_FACTORY_RESET (opcode 0x3A).

A mesh controller or management app broadcasts this to factory-reset peers.
Payload variants accepted by the firmware (see _mxr_check_mng_payload):
    empty           controller-only target (just the sender)
    1 byte = 0xFF   broadcast to all peers (controller/management only)
    16 bytes        single target uid
'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Uid import MxrDeviceUid

class FrameFactoryReset(FrameBase):
    '''Factory reset request.'''

    @cached_property
    def is_broadcast_all(self) -> bool:
        return (len(self) == 1) and (self.payload_u8(0) == 0xFF)

    @cached_property
    def target_uid(self) -> MxrDeviceUid | None:
        if (len(self) == 16):
            return self.payload_uuid(0)
        return None

    def __str__(self) -> str:
        if self.is_broadcast_all:
            return f"factory reset (broadcast) from {self.remote_device}"
        if (uid := self.target_uid) is not None:
            return f"factory reset target {self.uid_to_user_string(uid)} from {self.remote_device}"
        return f"factory reset from {self.remote_device}"
