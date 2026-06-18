######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for amplifier zone settings (gain, EQ, delay, power mode).'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import DeviceBase, BayBase, AmpZoneSettings, DeviceRegistry
from ..Uid import MxrDeviceUid
import logging

_LOGGER = logging.getLogger(__name__)

class FrameAmpZoneSettings(FrameBase):
    '''Amplifier zone settings for a bay (gain, EQ, delay, power mode, etc.).'''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:BayBase, settings:AmpZoneSettings) -> FrameBase|None:
        '''Build an amplifier zone settings frame for transmission.'''
        payload = bytearray()
        payload += target.device.remote_id.byte_value
        payload.append(target.port & 0xFF)
        payload.append((target.port >> 8) & 0xFF)
        payload.append(settings.gain_left & 0xFF)
        payload.append(settings.gain_right & 0xFF)
        payload.append(settings.volume_min & 0xFF)
        payload.append(settings.volume_max & 0xFF)
        payload += settings.delay_left.to_bytes(length=4, byteorder="little")
        payload += settings.delay_right.to_bytes(length=4, byteorder="little")
        payload += bytes([0, 0]) # padding
        payload.append(settings.bass & 0xFF)
        payload.append(settings.treble & 0xFF)
        payload.append(settings.bridged & 0xFF)
        payload.append(settings.power_mode & 0xFF)
        payload.append(settings.power_level & 0xFF)
        payload += bytes([0, 0, 0]) # padding
        payload += settings.power_timeout.to_bytes(length=4, byteorder="little")
        for r in range(5):
            payload.append(settings.eq_left[r] & 0xFF)
        for r in range(5):
            payload.append(settings.eq_right[r] & 0xFF)
        payload += bytes([0, 0]) # padding
        return FrameBase.construct_base(mxr=mxr, opcode=0x3D, protocol=0x1C, payload=payload)

    @property
    def target_device(self) -> DeviceBase|None:
        if self.target_uid.empty:
            return self.mxr.get_by_uid(self.header.remote_id)
        return self.mxr.get_by_uid(self.target_uid)

    @property
    def target_uid(self) -> MxrDeviceUid|None:
        return self.payload_uuid(0)

    @property
    def zone(self) -> int|None:
        return self.payload_u16(16)

    @property
    def bay(self) -> BayBase|None:
        target_device = self.target_device
        if (target_device is None) or (self.zone is None):
            _LOGGER.warning(f"amp zone settings no target uid = {self.target_uid}")
            return None
        return target_device.get_by_portnum(self.zone)

    @property
    def gain_left(self) -> int|None:
        return self.payload_u8(18)

    @property
    def gain_right(self) -> int|None:
        return self.payload_u8(19)

    @property
    def volume_min(self) -> int|None:
        return self.payload_u8(20)

    @property
    def volume_max(self) -> int|None:
        return self.payload_u8(21)

    @property
    def delay_left(self) -> int:
        return int.from_bytes(self.payload[22:26], "little")

    @property
    def delay_right(self) -> int:
        return int.from_bytes(self.payload[26:30], "little")

    @property
    def bass(self) -> int|None:
        return self.payload_u8(32)

    @property
    def treble(self) -> int|None:
        return self.payload_u8(33)

    @property
    def bridged(self) -> int|None:
        return self.payload_u8(34)

    @property
    def power_mode(self) -> int|None:
        return self.payload_u8(35)

    @property
    def power_level(self) -> int|None:
        return self.payload_u8(36)

    @property
    def power_timeout(self) -> int:
        return int.from_bytes(self.payload[40:44], "little")

    @property
    def eq_left(self) -> list[int]:
        return [int(x) for x in self.payload[44:49]]

    @property
    def eq_right(self) -> list[int]:
        return [int(x) for x in self.payload[49:54]]

    @cached_property
    def as_settings(self) -> AmpZoneSettings:
        settings = AmpZoneSettings()
        settings.gain_left = self.gain_left if (self.gain_left is not None) else 0
        settings.gain_right = self.gain_right if (self.gain_right is not None) else 0
        settings.volume_min = self.volume_min if (self.volume_min is not None) else 0
        settings.volume_max = self.volume_max if (self.volume_max is not None) else 0
        settings.delay_left = self.delay_left
        settings.delay_right = self.delay_right
        settings.bass = self.bass if (self.bass is not None) else 0
        settings.treble = self.treble if (self.treble is not None) else 0
        settings.bridged = self.bridged if (self.bridged is not None) else 0
        settings.power_mode = self.power_mode if (self.power_mode is not None) else 0
        settings.power_level = self.power_level if (self.power_level is not None) else 0
        settings.power_timeout = self.power_timeout
        settings.eq_left = self.eq_left
        settings.eq_right = self.eq_right
        return settings

    def process(self) -> None:
        '''Update the local device cache with amplifier zone settings.'''
        bay = self.bay
        if bay is not None:
            bay.amp_settings = self.as_settings

    def __str__(self) -> str:
        return f"amp zone settings {self.bay} size {len(self.payload)}: {str(self.as_settings)}"