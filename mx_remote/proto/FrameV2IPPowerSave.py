######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for V2IP power saving mode configuration.'''

from functools import cached_property
from ..Interface import MxrDeviceUid, DeviceBase
from .FrameBase import FrameBase

class FrameV2IPPowerSave(FrameBase):
    '''V2IP power saving mode status or configuration.'''
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
