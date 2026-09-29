######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame changing settings on every V2IP device of a mesh.'''

from functools import cached_property
from .FrameBase import FrameBase
from .FrameV2IPDeviceConfiguration import parse_settings_block, settings_block
from ..Interface import DeviceRegistry, V2IPDeviceSettings

# Payload: the 48-byte device settings block alone, as it sits at 128 in a
# V2IP_DEVICE_CFG.
#
# Broadcast, and each device applies the settings it has and ignores the rest.
# Nothing is cached from it: each device that applies a change reports its
# settings itself, and a device without one of the settings reports nothing.
_SETTINGS_MIN = 16

class FrameV2IPSettingsAll(FrameBase):
    '''Settings for every V2IP device of the mesh.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, settings:V2IPDeviceSettings) -> FrameBase|None:
        '''Build the broadcast. The caller has refused what every device would ignore.'''
        return FrameBase.construct_base(mxr=mxr, opcode=0x4C, payload=settings_block(settings))

    @cached_property
    def settings(self) -> V2IPDeviceSettings|None:
        '''The settings carried, None for a frame too short to hold the block.'''
        if (self.payload is None) or (len(self.payload) < _SETTINGS_MIN):
            return None
        return parse_settings_block(self.payload)

    def __str__(self) -> str:
        return f"V2IP settings for every device: {self.settings}"
