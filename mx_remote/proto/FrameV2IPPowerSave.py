##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
from ..Interface import MxrDeviceUid, DeviceBase
from .FrameBase import FrameBase

class FrameV2IPPowerSave(FrameBase):
    def process(self) -> None:
        pass

    @cached_property
    def enable(self) -> bool | None:
        if self.payload is None:
            return None
        if len(self.payload) == 1:
            return self.payload_bool(0)
        return self.payload_bool(16)

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        if self.payload is None:
            return None
        if len(self.payload) < 16:
            return None
        return self.payload_uuid(0)

    @cached_property
    def target(self) -> DeviceBase|None:
        if self.payload is None:
            return None
        if len(self.payload) < 16:
            return None
        return self.payload_device(0)

    def __str__(self) -> str:
        return f"{str(self.target)} power saving = {self.enable}"
