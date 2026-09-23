######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for V2IP device configuration (stream addresses, scaling, options).'''

from functools import cached_property
from typing import Any
from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Uid import MxrDeviceUid
from ..Interface import (DeviceBase, DeviceRegistry, DeviceV2IPDetails, DeviceV2IPScalingSettings,
                         DeviceV2IPSink, V2IPAudioFormat, V2IPDscpConfig, V2IPStreamSource)
from .Constants import (V2IPFpgaFeature, MXR_SCALING_FLAG_AUTO_SCALING, MXR_SCALING_FLAG_MODE_VALID,
                        MXR_SCALING_FLAG_OPTIONS_VALID, MXR_SCALING_FLAG_OPTIONS2_VALID,
                        MXR_SCALING_OPTIONS2_SETTINGS, MxrSignalType, v2ip_dscp_value,
                        v2ip_rate_valid)
from .V2IPConfig import V2IPStreamSourceImpl, parse_v2ip_av_source

# v2ip_device_config_update wire layout (little-endian, ALIGN(8) per inner struct):
#     0..16   uid (mxr_uid)
#    16..40   v2ip_av_source source (3 x v2ip_stream_source)
#    40..48   options: u8 tx_rate, u8 dscp_video, u8 dscp_audio, u8 dscp_anc, 4 pad
#    48..56   v2ip_stream_source audio_return (arc)
#    56..64   mxr_scaling_config: u16 mode, u16 refresh, u8 flags, 3 pad
#    64..88   mxr_v2ip_tiling_config: mxr_uid, 4 x u16
# v2ip_device_config_update_options trailer:
#    88..112  v2ip_av_source sink, zero when no route is active
#   112..120  v2ip_audio_format sink_audio_fmt
#   120..128  u64 video processor feature mask
#
# Each of those blocks was appended behind what came before it, leaving every
# offset ahead of it where it was, so the length is what says whether one is
# there and no stamp separates the forms.
#
# Every field carries its own validity marker and is applied only behind it,
# because a controller writing one field leaves the rest zeroed:
#
#   addresses   multicast with a non-zero port, video and anc both;
#               audio is optional and rides along
#   tx_rate     inside 5..100
#   dscp        per byte, MXR_V2IP_DSCP_SET
#   scaling     MXR_SCALING_FLAG_MODE_VALID covers mode and refresh,
#               MXR_SCALING_FLAG_OPTIONS_VALID auto-scaling, and
#               MXR_SCALING_FLAG_OPTIONS2_VALID match-source and skip-420
#   tiling      a non-zero uid; every real window carries one, so an all-zero
#               block means 'not carried' while a stamped uid with zero
#               geometry is a real clear
#
# DeviceV2IPDetails.merge() carries the unmarked fields forward. Replacing the
# cache wholesale reports a peer's addresses as 0.0.0.0 the moment a controller
# writes anything else. The sink trailer is the exception: present or absent by
# length, with no marker, and taken only from a device describing itself.
#
# Trust the scaling block only from a peer whose hello carries
# MXR_FEATURE_CONFIG_INITIALISED. Without it the sender may have built those
# flags on uninitialised stack, making MODE_VALID and the mode and refresh
# behind it meaningless and AUTO_SCALING spurious, and nothing within a frame
# distinguishes that from a real config. The firmware version cannot substitute
# for the bit: release builds use low majors while development builds use major
# 10 and above, so a numeric compare orders the two families wrongly.
#
# Nothing here caches tiling. Test the uid if that changes, or a controller
# write will wipe every sink's cached wall window.
_CONFIG_BASE_SIZE   = 64
'''The configuration as it was before the tiling window was appended to it,
which is the shortest whole one any sender emits. Every field ahead of the
window sits at the same offset in both forms, so a sender of this one is decoded
in full rather than refused: it is a complete configuration, just an older one.

Shorter than this is a frame no device acts on, and the fields it does carry are
not worth holding a configuration nothing else believes in.'''

