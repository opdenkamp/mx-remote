##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################

from __future__ import annotations
import logging
from typing import Any, Callable, override
from ..proto.Constants import BayStatusMask, BayFeaturesMask, EdidProfile, RCType, RCAction, RCKey
from ..proto.BayConfig import BayConfig
from ..proto.Data import VolumeMuteStatus
from ..proto.FrameV2IPSourceSwitch import FrameV2IPSourceSwitch
from ..proto.FrameEDIDProfile import FrameEDIDProfile
from ..proto.FrameBayHide import FrameBayHide
from ..proto.FrameSetName import FrameSetName
from ..proto.FrameRCAction import FrameRCAction
from ..proto.FrameVolumeSet import FrameVolumeSet
from ..proto.FrameAmpZoneSettings import FrameAmpZoneSettings
from ..proto.FrameV2IPAudio import FrameV2IPAudio
from ..Interface import (
    BayBase,
    DeviceBase,
    BayLink,
    MxrCallbacks,
    V2IPStreamSources,
    AmpZoneSettings,
    DeviceStatus,
    SelectedBays,
    PowerStatus,
    SignalStatus,
    ConnectStatus,
    FilteredDevices,
    HiddenStatus,
    BayMirrorStatus,
    MxrDeviceUid,
    AudioEndpoint,
    AudioChangeSource,
)
from ..Uid import MxrBayUid

_LOGGER = logging.getLogger(__name__)

