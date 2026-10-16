######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for device reboot commands.'''

from functools import cached_property
import warnings
from .FrameBase import FrameBase
from .FrameFactoryReset import manage_target
from ..Interface import DeviceBase, DeviceRegistry
from ..Uid import MxrDeviceUid

class FrameReboot(FrameBase):
    '''Reboot command for every unit, or one. It addresses them as a factory
    reset does: see manage_target().'''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:DeviceBase) -> FrameBase|None:
        '''Build a reboot frame for transmission to the target device.'''
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x28, payload=target.remote_id.byte_value)

    @cached_property
    def is_broadcast_all(self) -> bool:
        '''Whether this asks every unit to reboot.'''
        return ((target := manage_target(self)) is not None) and target[0]

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        '''Uid of the single unit being rebooted, None when the request names none.'''
        return target[1] if ((target := manage_target(self)) is not None) else None

    def __str__(self) -> str:
        if self.is_broadcast_all:
            return "reboot every unit"
        if ((uid := self.target_uid) is not None):
            return f"reboot {self.uid_to_user_string(uid)}"
        return "reboot of no length a unit takes"
