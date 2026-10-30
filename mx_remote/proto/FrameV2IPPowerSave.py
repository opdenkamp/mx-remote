######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for OneIP power saving mode configuration.'''

from functools import cached_property
from typing import Any
from ..Interface import MxrDeviceUid, DeviceBase, DeviceRegistry
from .FrameBase import FrameBase

_OPCODE = 0x41

class FrameV2IPPowerSave(FrameBase):
    '''A request for OneIP units to enter or leave power save.

    A unit tells the two forms apart by their exact length: 17 bytes, the uid
    of the unit asked and then the flag, or the flag alone, which reaches every
    unit. It takes either only from its mesh controller or a management
    application, and one that cannot power down ignores it.
    '''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:Any, target_uid:MxrDeviceUid, suspend:bool) -> FrameBase|None:
        '''Build the request asking one unit.'''
        return FrameBase.construct_base(mxr=mxr, opcode=_OPCODE, target=target,
                                        payload=(target_uid.byte_value + bytes([int(suspend)])))

    @staticmethod
    def construct_all(mxr:DeviceRegistry, suspend:bool) -> FrameBase|None:
        '''Build the request asking every unit.'''
        return FrameBase.construct_base(mxr=mxr, opcode=_OPCODE, payload=bytes([int(suspend)]))

    def process(self) -> None:
        '''No-op; power save state is informational only.'''
        pass

    @cached_property
    def enable(self) -> bool | None:
        '''Whether power saving is enabled.'''
        if self.payload is None:
            return None
        if len(self.payload) == 1:
            return self.payload_bool(0)
        return self.payload_bool(16)

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        '''UID of the target device.'''
        if self.payload is None:
            return None
        if len(self.payload) < 16:
            return None
        return self.payload_uuid(0)

    @cached_property
    def target(self) -> DeviceBase|None:
        '''Target device for the power save setting.'''
        if self.payload is None:
            return None
        if len(self.payload) < 16:
            return None
        return self.payload_device(0)

    def __str__(self) -> str:
        return f"{str(self.target)} power saving = {self.enable}"
