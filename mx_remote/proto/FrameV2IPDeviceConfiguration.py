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
from ..Interface import DeviceV2IPDetails, DeviceV2IPScalingSettings, DeviceV2IPSink, V2IPAudioFormat, V2IPDscpConfig, V2IPStreamSource
from .Constants import v2ip_dscp_value, v2ip_rate_valid
from .V2IPConfig import V2IPStreamSourceImpl, parse_v2ip_av_source

# v2ip_device_config_update wire layout (little-endian, ALIGN(8) per inner struct):
#   0..16    uid (mxr_uid)
#   16..40   v2ip_av_source source (3 × v2ip_stream_source)
#   40..48   options (u8 tx_rate + u8 dscp_video + u8 dscp_audio + u8 dscp_anc + 4 pad)
#   48..56   v2ip_stream_source audio_return (arc)
#   56..64   mxr_scaling_config (u16 mode + u16 refresh + u8 flags + 3 pad)
#   64..88   mxr_v2ip_tiling_config (mxr_uid + 4 × u16) - not parsed here, see below
#
# Every field here carries its own validity marker, because a controller writing
# one of them leaves the rest zeroed (mxr_pbuf_alloc zeroes the payload), and the
# firmware applies each only behind its own marker. An address is valid only when
# it is multicast with a non-zero port (video and anc both, audio rides along),
# tx_rate only inside 5..100, a dscp byte only with MXR_V2IP_DSCP_SET, scaling only
# under its MXR_SCALING_FLAG_*_VALID flags - and the mode/refresh pair and the
# options nibble are separately valid. DeviceV2IPDetails.merge() mirrors all of it;
# a receiver that replaces its cache wholesale reports a peer's addresses as
# 0.0.0.0 the moment a controller writes anything else.
#
# The sink trailer is the one part that is simply present or absent, by length.
#
# One caveat the markers cannot cover. A receiver-capable unit running firmware
# that predates the scaling-config initialisation fix builds mxr_scaling_config
# on the stack without zeroing it and only ever |= flags onto it, so:
#   - MODE_VALID can be set by leftover stack, and mode/refresh behind it are
#     then uninitialised memory - assigned only when a format really is
#     configured. Nothing in the frame distinguishes that from a real config, so
#     this is an exposure to note rather than one a client can close.
#   - AUTO_SCALING is only ever OR'd, never cleared, so it too can be spuriously
#     set. Reading bit 7 specifically is the best available reading, not a
#     correct one; it confines the noise to one bit instead of five.
#
# Nothing on the wire distinguishes a fixed sender from an unfixed one. The
# payload shape did not change, so MXR_PROTOCOL_VERSION stayed at 0x28 and no
# feature bit was added - confirmed, not assumed.
#
# Do not reach for the firmware version in the hello as a gate. Release builds
# use low majors (4.4.x) and development builds use major >= 10, one minor per
# developer - a parallel numbering, not a later one. A numeric compare puts
# 10.12.31 above every release that will ever carry the fix and 4.4.87 below a
# dev build predating it by months, so "is this at least the threshold" is not a
# well-formed question across the two families. Getting it right would mean
# judging dev builds by build date and release builds by version, which is a
# worse bug waiting to happen than the exposure it guards.
#
# The tiling block has no flag of its own, but its uid serves as one: both paths
# that produce a real window stamp it (v2ip_fpga.c:1445 for a remote sink, 1470
# for a local one), while a controller write passes tiling = NULL and leaves the
# whole block zeroed, uid included. So it is the all-zero *block* that means 'not
# carried', not an all-zero window:
#   uid zero                    -> not carried; keep whatever is cached
#   uid set, geometry zero      -> a real clear (the alignment check at 1457 is
#                                  skipped for 0x0, which is how a window clears)
#   uid set, geometry non-zero  -> a real window
# Nothing caches tiling on this side today - 0x40 V2IP_TILING's process() is a
# no-op and this frame does not parse the block - but if that changes, test the
# uid, or a controller write will wipe the cached wall window of every sink it
# touches until the next periodic broadcast heals it.
# v2ip_device_config_update_options trailer (optional, MXR protocol >= 0x26):
#   88..112  v2ip_av_source sink (zero when no active route)
#   112..120 v2ip_audio_format sink_audio_fmt
_BASE_SIZE          = 88
_OPTIONS_SIZE       = 32
_WITH_OPTIONS_SIZE  = _BASE_SIZE + _OPTIONS_SIZE
_SINK_OFFSET        = _BASE_SIZE
_SINK_AUDIO_OFFSET  = _BASE_SIZE + 24

class V2IPDeviceOptions:
    '''Parsed V2IP device options (TX rate and per-stream DSCP marking).'''
    def __init__(self, data:bytes) -> None:
        self._raw_tx_rate = int.from_bytes(data[0:1], "little")
        self._dscp = V2IPDscpConfig(
            video=v2ip_dscp_value(data[1] if (len(data) > 1) else None),
            audio=v2ip_dscp_value(data[2] if (len(data) > 2) else None),
            anc=v2ip_dscp_value(data[3] if (len(data) > 3) else None),
        )

    @property
    def raw_tx_rate(self) -> int:
        '''TX rate byte exactly as it arrived, valid range or not.'''
        return self._raw_tx_rate

    @property
    def tx_rate(self) -> int|None:
        '''TX rate in units of 10Mb/s, or None when the sender offered no rate.

        A rate-only write carries the rate on its own; every other controller
        write puts a value outside 5..100 here, which firmware drops as invalid
        so that address-only and scaling writes leave the peer's rate alone.'''
        return self._raw_tx_rate if v2ip_rate_valid(self._raw_tx_rate) else None

    @property
    def dscp(self) -> V2IPDscpConfig:
        '''Per-stream DSCP marking; each stream reads None when its byte is unset.'''
        return self._dscp

    def __str__(self) -> str:
        rate = f"{self._raw_tx_rate * 10}Mb/s" if (self.tx_rate is not None) else "not set"
        return f"tx rate: {rate}, dscp: {self._dscp}"

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
        return DeviceV2IPDetails(video=self.video, audio=self.audio, anc=self.anc, arc=self.arc, tx_rate=self.options.tx_rate, scaling=self.scaling, dscp=self.options.dscp)

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