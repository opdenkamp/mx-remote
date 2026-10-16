######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for SYS_FACTORY_RESET (opcode 0x3A).

A mesh controller or management app broadcasts this to factory-reset units.
It addresses them as a reboot does: see manage_target().
'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Uid import MxrDeviceUid

_MANAGE_ALL = 0xFF
'''The one-byte payload that addresses every unit.'''

def manage_target(frame:FrameBase) -> tuple[bool, MxrDeviceUid|None]|None:
    '''Whom a reboot or factory reset addresses: (True, None) for every unit,
    (False, uid) for one, and None for a frame a unit drops.

    A unit takes an empty payload or the single byte 0xFF as every unit, and
    exactly a 16-byte uid as one; it drops any other length.'''
    pl = frame.payload or b''
    if (len(pl) == 0) or (pl == bytes([_MANAGE_ALL])):
        return (True, None)
    if (len(pl) == 16):
        return (False, frame.payload_uuid(0))
    return None

class FrameFactoryReset(FrameBase):
    '''Factory reset request.'''

    @cached_property
    def is_broadcast_all(self) -> bool:
        '''Whether this asks every unit to reset.'''
        return ((target := manage_target(self)) is not None) and target[0]

    @cached_property
    def target_uid(self) -> MxrDeviceUid | None:
        '''Uid of the single unit being reset, None when the request names none.'''
        return target[1] if ((target := manage_target(self)) is not None) else None

    def __str__(self) -> str:
        if self.is_broadcast_all:
            return f"factory reset (every unit) from {self.remote_device}"
        if (uid := self.target_uid) is not None:
            return f"factory reset target {self.uid_to_user_string(uid)} from {self.remote_device}"
        return f"factory reset of no length a unit takes, from {self.remote_device}"