_BASE_SIZE          = 88
_OPTIONS_SIZE       = 32
_WITH_OPTIONS_SIZE  = _BASE_SIZE + _OPTIONS_SIZE
_SINK_OFFSET        = _BASE_SIZE
_SINK_AUDIO_OFFSET  = _BASE_SIZE + 24
_CODEC_OFFSET       = _WITH_OPTIONS_SIZE
_CODEC_SIZE         = 8

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
    # Bits 2 and 3 have no meaning. A sender without
    # MXR_FEATURE_CONFIG_INITIALISED builds this byte on uninitialised stack, so
    # mask at decode rather than where the value is used: a first frame has
    # nothing to merge against and would otherwise cache the noise whole.
    _DEFINED_FLAGS = (MXR_SCALING_FLAG_MODE_VALID
                      | MXR_SCALING_FLAG_OPTIONS_VALID
                      | MXR_SCALING_FLAG_OPTIONS2_VALID
                      | MXR_SCALING_OPTIONS2_SETTINGS
                      | MXR_SCALING_FLAG_AUTO_SCALING)

    def __init__(self, data:bytes, initialised:bool) -> None:
        '''Read the block, keeping the bits this sender can be believed about.

        The second options group is dropped from a sender that does not announce
        MXR_FEATURE_CONFIG_INITIALISED. No firmware carries those options without
        also making that announcement, so masking them can discard nothing real,
        while reading them would invent a capability out of whatever the stack
        held.

        The older bits are not that case and are kept: a sender without the
        announcement can still have a genuine mode configured, and dropping
        those would discard the only reading of such a device anyone has.
        '''
        self._mode = int.from_bytes(data[0:2], 'little')
        self._refresh = (int(data[3]) << 8) | int(data[2])
        believable = V2IPScalingSettingsImpl._DEFINED_FLAGS
        if not initialised:
            believable &= ~(MXR_SCALING_FLAG_OPTIONS2_VALID | MXR_SCALING_OPTIONS2_SETTINGS)
        self._flags = (data[4] & believable)

    @property
    def mode(self) -> int:
        return self._mode

    @property
    def refresh(self) -> int:
        return self._refresh

    @property
    def flags(self) -> int:
        return self._flags

_OPCODE = 0x3C

_RATE_UNSET = 0xFF
'''The tx_rate a frame that is not setting a rate carries.

The field's valid range ends at V2IP_SOURCE_RATE_MAX, and a receiver drops an
out-of-range rate and keeps the one it had. A plain zero would ask for a rate of
zero.'''

