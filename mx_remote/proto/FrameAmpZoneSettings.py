##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import DeviceBase, BayBase, AmpZoneSettings
from ..Uid import MxrDeviceUid
import logging

_LOGGER = logging.getLogger(__name__)

class FrameAmpZoneSettings(FrameBase):
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    @property
    def target_device(self) -> DeviceBase:
        if self.target_uid.empty:
            return self.mxr.get_by_uid(self.header.remote_id)
        return self.mxr.get_by_uid(self.target_uid)

    @property
    def target_uid(self) -> MxrDeviceUid:
        return MxrDeviceUid(self.payload[0:16])

    @property
    def zone(self) -> int:
        return int.from_bytes(self.payload[16:17], "little")

    @property
    def bay(self) -> BayBase|None:
        target_device = self.target_device
        if target_device is None:
            _LOGGER.warning(f"amp zone settings no target uid = {self.target_uid}")
            return None
        return target_device.get_by_portnum(self.zone)

    @property
    def gain_left(self) -> int:
        return self.payload[18]

    @property
    def gain_right(self) -> int:
        return self.payload[19]

    @property
    def volume_min(self) -> int:
        return self.payload[20]

    @property
    def volume_max(self) -> int:
        return self.payload[21]

    @property
    def delay_left(self) -> int:
        return int.from_bytes(self.payload[22:26], "little")

    @property
    def delay_right(self) -> int:
        return int.from_bytes(self.payload[26:30], "little")

    @property
    def bass(self) -> int:
        return self.payload[30]

    @property
    def treble(self) -> int:
        return self.payload[31]

    @property
    def bridged(self) -> int:
        return self.payload[32]

    @property
    def power_mode(self) -> int:
        return self.payload[33]

    @property
    def power_level(self) -> int:
        return self.payload[34]

    @property
    def power_timeout(self) -> int:
        return int.from_bytes(self.payload[35:39], "little")

    @property
    def eq_left(self) -> list[int]:
        return [int(x) for x in self.payload[39:44]]

    @property
    def eq_right(self) -> list[int]:
        return [int(x) for x in self.payload[44:49]]

    def as_settings(self) -> AmpZoneSettings:
        settings = AmpZoneSettings()
        settings.gain_left = self.gain_left
        settings.gain_right = self.gain_right
        settings.volume_min = self.volume_min
        settings.volume_max = self.volume_max
        settings.delay_left = self.delay_left
        settings.delay_right = self.delay_right
        settings.bass = self.bass
        settings.treble = self.treble
        settings.bridged = self.bridged
        settings.power_mode = self.power_mode
        settings.power_level = self.power_level
        settings.power_timeout = self.power_timeout
        settings.eq_left = self.eq_left
        settings.eq_right = self.eq_right
        return settings

    def process(self):
        # update the local cache
        bay = self.bay
        if bay is not None:
            bay.amp_settings = self.as_settings()

    def __str__(self) -> str:
        return f"amp zone settings {self.bay} size {len(self.payload)}: volume_range={self.volume_min}-{self.volume_max} bridged={self.bridged} power={self.power_mode} level={self.power_level} timeout={self.power_timeout} delay={self.delay_left}/{self.delay_right} gain={self.gain_left}/{self.gain_right} bass={self.bass} treble={self.treble} eq_left={self.eq_left} eq_right={self.eq_right}"