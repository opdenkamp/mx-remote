######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for firmware version information.'''

from functools import cached_property
from .FrameBase import FrameBase
from .Constants import FirmwareType, MXR_FW_VERSION_LEN, decode_enum
from ..Interface import FirmwareVersion

# A video processor report carries two more blocks behind its 144 bytes. The
# first, up to 152, holds the hashes of the RTOS and loader images, which share
# the video processor's version and install time. The second, up to 200,
# describes the unit's own firmware and its bootloader: a u32 hash and a u32 time
# each at 152 and 160, then their 16-byte versions at 168 and 184.
_RTOS_LOADER_END = 152
_MCU_END = 200

class FrameFirmwareVersion(FrameBase):
    '''Firmware version report from a device.'''
    @cached_property
    def fw_type(self) -> FirmwareType:
        '''Firmware component type.'''
        fw = decode_enum(FirmwareType, self.payload_u8(0))
        return fw if (fw is not None) else FirmwareType.UNKNOWN

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

        Not named `timestamp`: FrameBase assigns that instance attribute for our
        own receive time, and an instance attribute shadows a cached_property of
        the same name.
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

    @cached_property
    def versions(self) -> list[FirmwareVersion]:
        '''Every component the report describes: its own, and behind a video
        processor's the RTOS, the loader, the unit's firmware and its
        bootloader, as far as the frame reaches.'''
        if ((version := self.version) is None):
            return []
        rv = [version]
        if (self.fw_type != FirmwareType.VIDEO_PROCESSOR):
            return rv
        length = len(self.payload or b'')
        if (length >= _RTOS_LOADER_END):
            for fw_type, at in ((FirmwareType.RTOS, 144), (FirmwareType.LOADER, 148)):
                rv.append(FirmwareVersion(type=fw_type, timestamp=version.timestamp, version=version.version,
                                          hash=(self.payload_u32(at) or 0)))
        if (length >= _MCU_END):
            for fw_type, at, version_at in ((FirmwareType.MCU, 152, 168), (FirmwareType.BOOTLOADER, 160, 184)):
                rv.append(FirmwareVersion(type=fw_type, timestamp=(self.payload_u32(at + 4) or 0),
                                          version=(self.payload_str(version_at, 16) or ''),
                                          hash=(self.payload_u32(at) or 0)))
        return rv

    def process(self) -> None:
        '''Update the local device cache with every firmware version reported.'''
        if ((dev := self.remote_device) is not None):
            for version in self.versions:
                dev.on_mxr_update(version)

    def __str__(self) -> str:
        hash = self.hash if (self.hash is not None) else 0
        return f"firmware version: type {self.fw_type}: '{self.fw_version}' hash: {hex(hash)} built: {self.build_timestamp}"

    def __repr__(self) -> str:
        return str(self)