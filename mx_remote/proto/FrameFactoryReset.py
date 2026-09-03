######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for SYS_FACTORY_RESET (opcode 0x3A).

A mesh controller or management app broadcasts this to factory-reset peers.
Payload forms:
    empty            controller-only target (just the sender)
    >=1, byte 0xFF   broadcast to all peers (controller/management only)
    >=16             single target uid

Each length is a minimum and they are tested longest first. An update that
appends a field leaves the fields ahead of it where they are, so an exact
length would read a grown request as a shorter form - here, as one addressing
nobody.
'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Uid import MxrDeviceUid

class FrameFactoryReset(FrameBase):
    '''Factory reset request.'''

    @cached_property
    def is_broadcast_all(self) -> bool:
        '''Whether this asks every peer to reset.

        Tested after the uid form, which is longer: a uid whose first byte is
        0xFF would otherwise read as a broadcast.'''
        return (self.target_uid is None) and (len(self) >= 1) and (self.payload_u8(0) == 0xFF)

    @cached_property
    def target_uid(self) -> MxrDeviceUid | None:
        '''Uid of the single peer being reset, None when the request names none.

        A minimum rather than an exact length. A sender that appends a field
        leaves the uid where it is, so requiring 16 exactly would read a grown
        request as one addressing nobody - which is the sender resetting itself,
        a different request altogether.'''
        if (len(self) >= 16):
            return self.payload_uuid(0)
        return None

    def __str__(self) -> str:
        if self.is_broadcast_all:
            return f"factory reset (broadcast) from {self.remote_device}"
        if (uid := self.target_uid) is not None:
            return f"factory reset target {self.uid_to_user_string(uid)} from {self.remote_device}"
        return f"factory reset from {self.remote_device}"
