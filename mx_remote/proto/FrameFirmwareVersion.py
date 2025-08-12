##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
from .FrameBase import FrameBase
from .Constants import FirmwareType
from ..Interface import FirmwareVersion

class FrameFirmwareVersion(FrameBase):
    @cached_property
    def fw_type(self) -> FirmwareType:
        return FirmwareType(self.payload_u8(0))

    @cached_property
    def fw_version(self) -> str|None:
        return self.payload_str(12)

    @cached_property
    def hash(self) -> int|None:
        return self.payload_u32(4)

    @cached_property
    def timestamp(self) -> int|None:
        return self.payload_u32(8)

    @cached_property
    def version(self) -> FirmwareVersion|None:
        if ((version := self.fw_version) is not None) and ((timestamp := self.timestamp) is not None):
            if ((hash := self.hash) is None):
                hash = 0
            return FirmwareVersion(type=self.fw_type, timestamp=timestamp, version=version, hash=hash)
        return None

    def process(self) -> None:
        if ((dev := self.remote_device) is not None) and ((version := self.version) is not None):
            dev.on_mxr_update(version)

    def __str__(self) -> str:
        hash = self.hash if (self.hash is not None) else 0
        return f"firmware version: type {self.fw_type}: '{self.fw_version}' hash: {hex(hash)} timestamp: {self.timestamp}"

    def __repr__(self) -> str:
        return str(self)