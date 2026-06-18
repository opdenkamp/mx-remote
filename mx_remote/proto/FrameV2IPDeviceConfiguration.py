######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for V2IP device configuration (stream addresses, scaling, options).'''

from functools import cached_property
from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Uid import MxrDeviceUid
from ..Interface import DeviceV2IPDetails, DeviceV2IPScalingSettings, DeviceV2IPSink, V2IPAudioFormat, V2IPStreamSource
from .V2IPConfig import V2IPStreamSourceImpl, parse_v2ip_av_source

# v2ip_device_config_update wire layout (little-endian, ALIGN(8) per inner struct):
#   0..16    uid (mxr_uid)
#   16..40   v2ip_av_source source (3 × v2ip_stream_source)
#   40..48   options (u8 tx_rate + 3 reserved + 4 pad)
#   48..56   v2ip_stream_source audio_return (arc)
#   56..64   mxr_scaling_config (u16 mode + u16 refresh + u8 flags + 3 pad)
#   64..88   mxr_v2ip_tiling_config (mxr_uid + 4 × u16)
# v2ip_device_config_update_options trailer (optional, MXR protocol >= 0x26):
#   88..112  v2ip_av_source sink (zero when no active route)
#   112..120 v2ip_audio_format sink_audio_fmt
_BASE_SIZE          = 88
_OPTIONS_SIZE       = 32
_WITH_OPTIONS_SIZE  = _BASE_SIZE + _OPTIONS_SIZE
_SINK_OFFSET        = _BASE_SIZE
_SINK_AUDIO_OFFSET  = _BASE_SIZE + 24

class V2IPDeviceOptions:
    '''Parsed V2IP device options (TX rate, etc.).'''
    def __init__(self, data:bytes) -> None:
        self._tx_rate = int.from_bytes(data[0:1], "little")

    @property
    def tx_rate(self) -> int:
        return self._tx_rate

    def __str__(self) -> str:
        return f"tx rate: {self.tx_rate * 10}Mb/s"

class V2IPScalingSettingsImpl(DeviceV2IPScalingSettings):
    '''Concrete implementation of V2IP output scaling settings.'''
    def __init__(self, data:bytes) -> None:
        self._mode = int.from_bytes(data[0:2], 'little')
        self._refresh = (int(data[3]) << 8) | int(data[2])
        self._flags = data[4]

    @property
    def mode(self) -> int:
        return self._mode

    @property
    def refresh(self) -> int:
        return self._refresh

    @property
    def flags(self) -> int:
        return self._flags

class FrameV2IPDeviceConfiguration(FrameBase):
    '''V2IP device configuration with stream addresses and scaling settings.'''
    def __init__(self, header:FrameHeader, timestamp:float):
        super().__init__(header=header, timestamp=timestamp)
        if (self.payload is None) or (len(self.payload) < 61):
            raise Exception("invalid v2ip configuration")
        self.video = V2IPStreamSourceImpl("video", self.payload[16:22])
        self.audio = V2IPStreamSourceImpl("audio", self.payload[24:30])
        self.anc = V2IPStreamSourceImpl("anc", self.payload[32:38])
        self.options = V2IPDeviceOptions(self.payload[40:44])
        self.arc = V2IPStreamSourceImpl("arc", self.payload[48:54])
        self.scaling = V2IPScalingSettingsImpl(self.payload[56:61])

    @property
    def target_uid(self) -> MxrDeviceUid|None:
        return self.payload_uuid(idx=0)

    @property
    def target_self(self) -> bool:
        return (self.remote_id == self.target_uid)

    @cached_property
    def details(self) -> DeviceV2IPDetails:
        return DeviceV2IPDetails(video=self.video, audio=self.audio, anc=self.anc, arc=self.arc, tx_rate=self.options.tx_rate, scaling=self.scaling)

    @cached_property
    def sink(self) -> DeviceV2IPSink|None:
        '''Sink-side state appended by peers running MXR protocol >= 0x26; None on older senders.'''
        if (self.payload is None) or (len(self.payload) < _WITH_OPTIONS_SIZE):
            return None
        return DeviceV2IPSink(
            addresses=parse_v2ip_av_source(self.payload, _SINK_OFFSET),
            audio_fmt=V2IPAudioFormat.from_bytes(self.payload[_SINK_AUDIO_OFFSET:_SINK_AUDIO_OFFSET + 8]),
        )

    def process(self) -> None:
        '''Update the local device cache with V2IP configuration details.'''
        if ((dev := self.remote_device) is None):
            return
        dev.on_mxr_update(self.details)
        if ((sink := self.sink) is not None):
            dev.on_mxr_update(sink)

    def __str__(self) -> str:
        sink_str = f" sink=[{self.sink}]" if (self.sink is not None) else ""
        return f"V2IP device configuration self={self.target_self} {self.video} {self.audio} {self.anc} {self.arc} options={self.options}{sink_str}"