##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Protocol frame for amplifier Dolby audio settings.'''

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import DeviceBase, AmpDolbySettings
from ..Uid import MxrDeviceUid
import logging

_LOGGER = logging.getLogger(__name__)

class FrameAmpDolbySettings(FrameBase):
    '''Amplifier Dolby audio processing settings.'''
    @property
    def target_device(self) -> DeviceBase|None:
        '''Target device for the Dolby settings.'''
        if (self.target_uid is None) or self.target_uid.empty:
            return self.mxr.get_by_uid(self.header.remote_id)
        return self.mxr.get_by_uid(self.target_uid)

    @property
    def target_uid(self) -> MxrDeviceUid|None:
        '''UID of the target device.'''
        return self.payload_uuid(0)

    @property
    def dolby_mode(self) -> int|None:
        '''Active Dolby processing mode.'''
        return self.payload_u8(16)

    @property
    def pcm_upmix(self) -> bool|None:
        '''Whether PCM upmix is enabled.'''
        payload = self.payload_u8(17)
        if payload is None:
            return None
        return ((payload & 0x1) != 0)

    @property
    def dolby_detected(self) -> bool|None:
        '''Whether a Dolby signal is detected.'''
        payload = self.payload_u8(17)
        if payload is None:
            return None
        return ((payload & 0x2) != 0)

    @property
    def pcm_upmix_active(self) -> bool|None:
        '''Whether PCM upmix is currently active.'''
        payload = self.payload_u8(17)
        if payload is None:
            return None
        return ((payload & 0x4) != 0)

    def as_settings(self) -> AmpDolbySettings:
        '''Convert parsed frame data to an AmpDolbySettings object.'''
        settings = AmpDolbySettings()
        settings.mode = self.dolby_mode if (self.dolby_mode is not None) else 0
        settings.pcm_upmix = self.pcm_upmix if (self.pcm_upmix is not None) else False
        settings.pcm_upmix_active = self.pcm_upmix_active if (self.pcm_upmix_active is not None) else False
        settings.dolby_detected = self.dolby_detected if (self.dolby_detected is not None) else False
        return settings

    def process(self) -> None:
        '''Update the local device cache with Dolby settings.'''
        device = self.target_device
        if device is not None:
            device.dolby_settings = self.as_settings()

    def __str__(self) -> str:
        return f"amp dolby settings {self.target_device}: mode={self.dolby_mode} upmix={self.pcm_upmix} dolby detected={self.dolby_detected} upmix active={self.pcm_upmix_active}"