class FrameV2IPDeviceConfiguration(FrameBase):
    '''V2IP device configuration with stream addresses and scaling settings.'''
    def __init__(self, header:FrameHeader, timestamp:float):
        super().__init__(header=header, timestamp=timestamp)
        if (self.payload is None) or (len(self.payload) < _CONFIG_BASE_SIZE):
            raise Exception("invalid v2ip configuration")
        self.video = V2IPStreamSourceImpl("video", self.payload[16:22])
        self.audio = V2IPStreamSourceImpl("audio", self.payload[24:30])
        self.anc = V2IPStreamSourceImpl("anc", self.payload[32:38])
        self.options = V2IPDeviceOptions(self.payload[40:44])
        self.arc = V2IPStreamSourceImpl("arc", self.payload[48:54])
        # The mask is the sender's own standing, not the subject's: it says
        # whether the bytes in front of us were built over an initialised block.
        sender = self.remote_device
        self.scaling = V2IPScalingSettingsImpl(self.payload[56:61],
                                               initialised=((sender is not None)
                                                            and sender.config_initialised))

    @staticmethod
    def construct_scaling(mxr:DeviceRegistry, target:Any, target_uid:MxrDeviceUid,
                          mode:MxrSignalType, refresh:int, flags:int) -> FrameBase|None:
        '''Build the 0x3C write that moves one sink's scaling block and nothing else.

        88 bytes, which is both the receiver's minimum and the whole of
        v2ip_device_config_update: uid 0..16, source 16..40, the options word at
        40, audio return 48..56, scaling 56..64, tiling 64..88.

        **88 rather than the 120-byte form.** The longer form appends a sink
        block, and a receiver copies that block into its record for the target
        with no validity test of its own - unlike the source, rate, marking,
        scaling and tiling fields, which each sit behind one. This frame is a
        broadcast, so every device on the network runs that copy, not just the
        addressee: sending the long form with the block zeroed would replace the
        whole network's idea of where the target's sink is subscribed, as a side
        effect of setting one scaling flag. At 88 the block is absent rather
        than zeroed and nothing reads it.

        **The source block at 16..40 must stay zeroed**, and does. A receiver
        hands this frame's addresses to its encoder unconditionally, on every
        frame it applies rather than only on the ones that carry addresses; what
        stops a scaling write from repointing the encoder is that the call
        refuses a video address which is not multicast. Zero is not multicast.
        Anything that is, written here, would move a transceiver's stream.

        Which halves of the scaling block a receiver reads is chosen by the
        validity bits in flags, not by this layout: the mode and refresh are
        read behind MXR_SCALING_FLAG_MODE_VALID and the options behind
        MXR_SCALING_FLAG_OPTIONS_VALID, so a write that carries neither bit
        lands as a no-op rather than as a request to zero the settings.
        '''
        payload = bytearray(target_uid.byte_value)
        if (len(payload) != 16):
            raise ValueError(f"invalid uid length: {len(payload)}")
        # source: three stream slots, left zeroed so the encoder keeps its own.
        payload += bytes(40 - len(payload))
        payload.append(_RATE_UNSET)
        # Three dscp bytes with no MXR_V2IP_DSCP_SET bit, so no marking is
        # applied, then the padding that aligns the audio-return slot, then the
        # audio return itself, zeroed, which reads as carrying no address.
        payload += bytes(56 - len(payload))
        payload += mode.byte_value
        payload += refresh.to_bytes(2, 'little')
        payload.append(flags & 0xFF)
        # The scaling struct is 8-aligned, so its five bytes of fields are
        # followed by three of padding; then the tiling window, whose zero uid
        # is what says no window is carried.
        payload += bytes(_BASE_SIZE - len(payload))
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=_OPCODE, payload=bytes(payload))

    @property
    def target_uid(self) -> MxrDeviceUid|None:
        return self.payload_uuid(idx=0)

    @property
    def target_self(self) -> bool:
        return (self.remote_id == self.target_uid)

    @cached_property
    def subject_device(self) -> DeviceBase|None:
        '''The device this configuration is about, None when nothing would act on it.

        The payload names its subject in the first sixteen bytes, and that is
        what decides whose configuration this is - not who sent it. Equal to the
        sender it is a device describing itself, which is what almost every one
        of these frames is. Different, it is a write for the device it names,
        and a receiver takes one only from a sender it treats as management.
        Anything else is dropped rather than filed against the sender, because a
        frame the network ignores must not move a record here.
        '''
        if ((subject := self.target_uid) is None):
            return None
        if (subject == self.remote_id):
            return self.remote_device
        # An unknown subject is dropped, as it is on a device: there is no
        # record to move, and inventing one from a third party's description
        # would create a device nothing has been heard from.
        if ((device := self.mxr.get_by_uid(subject)) is None):
            return None
        sender = self.remote_device
        if ((sender is not None) and sender.is_management):
            return device
        # Or the subject naming this sender as its mesh controller. Asked of the
        # subject rather than the sender because it closes the window where a
        # controller has been promoted but has no bays mapped yet, and so
        # announces neither bit while still being the controller its mesh obeys.
        #
        # A subject that has named no controller contributes nothing here rather
        # than refusing: not knowing who a device follows is not knowing that it
        # follows nobody, and a client that has just started knows nothing about
        # anyone for as long as a broadcast period.
        if (device.mesh_master_uid == self.remote_id):
            return device
        return None

    @cached_property
    def details(self) -> DeviceV2IPDetails:
        return DeviceV2IPDetails(video=self.video, audio=self.audio, anc=self.anc, arc=self.arc, tx_rate=self.options.tx_rate, scaling=self.scaling, dscp=self.options.dscp)

    @cached_property
    def video_processor_features(self) -> V2IPFpgaFeature|None:
        '''What the subject's video processor supports, None when nothing is known.

        Read only from a frame a device sent about itself. A device leaves the
        word zero on one it sends to configure someone else, so a third party's
        frame says nothing about the subject's processor - and a client that did
        fill the field in could otherwise redefine a device's capabilities from
        across the network.

        An empty mask is nothing known rather than a device that supports
        nothing. The word is zero until the processor answers after boot, and an
        older processor answers with none of the optional commands; the two are
        identical on the wire, so neither can be a capability set.
        '''
        if (self.payload is None) or (len(self.payload) < (_CODEC_OFFSET + _CODEC_SIZE)):
            return None
        if not self.target_self:
            return None
        mask = int.from_bytes(self.payload[_CODEC_OFFSET:(_CODEC_OFFSET + _CODEC_SIZE)], 'little')
        if (mask == 0):
            return None
        return V2IPFpgaFeature(mask)

    @cached_property
    def sink(self) -> DeviceV2IPSink|None:
        '''Sink-side state a longer frame appends to the configuration; None when
        the frame stops in front of it.

        Read only from a frame a device sent about itself. A controller writing
        another device's configuration sends the block zeroed, because it has
        nothing to say about that sink's subscription, and caching those zeros
        would clear the route on every unrelated write.
        '''
        if (self.payload is None) or (len(self.payload) < _WITH_OPTIONS_SIZE):
            return None
        if not self.target_self:
            return None
        return DeviceV2IPSink(
            addresses=parse_v2ip_av_source(self.payload, _SINK_OFFSET),
            audio_fmt=V2IPAudioFormat.from_bytes(self.payload[_SINK_AUDIO_OFFSET:_SINK_AUDIO_OFFSET + 8]),
        )

    def process(self) -> None:
        '''Update the cache of the device this configuration names, not of its sender.'''
        if ((dev := self.subject_device) is None):
            return
        dev.on_mxr_update(self.details)
        if ((sink := self.sink) is not None):
            dev.on_mxr_update(sink)
        if ((features := self.video_processor_features) is not None):
            dev.on_mxr_update(features)

    def __str__(self) -> str:
        sink_str = f" sink=[{self.sink}]" if (self.sink is not None) else ""
        fpga_str = f" fpga={self.video_processor_features}" if (self.video_processor_features is not None) else ""
        return f"V2IP device configuration self={self.target_self} {self.video} {self.audio} {self.anc} {self.arc} options={self.options}{sink_str}{fpga_str}"