class Bay(BayBase):
    ARC_NONE = 'Inactive'
    ARC_HDMI = 'HDMI'
    ARC_OPTICAL = 'optical'
    ARC_ANALOG = 'analog'

    def __init__(self, dev:DeviceBase, data:BayConfig) -> None:
        self._dev = dev
        self._port_number = data.port
        self._port_name = data.bay_name
        self._user_name = None
        self._features = data.features
        self._mbay_id = None
        self._video_source = None
        self._audio_source = None
        self._power_status:PowerStatus|None = None
        self._faulty = None
        self._hidden = None
        self._poe_powered = None
        self._hdbt_connected = None
        self._signal_detected = None
        self._signal_type = None
        self._hpd_detected = None
        self._cec_detected = None
        self._arc = self.ARC_NONE
        self._audio_volume = None
        self._rc_type = None
        self._edid_profile = None
        self._decoder_disabled = None
        self._encoder_disabled = None
        self._status_mask = data.status
        self._audio_endpoint:AudioEndpoint|None = None
        self._v2ip_uid:MxrDeviceUid|None = None
        self._amp_settings:AmpZoneSettings|None = None
        self._filtered:FilteredDevices = FilteredDevices()
        self._mirror:BayMirrorStatus = BayMirrorStatus()
        self._bay_callbacks:list[Callable[[BayBase],None]] = []

    def register_callback(self, callback:Callable[[BayBase],None]) -> None:
         '''register a callback, called when the device state changed'''
         self._bay_callbacks.append(callback)

    def unregister_callback(self, callback:Callable[[BayBase],None]) -> None:
         '''unregister a callback'''
         if callback in self._bay_callbacks:
            self._bay_callbacks.remove(callback)

    def call_callbacks(self) -> None:
        for callback in self._bay_callbacks:
            callback(self)

    @property
    @override
    def rebooting(self) -> bool:
        '''True if rebooting'''
        return self.device.rebooting

    @property
    @override
    def booting(self) -> bool:
        '''True if booting'''
        return self.device.booting

    @property
    @override
    def status(self) -> DeviceStatus:
        if self.online:
            if self.rebooting:
                return DeviceStatus.REBOOTING
            if self.booting:
                return DeviceStatus.BOOTING
            if BayStatusMask.ENCODER_DISABLED in self.status_mask or BayStatusMask.DECODER_DISABLED in self.status_mask:
                return DeviceStatus.INACTIVE
            return DeviceStatus.ONLINE
        return DeviceStatus.OFFLINE

    @property
    @override
    def v2ip_source(self) -> V2IPStreamSources|None:
        return self.device.v2ip_source(self)

    @property
    @override
    def callbacks(self) -> MxrCallbacks:
        return self.device.callbacks

    @property
    @override
    def device(self) -> DeviceBase:
        # remote device
        return self._dev

    @property
    @override
    def bay_uid(self) -> MxrBayUid:
        return MxrBayUid(self.device.remote_id, self.port)

    @property
    @override
    def v2ip_uid(self) -> MxrDeviceUid|None:
        return self._v2ip_uid

    @v2ip_uid.setter
    def v2ip_uid(self, uid:MxrDeviceUid|None) -> None:
        self._v2ip_uid = uid

    @property
    @override
    def v2ip_device(self) -> DeviceBase|None:
        return self.device.registry.get_by_uid(self._v2ip_uid)

    @property
    @override
    def online(self) -> bool:
        # check whether the device to which this bay belongs is online
        return self.device.online

    @property
    @override
    def port(self) -> int:
        # port number used for mxremote operations
        return self._port_number

    @property
    @override
    def bay_name(self) -> str:
        # mbay name
        return self._port_name

    @property
    @override
    def user_name(self) -> str:
        # name set up by the user
        return self._user_name if (self._user_name is not None) \
            else self.bay_name

    @user_name.setter
    def user_name(self, val:str) -> None:
        prev = self.user_name
        self._user_name = val
        if (self.user_name != prev):
            self.callbacks.on_name_changed(self, self.user_name)
            self.call_callbacks()

    @property
    @override
    def has_default_name(self) -> bool:
        # default name set or custom name set
        return (self.user_name == self.bay_name)

    @property
    @override
    def bay_label(self) -> str:
        # bay name + user name, used for logging
        name = self.bay_name
        user_name = self.user_name
        if user_name != name:
            return "{} ({})".format(name, user_name)
        return name

    @property
    @override
    def is_local(self) -> bool:
        return not self.is_v2ip_remote

    @property
    @override
    def is_v2ip_remote(self) -> bool:
        return BayFeaturesMask.V2IP_SINK_REMOTE in self.features or BayFeaturesMask.V2IP_SOURCE_REMOTE in self.features

    @property
    @override
    def is_v2ip_source(self) -> bool:
        return BayFeaturesMask.V2IP_SOURCE_LOCAL in self.features \
            or BayFeaturesMask.V2IP_SOURCE_REMOTE in self.features

    @property
    @override
    def is_v2ip_sink(self) -> bool:
        return BayFeaturesMask.V2IP_SINK_LOCAL in self.features \
            or BayFeaturesMask.V2IP_SINK_REMOTE in self.features

    @property
    @override
    def dolby_input(self) -> str|None:
        # if dolby mode is set, the input bay that provides the audio source
        if BayFeaturesMask.DOLBY in self.features:
            # TODO fix mx_remote offset
            return 'Input {}'.format('9') #((features >> proto.MX_BAY_FEATURE_DOLBY_IN_POS) & 0xF)
        return None

    @property
    @override
    def dolby_input_bay(self) -> BayBase|None:
        db = self.dolby_input
        if db is None:
            return None
        return self.device.get_by_portname(db)

    @property
    @override
    def has_volume_control(self) -> bool:
        return BayFeaturesMask.AUDIO_ANA_OUT in self.features \
            or BayFeaturesMask.AUDIO_AMP_OUT in self.features \
            or BayFeaturesMask.AUDIO_ANA_IN in self.features \
            or BayFeaturesMask.AUDIO_DIG_IN in self.features

    @property
    @override
    def is_input(self) -> bool:
        return BayFeaturesMask.HDMI_IN in self.features \
            or BayFeaturesMask.AUDIO_DIG_IN in self.features \
            or BayFeaturesMask.AUDIO_ANA_IN in self.features \
            or self.is_v2ip_source

    @property
    @override
    def is_output(self) -> bool:
        return BayFeaturesMask.HDMI_OUT in self.features \
            or BayFeaturesMask.AUDIO_AMP_OUT in self.features \
            or BayFeaturesMask.AUDIO_DIG_OUT in self.features \
            or BayFeaturesMask.AUDIO_ANA_OUT in self.features \
            or self.is_v2ip_sink

    @property
    @override
    def mode(self) -> str:
        # bay mode used by the web api and logging
        if self.is_output:
            return 'Output'
        if self.is_input:
            return 'Input'
        return 'unknown'

    @property
    @override
    def other_mode(self) -> str:
        # bay mode used by the web api and logging
        if self.is_output:
            return 'Input'
        if self.is_input:
            return 'Output'
        return 'unknown'

    @property
    @override
    def bay(self) -> int:
        # bay number used by the web api
        return self._mbay_id if (self._mbay_id is not None) \
            else int(self.bay_name[len(self.mode)+1:])

    @bay.setter
    def bay(self, val:int) -> None:
        if self._mbay_id is None:
            self._mbay_id = val

    @property
    @override
    def available(self) -> bool:
        if self.faulty or self.hidden or not self.online:
            return False
        if self.is_hdbaset and not self.hdbt_connected:
            return False
        if self.device.is_amp:
            if self.is_output:
                return (self.bay == 0) or (self.bay >= self.device.amp_dolby_channels)
            return (self.bay > self.device.amp_dolby_channels)
        return True

    @property
    @override
    def is_hdmi(self) -> bool:
        return BayFeaturesMask.HDMI_IN in self.features \
            or BayFeaturesMask.HDMI_OUT in self.features

    @property
    @override
    def is_hdbaset(self) -> bool:
        #HDBaseT bay
        # TODO add to proto
        return self.is_hdmi and self.is_output and (self.bay < self.device.nb_hdbt)

    @property
    @override
    def is_audio(self) -> bool:
        if self.is_hdmi:
            return False
        return BayFeaturesMask.AUDIO_AMP_OUT in self.features \
            or BayFeaturesMask.AUDIO_ANA_IN in self.features \
            or BayFeaturesMask.AUDIO_ANA_OUT in self.features \
            or BayFeaturesMask.AUDIO_DIG_IN in self.features \
            or BayFeaturesMask.AUDIO_DIG_OUT in self.features

    @property
    @override
    def edid_profile(self) -> EdidProfile|None:
        if not self.is_hdmi or not self.is_input:
            return None
        return EdidProfile(self._edid_profile)

    @edid_profile.setter
    def edid_profile(self, val:int) -> None:
        if not self.is_hdmi or not self.is_input:
            return
        if ((self._edid_profile is None) or (self._edid_profile != val)):
            self._edid_profile = val
            self.callbacks.on_edid_profile_changed(self, self.edid_profile)
            self.call_callbacks()

    @property
    @override
    def rc_type(self) -> RCType|None:
        if not self.is_hdmi or not self.is_input:
            return None
        return RCType(self._rc_type)

    @rc_type.setter
    def rc_type(self, val:int) -> None:
        if not self.is_hdmi or not self.is_input:
            return
        if ((self._rc_type is None) or (self._rc_type != val)):
            self._rc_type = val
            self.callbacks.on_rc_type_changed(self, self.rc_type)
            self.call_callbacks()

    @property
    @override
    def video_source(self) -> BayBase|None:
        if not self.is_output:
            return None
        # current video source bay
        return self._video_source

    @video_source.setter
    def video_source(self, source:BayBase|None) -> None:
        # set the cached video source bay
        if not self.is_output:
            return
        if source is None:
            self._video_source = source
            return
        if (self._video_source is None) or (source != self._video_source):
            self._video_source = source
            self.callbacks.on_video_source_changed(self, source)
            self.call_callbacks()

    @property
    @override
    def available_video_sources(self) -> list[BayBase]:
        rv:list[BayBase] = []
        if (not self.is_output):
            return rv
        for _, bay in self.device.inputs.items():
            if (not bay.is_audio):
                rv.append(bay)
        return rv

    @property
    @override
    def audio_source(self) -> BayBase|None:
        if not self.is_output:
            return None
        # current audio source bay
        if self._audio_source is None:
            return self.video_source
        return self._audio_source

    @audio_source.setter
    def audio_source(self, source:BayBase|None) -> None:
        if not self.is_output:
            return
        # set the cached audio source bay
        if source is None:
            self._audio_source = source
            return
        prev = self.audio_source
        if (self._audio_source is None) or (source != self._audio_source):
            self._audio_source = source
        if (prev != self.audio_source):
            self.callbacks.on_audio_source_changed(bay=self, audio_source=self.audio_source)
            self.call_callbacks()

    @property
    @override
    def available_audio_sources(self) -> list[BayBase]:
        rv:list[BayBase] = []
        if (not self.is_output):
            return rv
        for _, bay in self.device.inputs.items():
            if (bay.audio_endpoint is not None):
                lep = bay.audio_endpoint.link(self.device.registry)
                if (lep is not None) and (lep.bay is not None):
                    rv += lep.bay.available_audio_sources
            # if self.is_v2ip_sink:
            #     rv.append(bay)
            # elif (bay.is_audio):
            #     rv.append(bay)
            rv.append(bay)
        return rv

    @property
    @override
    def audio_endpoint(self) -> AudioEndpoint|None:
        return self._audio_endpoint

    @audio_endpoint.setter
    def audio_endpoint(self, endpoint:AudioEndpoint) -> None:
        if (self._audio_endpoint is None) or (self._audio_endpoint != endpoint):
            self._audio_endpoint = endpoint
            self._audio_endpoint.bay = self
            self.call_callbacks()

    @property
    @override
    def powered_on(self) -> bool:
        # connected device powered on
        # return (self._power_status is not None) and (self._power_status == PowerStatus.ON)
        return (self._power_status == PowerStatus.ON)

    @property
    @override
    def powered_off(self) -> bool:
        # connected device powered off
        # return (self._power_status is not None) and (self._power_status == 'off')
        return (self._power_status == PowerStatus.OFF)

    @property
    @override
    def power_status(self) -> PowerStatus:
        # device power status
        if not self.available or self.powered_off:
            return PowerStatus.OFF
        if self.powered_on:
            return PowerStatus.ON
        if self.is_hdmi:
            if self.is_input:
                return PowerStatus.ON if self.signal_detected else PowerStatus.OFF
            if self.is_output and not self.hpd_detected:
                return PowerStatus.OFF
            if not self.signal_detected:
                return PowerStatus.OFF
            if self.is_hdbaset and not self.hdbt_connected:
                return PowerStatus.OFF
        elif self.is_audio:
            if self.muted:
                return PowerStatus.OFF
            return PowerStatus.ON if (self.signal_detected) else PowerStatus.OFF
        return PowerStatus.UNKNOWN

    @power_status.setter
    def power_status(self, power:PowerStatus) -> None:
        prev = self.power_status
        self._power_status = power
        if (self.power_status != prev):
            self.callbacks.on_power_changed(self, power)
            self.call_callbacks()

    @property
    @override
    def faulty(self) -> bool:
        # bay is faulty
        return (self._faulty is not None) and self._faulty

    @faulty.setter
    def faulty(self, val:bool) -> None:
        prev = self.faulty
        self._faulty = val
        if prev != self.faulty and (prev or val):
            self.callbacks.on_status_faulty_changed(self, val)
            self.call_callbacks()

    @property
    @override
    def hidden(self) -> bool:
        # bay is hidden
        return (self._hidden is not None) and self._hidden

    @hidden.setter
    def hidden(self, val:bool) -> None:
        prev = self.hidden
        self._hidden = val
        if prev != self.hidden and (prev or val):
            self.callbacks.on_status_hidden_changed(self, val)
            self.call_callbacks()

    @property
    @override
    def poe_powered(self) -> bool:
        # bay poe is powered
        return (self._poe_powered is not None) and self._poe_powered

    @poe_powered.setter
    def poe_powered(self, val:bool) -> None:
        prev = self.poe_powered
        self._poe_powered = val
        if prev != self.poe_powered and (not prev or not val):
            self.callbacks.on_status_poe_powered_changed(self, val)
            self.call_callbacks()

    @property
    @override
    def hdbt_connected(self) -> bool:
        # hdbt link up
        return (self._hdbt_connected is not None) and self._hdbt_connected

    @hdbt_connected.setter
    def hdbt_connected(self, val:bool) -> None:
        prev = self.hdbt_connected
        self._hdbt_connected = val
        if prev != self.hdbt_connected:
            self.callbacks.on_status_hdbt_connected_changed(self, val)
            self.call_callbacks()

    @property
    @override
    def signal_detected(self) -> bool:
        # video/audio signal detected
        return (self._signal_detected is not None) and self._signal_detected

    @signal_detected.setter
    def signal_detected(self, val:bool) -> None:
        prev = self.signal_detected
        self._signal_detected = val
        if prev != self.signal_detected:
            self.callbacks.on_status_signal_detected_changed(self, val)
            self.call_callbacks()

    @property
    @override
    def encoder_disabled(self) -> bool:
        # video/audio encoder disabled
        return (self._encoder_disabled is not None) and self._encoder_disabled

    @encoder_disabled.setter
    def encoder_disabled(self, val:bool) -> None:
        prev = self.encoder_disabled
        self._encoder_disabled = val
        if prev != self.decoder_disabled:
            self.callbacks.on_bay_update(self)
            self.call_callbacks()

    @property
    @override
    def decoder_disabled(self) -> bool:
        # video/audio decoder disabled
        return (self._decoder_disabled is not None) and self._decoder_disabled

    @decoder_disabled.setter
    def decoder_disabled(self, val:bool) -> None:
        prev = self._decoder_disabled
        self._decoder_disabled = val
        if prev != self.decoder_disabled:
            self.callbacks.on_bay_update(self)
            self.call_callbacks()

    @property
    @override
    def signal_type(self) -> str:
        # video/audio signal type
        return self._signal_type if (self._signal_type is not None) else 'unknown'

    @signal_type.setter
    def signal_type(self, val:str) -> None:
        prev = self.signal_type
        self._signal_type = val
        if prev != self.signal_type:
            self.callbacks.on_status_signal_type_changed(self, val)
            self.call_callbacks()

    @property
    @override
    def hpd_detected(self) -> bool:
        # hotplug detected
        return (self._hpd_detected is not None) and self._hpd_detected

    @hpd_detected.setter
    def hpd_detected(self, val:bool) -> None:
        prev = self.hpd_detected
        self._hpd_detected = val
        if prev != self.hpd_detected:
            self.callbacks.on_status_hpd_detected_changed(self, val)
            self.call_callbacks()

    @property
    def cec_detected(self) -> bool:
        # CEC capable device detected
        return (self._cec_detected is not None) and self._cec_detected

    @cec_detected.setter
    def cec_detected(self, val:bool) -> None:
        prev = self.cec_detected
        self._cec_detected = val
        if prev != self.cec_detected:
            self.callbacks.on_status_cec_detected_changed(self, val)
            self.call_callbacks()

    @property
    @override
    def mirroring(self) -> BayMirrorStatus:
        return self._mirror

    @mirroring.setter
    def mirroring(self, val:BayMirrorStatus) -> None:
        prev = self.mirroring
        self._mirror = val
        if prev != val:
            self.callbacks.on_mirror_status_changed(self, val)
            self.call_callbacks()

    @property
    @override
    def filtered(self) -> FilteredDevices:
        return self._filtered

    @filtered.setter
    def filtered(self, val:FilteredDevices) -> None:
        prev = self.filtered
        self._filtered = val
        if prev != val:
            self.callbacks.on_filter_status_changed(self, val)
            self.call_callbacks()

    @property
    @override
    def arc(self) -> str:
        # audio return channel status
        return self._arc

    @arc.setter
    def arc(self, val:str) -> None:
        prev = self.arc
        self._arc = val
        if prev != self.arc:
            self.callbacks.on_status_arc_changed(self, val)
            self.call_callbacks()

    @property
    @override
    def volume_status(self) -> VolumeMuteStatus|None:
        # volume and mute status
        if not self.has_volume_control:
            if ((other := self.linked_bay) is not None) and other.has_volume_control:
                return other.volume_status
            return None
        return self._audio_volume

    @volume_status.setter
    def volume_status(self, other:VolumeMuteStatus) -> None:
        # # handle amp dolby modes
        # if self.device.is_amp:
        #     if self.is_output:
        #         if (self.bay >= self.device.amp_dolby_channels):
        #             self.device.get_by_portname('Input {}'.format(self.bay + 1)).volume_status = other
        #             return
        #         self.device.get_by_portname('Input 9').volume_status = other
        #         return
        if not self.has_volume_control:
            if ((other_bay := self.linked_bay) is not None) and other_bay.has_volume_control:
                other_bay.on_mxr_update(other)
            return

        changed = False
        if self._audio_volume is None:
            self._audio_volume = other
            changed = True
        else:
            changed = self._audio_volume.update(other)

        if changed:
            self.callbacks.on_volume_changed(self, self.volume_status)
            self.call_callbacks()
            lbay = self.linked_bay
            if lbay is not None:
                self.callbacks.on_volume_changed(lbay, self.volume_status)
                self.call_callbacks()

            if self.device.is_amp and self.is_input:
                if (self.bay == 8):
                    nb = 0
                    while nb < self.device.amp_dolby_channels:
                        outbay = self.device.get_by_mode_bay('Output', nb)
                        if (outbay is not None):
                            self.callbacks.on_volume_changed(outbay, self.volume_status)
                            outbay.call_callbacks()
                        nb = nb + 1
                    return
                outbay = self.device.get_by_mode_bay('Output', self.bay)
                if (outbay is not None):
                    self.callbacks.on_volume_changed(outbay, self.volume_status)
                    outbay.call_callbacks()

    @property
    @override
    def volume(self) -> int|None:
        # current volume
        vs = self.volume_status
        return vs.volume if vs is not None else None

    @property
    @override
    def muted(self) -> bool|None:
        # muted or not
        vs = self.volume_status
        return vs.muted if vs is not None else None

    @property
    @override
    def amp_settings(self) -> AmpZoneSettings|None:
        return self._amp_settings

    @amp_settings.setter
    def amp_settings(self, settings:AmpZoneSettings) -> None:
        changed = (self._amp_settings is None) or (self._amp_settings != settings)
        self._amp_settings = settings
        if changed:
            self.callbacks.on_amp_zone_settings_changed(self, settings)
            self.call_callbacks()

    @override
    async def select_edid_profile(self, profile:EdidProfile) -> bool:
        frame = FrameEDIDProfile.construct(mxr=self.device.registry, target=self.device, profile=profile)
        if frame is not None:
            self.device.registry.transmit(frame.frame)
            self.edid_profile = profile.value
            return True
        return False

    @override
    async def set_hidden(self, hidden:bool) -> bool:
        frame = FrameBayHide.construct(mxr=self.device.registry, target=self, hidden=hidden)
        if frame is not None:
            self.device.registry.transmit(frame.frame)
            self.hidden = hidden
            return True
        return False

    @override
    async def select_audio_source(self, source:int|BayBase|str|None, endpoint:str|None=None) -> bool:
        if not self.is_v2ip_sink:
            return False
        if isinstance(source, int):
            source = self.device.get_by_portnum(source)
        elif isinstance(source, str):
            source = self.bay_by_user_name(name=source)
        if (source is None):
            return False

        if (endpoint is not None):
            ep = source.device.audio_endpoint_by_name(name=endpoint)
            if (ep is None) or (self.audio_endpoint is None):
                return False
            frame = FrameV2IPAudio.construct_select_input(mxr=self.device.registry, sink=self.device.remote_id, sink_ep=self.audio_endpoint, source=source.device.remote_id, source_ep=ep)
        else:
            frame = FrameV2IPSourceSwitch.construct(mxr=self.device.registry, target=self, audio=source)
        if (frame is not None):
            self.device.registry.transmit(frame.frame)
            return True
        return False

    @override
    async def select_video_source(self, port:int, opt:bool=True) -> bool:
        if not self.is_output:
            return False
        if self.is_v2ip_sink:
            source_bay = self.device.get_by_portnum(port)
            if source_bay is not None:
                frame = FrameV2IPSourceSwitch.construct(mxr=self.device.registry, target=self, video=source_bay)
                if frame is not None:
                    self.device.registry.transmit(frame.frame)
                    return True
        return await self.device.get_api(f"port/set/{port}/{self.bay}/{1 if opt else 0}") is not None

    def bay_by_user_name(self, name:str) -> BayBase|None:
        for _, bay in self.device.inputs.items():
            if (bay.user_name == name):
                return bay
        return None

    @override
    async def select_video_source_by_user_name(self, name:str, opt:bool=True) -> bool:
        source = self.bay_by_user_name(name=name)
        if (source is None):
            return False
        return await self.select_video_source(source.port, opt)

    @override
    async def set_name(self, name:str) -> bool:
        frame = FrameSetName.construct(mxr=self.device.registry, target=self, name=name)
        if frame is not None:
            self.device.registry.transmit(frame.frame)
            self.user_name = name
            return True
        return False

    @override
    async def tx_action(self, action:RCAction) -> bool:
        pkt = FrameRCAction.construct(mxr=self.device.registry, target=self, action=action)
        if pkt is None:
            return False
        return self.device.registry.transmit(pkt.frame) == len(pkt)

    @override
    async def power_on(self) -> bool:
        if await self.tx_action(RCAction.ACTION_POWER_ON):
            self.power_status = PowerStatus.ON
            return True
        return False

    @override
    async def power_off(self) -> bool:
        if await self.tx_action(RCAction.ACTION_POWER_OFF):
            self.power_status = PowerStatus.OFF
            return True
        return False

    @override
    def volume_up(self) -> bool:
        return self.volume_set(self.volume + 1) if self.volume is not None else False

    @override
    def volume_down(self) -> bool:
        return self.volume_set(self.volume - 1) if self.volume is not None else False

    def _volume_set(self, volume:int, muted:bool|None=None) -> bool:
        if not self.has_volume_control:
            return False

        new_value = self.volume_status
        if new_value is None:
            # no known value, create a new one
            new_value = VolumeMuteStatus(volume_left=volume, volume_right=volume, muted_left=(volume != 0), muted_right=(volume != 0))
        else:
            # update the volume
            new_value.volume = volume

        self.volume_status = new_value

        if BayFeaturesMask.DOLBY in self.features and (self.bay == 0):
                for b in range(1, 4):
                    bay = self.device.get_by_mode_bay(mode=self.mode, bay=b)
                    if (bay is not None) and (BayFeaturesMask.DOLBY in bay.features):
                        bay.volume_status = new_value # pyright: ignore[reportAttributeAccessIssue]

        if (self.volume is None) or (volume > self.volume):
            # unmute
            self.volume_status.muted = False # pyright: ignore[reportOptionalMemberAccess]

        if muted is not None:
            # update the mute value if provided
            new_value.muted = muted

        # send the update to the remote device
        pkt = FrameVolumeSet.construct(mxr=self.device.registry, target=self, volume=new_value)
        if pkt is None:
            return False
        if self.device.registry.transmit(pkt.frame):
            self.callbacks.on_volume_changed(bay=self, volume=new_value)
            return True
        return False

    @override
    def volume_set(self, volume:int, muted:bool|None=None) -> bool:
        ''' Change the volume on the remote device '''
        if self._volume_set(volume=volume, muted=muted):
            return True

        if ((other := self.linked_bay) is not None):
            return other._volume_set(volume=volume, muted=muted) # pyright: ignore[reportAttributeAccessIssue]

        _LOGGER.warning(f"volume control is not supported by {self.device.serial}")
        return False

    @override
    def mute_set(self, mute:bool) -> bool:
        if (self.volume is None):
            return False
        return self.volume_set(self.volume, mute)

    @override
    async def send_key(self, key:int) -> bool:
        cmd = f"key/sendkey/{str(key)}/{self.mode}/{self.bay}"
        _LOGGER.debug(cmd)
        return await self.device.get_api(cmd) is not None

    @property
    @override
    def is_primary(self) -> bool:
        return self.device.registry.links.is_primary(self)

    @property
    @override
    def primary(self) -> BayBase:
        # primary bay if linked. this is the source type bay for linked bays. this bay is it's own primary if not linked
        if self.link_configured and not self.is_primary and self.link is not None and self.link.linked_bay is not None:
            return self.link.linked_bay
        return self

    @property
    @override
    def linked_bay(self) -> BayBase|None:
        # linked bay if linked, None if not linked
        if self.link_configured and self.link is not None:
            return self.link.linked_bay
        return None

    @property
    @override
    def link(self) -> BayLink|None:
        return self.device.registry.links.get(self)

    @property
    @override
    def link_configured(self) -> bool:
        link = self.link
        return (link is not None) and (link.linked)

    @property
    @override
    def link_connected(self) -> bool:
        return self.link.connected if self.link is not None else False

    @property
    @override
    def link_online(self) -> bool:
        return self.link.online if self.link is not None else False

    @property
    @override
    def features(self) -> BayFeaturesMask:
        return self._features

    def _on_mxr_bay_status(self, data:BayStatusMask|None) -> None:
        if (data is None):
            #TODO
            return
        self.faulty = BayStatusMask.FAULT in data
        self.hidden = BayStatusMask.HIDDEN in data
        self.poe_powered = BayStatusMask.POWERED in data
        self.hdbt_connected = BayStatusMask.HDBT_CONNECTED in data
        self.hpd_detected = BayStatusMask.HPD_DETECTED in data
        self.cec_detected = BayStatusMask.CEC_DETECTED in data
        self.signal_detected = BayStatusMask.SIGNAL_DETECTED in data
        self.encoder_disabled = BayStatusMask.ENCODER_DISABLED in data
        self.decoder_disabled = BayStatusMask.DECODER_DISABLED in data

        if BayStatusMask.CEC_DETECTED not in data:
            self.power_status = PowerStatus.UNKNOWN
        elif BayStatusMask.POWERED_ON in data:
            self.power_status = PowerStatus.ON
        elif BayStatusMask.POWERED_OFF in data:
            self.power_status = PowerStatus.OFF
        else:
            self.power_status = PowerStatus.UNKNOWN
        if BayStatusMask.AUDIO_ARC_HDMI in data:
            self.arc = self.ARC_HDMI
        elif BayStatusMask.AUDIO_ARC_OPTICAL in data:
            self.arc = self.ARC_OPTICAL
        elif BayStatusMask.AUDIO_ARC_ANALOG in data:
            self.arc = self.ARC_ANALOG
        else:
            self.arc = self.ARC_NONE

    def _on_mxr_bay_config(self, data:BayConfig) -> None:
        self._features = data.features
        self.status_mask = data.status
        self.user_name = data.user_name
        self.bay = data.bay
        self._on_mxr_bay_status(data.status)
        if BayStatusMask.SIGNAL_DETECTED not in data.status or not self.device.is_v2ip:
            self.signal_type = data.signal_type
        if self.is_output:
            self.video_source = self.device.get_by_portnum(data.video_source)
            self.audio_source = self.device.get_by_portnum(data.audio_source)
        else:
            self.rc_type = data.rc_type
            self.edid_profile = data.edid_profile

    @property
    def is_dolby(self) -> bool:
        if (not self.is_output):
            return False
        return BayFeaturesMask.DOLBY in self.features

    @override
    def set_zone_settings(self, settings:AmpZoneSettings) -> bool:
        frame = FrameAmpZoneSettings.construct(mxr=self.device.registry, target=self, settings=settings)
        if (frame is not None):
            self.device.registry.transmit(frame.frame)
            self.amp_settings = settings
            return True
        return False

    def on_mxr_audio_source_change(self, endpoint:AudioEndpoint, data:AudioChangeSource) -> None:
        if (data.target_uid is not None) and (data.target_id is not None):
            target = self.device.registry.get_audio_endpoint(device=data.target_uid, id=data.target_id)
            if (target is not None):
                if (target.bay is not None) and (target.bay == self):
                    print(f"TODO: {str(self)} change local audio source of {endpoint} to source {target}")
                else:
                    print(f"TODO: {str(target.bay)} change audio source of {endpoint} to source {target}")

    @override
    def on_mxr_update(self, data:Any) -> None:
        if (data is None):
            return
        if isinstance(data, VolumeMuteStatus):
            self.volume_status = data
            if BayFeaturesMask.DOLBY in self.features and (self.bay == 0):
                for b in range(1, 4):
                    bay = self.device.get_by_mode_bay(mode=self.mode, bay=b)
                    if (bay is not None) and (BayFeaturesMask.DOLBY in bay.features):
                        bay.on_mxr_update(data=data)
        elif isinstance(data, BayStatusMask):
            self._on_mxr_bay_status(data)
        elif isinstance(data, BayConfig):
            self._on_mxr_bay_config(data)
        elif isinstance(data, BayFeaturesMask):
            self._features = data
        elif isinstance(data, SelectedBays):
            if (data.video is not None):
                self.video_source = data.video
            if (data.audio is not None):
                self.audio_source = data.audio
        elif isinstance(data, PowerStatus):
            self.power_status = data
        elif isinstance(data, SignalStatus):
            self.signal_detected = data.detected
            if (data.description is not None):
                self.signal_type = data.description
        elif isinstance(data, RCAction):
            self.callbacks.on_action_received(self, data)
            self.call_callbacks()
        elif isinstance(data, RCKey):
            self.callbacks.on_key_pressed(self, data)
            self.call_callbacks()
        elif isinstance(data, ConnectStatus):
            if self.is_input:
                self.signal_detected = (data == ConnectStatus.CONNECTED)
            else:
                self.hpd_detected =  (data == ConnectStatus.CONNECTED)
        elif isinstance(data, FilteredDevices):
            self.filtered = data
        elif isinstance(data, HiddenStatus):
            if (data != HiddenStatus.UNKNOWN):
                self.hidden = (data == HiddenStatus.HIDDEN)
        elif isinstance(data, BayMirrorStatus):
            self.mirroring = data

    def __str__(self) -> str:
        if self.is_v2ip_source:
            if self.v2ip_source is None:
                return f"{self.device.serial} {self.bay_label} <unknown mcast address>"
            return f"{self.device.serial} {self.bay_label} {self.v2ip_source.video}"
        return f"{self.device.serial} {self.bay_label}"

    def __eq__(self, other:Any) -> bool:
        return isinstance(other, BayBase) and \
                (self.device == other.device) and \
                (self.port == other.port)
