######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for firmware version information.'''

from functools import cached_property
from .FrameBase import FrameBase
from .Constants import FirmwareType, MXR_FW_VERSION_LEN
from ..Interface import FirmwareVersion

class FrameFirmwareVersion(FrameBase):
    '''Firmware version report from a device.'''
    @cached_property
    def fw_type(self) -> FirmwareType:
        '''Firmware component type.'''
        return FirmwareType(self.payload_u8(0))

    @cached_property
    def fw_version(self) -> str|None:
        '''Firmware version string (fixed-width MXR_FW_VERSION_LEN field).'''
        return self.payload_str(12, MXR_FW_VERSION_LEN)

    @cached_property
    def hash(self) -> int|None:
        '''Firmware build hash.'''
        return self.payload_u32(4)

    @cached_property
    def build_timestamp(self) -> int|None:
        '''Firmware build/installation timestamp.

        Not `timestamp`: FrameBase sets that as an instance attribute in
        __init__ for our own receive time, and an instance attribute shadows a
        cached_property of the same name - so a property called `timestamp`
        here was never reached, and the build time read back as the moment we
        happened to receive the frame.
        '''
        return self.payload_u32(8)

    @cached_property
    def version(self) -> FirmwareVersion|None:
        '''Assembled FirmwareVersion object, or None if data is incomplete.'''
        if ((version := self.fw_version) is not None) and ((timestamp := self.build_timestamp) is not None):
            if ((hash := self.hash) is None):
                hash = 0
            return FirmwareVersion(type=self.fw_type, timestamp=timestamp, version=version, hash=hash)
        return None

    def process(self) -> None:
        '''Update the local device cache with the firmware version.'''
        if ((dev := self.remote_device) is not None) and ((version := self.version) is not None):
            dev.on_mxr_update(version)

    def __str__(self) -> str:
        hash = self.hash if (self.hash is not None) else 0
        return f"firmware version: type {self.fw_type}: '{self.fw_version}' hash: {hex(hash)} built: {self.build_timestamp}"

    def __repr__(self) -> str:
        return str(self)