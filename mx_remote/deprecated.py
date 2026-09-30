######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################

"""
The public names this package had before it called the product OneIP.

V2IP is the firmware's internal name for OneIP, and FPGA its name for the video
processor. Up to 5.11 the public API used both; every such name is now spelled
OneIP and VideoProcessor, and the old spelling still works but raises a
DeprecationWarning. They will be removed in a future major release.

A module-level name resolves through the module's __getattr__, so
``from mx_remote import *`` does not bring the old names in.
"""

import warnings
from typing import Any

def oneip_name(old:str) -> str:
    '''The public spelling of an old V2IP or FPGA name.'''
    if (old.upper() == old):
        return old.replace('V2IP', 'ONEIP').replace('FPGA', 'VIDEO_PROCESSOR')
    return old.replace('V2IP', 'OneIP').replace('v2ip', 'oneip').replace('Fpga', 'VideoProcessor')

RENAMED_NAMES:frozenset[str] = frozenset((
    'DeviceV2IPDetails', 'DeviceV2IPScalingSettings', 'DeviceV2IPSink',
    'MXR_V2IP_DSCP_SET', 'V2IPAudioFormat', 'V2IPDeviceSetting',
    'V2IPDeviceSettings', 'V2IPDeviceStats', 'V2IPDscpConfig',
    'V2IPFpgaFeature', 'V2IPOutputMode', 'V2IPPowerSaveSchedule',
    'V2IPScalingSettings', 'V2IPStreamSource', 'V2IPStreamSources',
    'V2IPStreamSourcesList', 'V2IP_AUDIO_DEFAULT_CHANNELS',
    'V2IP_AUDIO_DEFAULT_SAMPLE_RATE', 'V2IP_AUDIO_MAX_CHANNELS',
    'V2IP_AUDIO_MIN_CHANNELS', 'V2IP_DEVICE_SETTINGS_REPORTED_ONLY',
    'V2IP_DEVICE_SETTING_SWITCHES', 'V2IP_DSCP_DEFAULT', 'V2IP_DSCP_MAX',
    'V2IP_IR_PROFILE_MAX', 'V2IP_IR_PROFILE_NOT_SET', 'V2IP_MINUTES_PER_DAY',
    'V2IP_SCALING_REFRESH_MAX', 'V2IP_SCALING_REFRESH_MIN',
    'V2IP_SOURCE_RATE_MAX', 'V2IP_SOURCE_RATE_MIN', 'v2ip_av_source_valid',
    'v2ip_dscp_value', 'v2ip_rate_valid', 'v2ip_stream_cleared',
    'v2ip_stream_valid',
))
"""Module-level names released with a V2IP spelling."""

def _warn(old:str, new:str) -> None:
    warnings.warn(f"{old} is deprecated, use {new}", DeprecationWarning, stacklevel=3)

def module_getattr(module:str, namespace:dict[str, Any]) -> Any:
    '''A module __getattr__ that resolves the old spelling of a name defined
    in namespace.'''
    def __getattr__(name:str) -> Any:
        if (name in RENAMED_NAMES) and ((new := oneip_name(name)) in namespace):
            _warn(name, new)
            return namespace[new]
        raise AttributeError(f"module {module!r} has no attribute {name!r}")
    return __getattr__

class _Renamed:
    '''A class member under its old name, forwarding to the new one.'''
    def __init__(self, owner:str, old:str) -> None:
        self._old = f"{owner}.{old}"
        self._new = oneip_name(old)
        self.__doc__ = f"Deprecated: use {self._new}."

    def __get__(self, obj:Any, objtype:Any=None) -> Any:
        if (obj is None):
            return self
        _warn(self._old, self._new)
        return getattr(obj, self._new)

    def __set__(self, obj:Any, value:Any) -> None:
        _warn(self._old, self._new)
        setattr(obj, self._new, value)

def alias_members(cls:type, *old:str) -> None:
    '''Keep the old spelling of each of cls's renamed members working.'''
    for name in old:
        setattr(cls, name, _Renamed(cls.__name__, name))
