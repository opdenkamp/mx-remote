######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame changing settings on every OneIP device of a mesh.'''

from functools import cached_property
from .FrameBase import FrameBase
from .FrameV2IPDeviceConfiguration import (carries_settings_block, own_settings_block, parse_settings_block,
                                           settings_block)
from ..Interface import DeviceRegistry, OneIPDeviceSettings

# Payload: the 48-byte device settings block, as it sits at 128 in a
# V2IP_DEVICE_CFG, and behind it at 48 the 8-byte block of their own the
# settings in ONEIP_DEVICE_SETTINGS_BLOCK travel in, when they carry one.
#
# Broadcast, and each device applies the settings it has and ignores the rest.
# Nothing is cached from it: each device that applies a change reports its
# settings itself, and a device without one of the settings reports nothing.
_SETTINGS_MIN = 16
_OWN_BLOCK_AT = 48

class FrameV2IPSettingsAll(FrameBase):
    '''Settings for every OneIP device of the mesh.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, settings:OneIPDeviceSettings) -> FrameBase|None:
        '''Build the broadcast. The caller has refused what every device would ignore.'''
        payload = settings_block(settings)
        if carries_settings_block(settings):
            payload += own_settings_block(settings)
        return FrameBase.construct_base(mxr=mxr, opcode=0x4C, payload=payload)

    @cached_property
    def settings(self) -> OneIPDeviceSettings|None:
        '''The settings carried, None for a frame too short to hold the block.'''
        if (self.payload is None) or (len(self.payload) < _SETTINGS_MIN):
            return None
        return parse_settings_block(self.payload, self.payload[_OWN_BLOCK_AT:])

    def __str__(self) -> str:
        return f"OneIP settings for every device: {self.settings}"
