##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import DeviceBase, AmpDolbySettings
from ..Uid import MxrDeviceUid
import logging

_LOGGER = logging.getLogger(__name__)

class FrameAmpDolbySettings(FrameBase):
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
    def dolby_mode(self) -> int:
        return self.payload[16]

    @property
    def pcm_upmix(self) -> bool:
        return (self.payload[17] != 0)

    def as_settings(self) -> AmpDolbySettings:
        settings = AmpDolbySettings()
        settings.mode = self.dolby_mode
        settings.pcm_upmix = self.pcm_upmix
        return settings

    def process(self):
        # update the local cache
        device = self.target_device
        if device is not None:
            device.dolby_settings = self.as_settings()

    def __str__(self) -> str:
        return f"amp dolby settings {self.target_device}: mode={self.dolby_mode} upmix={self.pcm_upmix}"
