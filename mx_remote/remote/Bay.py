##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from __future__ import annotations
import mx_remote.proto as proto
import logging
from typing import Any
from ..proto.Constants import BayStatusMask, EdidProfile, RCType, RCAction, RCKey
from ..proto.BayConfig import BayConfig
from ..proto.Data import VolumeMuteStatus
from ..proto.FrameBase import FrameBase
from ..proto.FrameV2IPSourceSwitch import FrameV2IPSourceSwitch
from ..proto.FrameEDIDProfile import FrameEDIDProfile
from ..proto.FrameBayHide import FrameBayHide
from ..proto.FrameSetName import FrameSetName
from ..Interface import BayBase, DeviceBase, BayLink, MxrCallbacks, V2IPStreamSources, AmpZoneSettings, DeviceStatus
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
        self._power_status = None
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
        self._mirror = None
        self._decoder_disabled = None
        self._encoder_disabled = None
        self._status_mask = data.status
        self._amp_settings:AmpZoneSettings|None = None
        self._filtered = []
        self._bay_callbacks:list[callable] = []

    def register_callback(self, callback:callable) -> None:
         '''register a callback, called when the device state changed'''
         self._bay_callbacks.append(callback)

    def unregister_callback(self, callback:callable) -> None:
         '''unregister a callback'''
         if callback in self._bay_callbacks:
            self._bay_callbacks.remove(callback)

    def call_callbacks(self) -> None:
        for callback in self._bay_callbacks:
            callback(self)

    @property
    def rebooting(self) -> bool:
        '''True if rebooting'''
        return self.device.rebooting

    @property
    def booting(self) -> bool:
        '''True if booting'''
        return self.device.booting

    @property
    def status(self) -> DeviceStatus:
        if self.online:
            if self.rebooting:
                return DeviceStatus.REBOOTING
            if self.booting:
                return DeviceStatus.BOOTING
            if self.status_mask.encoder_disabled or self.status_mask.decoder_disabled:
                return DeviceStatus.INACTIVE
            return DeviceStatus.ONLINE
        return DeviceStatus.OFFLINE

    @property
    def v2ip_source(self) -> V2IPStreamSources|None:
        return self.device.v2ip_source(self)

    @property
    def callbacks(self) -> MxrCallbacks:
        return self.device.callbacks

    @property
    def device(self) -> DeviceBase:
        # remote device
        return self._dev

    @property
    def bay_uid(self) -> MxrBayUid:
        return MxrBayUid(self.device.remote_id, self.port)

    @property
    def online(self) -> bool:
        # check whether the device to which this bay belongs is online
        return self.device.online

    @property
    def port(self) -> int:
        # port number used for mxremote operations
        return self._port_number

    @property
    def bay_name(self) -> str:
        # mbay name
        return self._port_name

    @property
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
    def has_default_name(self) -> bool:
        # default name set or custom name set
        return (self.user_name == self.bay_name)

    @property
    def bay_label(self) -> str:
        # bay name + user name, used for logging
        name = self.bay_name
        user_name = self.user_name
        if user_name != name:
            return "{} ({})".format(name, user_name)
        return name

    @property
    def features_mask(self) -> int:
        # supported features for this bay (bitmask)
        return self._features if self._features is not None else 0

    @features_mask.setter
    def features_mask(self, val:int) -> None:
        self._features = val

    @property
    def is_local(self) -> bool:
        return not self.is_v2ip_remote

    @property
    def is_v2ip_source(self) -> bool:
        mask = self.features_mask
        return ((mask & proto.MX_BAY_FEATURE_V2IP_SOURCE_REMOTE) != 0) \
            or ((mask & proto.MX_BAY_FEATURE_V2IP_SOURCE_LOCAL) != 0)

    @property
    def is_v2ip_sink(self) -> bool:
        mask = self.features_mask
        return ((mask & proto.MX_BAY_FEATURE_V2IP_SINK_REMOTE) != 0) \
            or ((mask & proto.MX_BAY_FEATURE_V2IP_SINK_LOCAL) != 0)

    @property
    def is_v2ip_remote_sink(self) -> bool:
        return ((self.features_mask & proto.MX_BAY_FEATURE_V2IP_SINK_REMOTE) != 0)

    @property
    def is_v2ip_remote_source(self) -> bool:
        return ((self.features_mask & proto.MX_BAY_FEATURE_V2IP_SOURCE_REMOTE) != 0)

    @property
    def is_v2ip_remote(self) -> bool:
        return self.is_v2ip_remote_sink or self.is_v2ip_remote_source

    @property
    def dolby_input(self) -> int:
        # if dolby mode is set, the input bay that provides the audio source
        features = self.features_mask
        if (features & proto.MX_BAY_FEATURE_DOLBY):
            # TODO fix mx_remote offset
            return 'Input {}'.format('9') #((features >> proto.MX_BAY_FEATURE_DOLBY_IN_POS) & 0xF)
        return None

    @property
    def dolby_input_bay(self) -> BayBase:
        db = self.dolby_input
        if db is None:
            return None
        return self.device.get_by_portname(db)

    @property
    def features(self) -> list[str]:
        # list of supported features for this bay
        rv = []
        mask = self.features_mask
        if (mask & proto.MX_BAY_FEATURE_HDMI_OUT):
            rv.append('HDMI output')
        if (mask & proto.MX_BAY_FEATURE_HDMI_IN):
            rv.append('HDMI input')
        if (mask & proto.MX_BAY_FEATURE_AUDIO_DIG_OUT):
            rv.append('digital audio output')
        if (mask & proto.MX_BAY_FEATURE_AUDIO_DIG_IN):
            rv.append('digital audio input')
        if (mask & proto.MX_BAY_FEATURE_AUDIO_ANA_OUT):
            rv.append('analog audio output')
        if (mask & proto.MX_BAY_FEATURE_AUDIO_ANA_IN):
            rv.append('analog audio input')
        if (mask & proto.MX_BAY_FEATURE_IR_OUT):
            rv.append('IR transmitter')
        if (mask & proto.MX_BAY_FEATURE_IR_IN):
            rv.append('IR receiver')
        if (mask & proto.MX_BAY_FEATURE_AUDIO_AMP_OUT):
            rv.append('amplifier audio output')
        if (mask & proto.MX_BAY_FEATURE_RC_OUT):
            rv.append('remote control out')
        if (mask & proto.MX_BAY_FEATURE_RC_IN):
            rv.append('remote control in')
        if (mask & proto.MX_BAY_FEATURE_V2IP_SOURCE_REMOTE):
            rv.append('V2IP remote source')
        if (mask & proto.MX_BAY_FEATURE_V2IP_SINK_REMOTE):
            rv.append('V2IP remote sink')
        if (mask & proto.MX_BAY_FEATURE_V2IP_SOURCE_LOCAL):
            rv.append('V2IP source')
        if (mask & proto.MX_BAY_FEATURE_V2IP_SINK_LOCAL):
            rv.append('V2IP sink')
        if (mask & proto.MX_BAY_FEATURE_DOLBY):
            rv.append('dolby')
        if (mask & proto.MX_BAY_FEATURE_AUTO_OFF):
            rv.append('auto off')
        return rv

    @property
    def has_volume_control(self) -> bool:
        mask = self.features_mask
        if (mask & proto.MX_BAY_FEATURE_AUDIO_ANA_OUT):
            return True
        if (mask & proto.MX_BAY_FEATURE_AUDIO_AMP_OUT):
            return True
        return False

    @property
    def is_input(self) -> bool:
        mask = self.features_mask
        return ((mask & proto.MX_BAY_FEATURE_HDMI_IN) != 0) \
            or ((mask & proto.MX_BAY_FEATURE_AUDIO_DIG_IN) != 0) \
            or ((mask & proto.MX_BAY_FEATURE_AUDIO_ANA_IN) != 0) \
            or ((mask & proto.MX_BAY_FEATURE_V2IP_SOURCE_REMOTE) != 0) \
            or ((mask & proto.MX_BAY_FEATURE_V2IP_SOURCE_LOCAL) != 0)

    @property
    def is_output(self) -> bool:
        mask = self.features_mask
        return ((mask & proto.MX_BAY_FEATURE_HDMI_OUT) != 0) \
            or ((mask & proto.MX_BAY_FEATURE_AUDIO_AMP_OUT) != 0) \
            or ((mask & proto.MX_BAY_FEATURE_AUDIO_DIG_OUT) != 0) \
            or ((mask & proto.MX_BAY_FEATURE_AUDIO_ANA_OUT) != 0) \
            or ((mask & proto.MX_BAY_FEATURE_V2IP_SINK_REMOTE) != 0) \
            or ((mask & proto.MX_BAY_FEATURE_V2IP_SINK_LOCAL) != 0)

    @property
    def mode(self) -> str:
        # bay mode used by the web api and logging
        if self.is_output:
            return 'Output'
        if self.is_input:
            return 'Input'
        return 'unknown'

    @property
    def other_mode(self) -> str:
        # bay mode used by the web api and logging
        if self.is_output:
            return 'Input'
        if self.is_input:
            return 'Output'
        return 'unknown'

    @property
    def bay(self) -> int:
        # bay number used by the web api
        return self._mbay_id if (self._mbay_id is not None) \
            else int(self.bay_name[len(self.mode)+1:])

    @bay.setter
    def bay(self, val:int) -> None:
        if self._mbay_id is None:
            self._mbay_id = val

    @property
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
    def is_hdmi(self) -> bool:
        # HDMI bay
        mask = self.features_mask
        return ((mask & proto.MX_BAY_FEATURE_HDMI_OUT) != 0) or ((mask & proto.MX_BAY_FEATURE_HDMI_IN) != 0)

    @property
    def is_hdbaset(self) -> bool:
        #HDBaseT bay
        # TODO add to proto
        return self.is_hdmi and self.is_output and (self.bay < self.device.nb_hdbt)

    @property
    def is_audio(self) -> bool:
        # audio bay
        if self.is_hdmi:
            return False
        mask = self.features_mask
        return ((mask & proto.MX_BAY_FEATURE_AUDIO_DIG_OUT) != 0) or ((mask & proto.MX_BAY_FEATURE_AUDIO_DIG_IN) != 0) or \
            ((mask & proto.MX_BAY_FEATURE_AUDIO_ANA_OUT) != 0) or ((mask & proto.MX_BAY_FEATURE_AUDIO_ANA_IN) != 0) or \
            ((mask & proto.MX_BAY_FEATURE_AUDIO_AMP_OUT) != 0)

    @property
    def edid_profile(self) -> EdidProfile:
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
    def rc_type(self) -> RCType:
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
    def video_source(self) -> BayBase:
        if not self.is_output:
            return None
        # current video source bay
        return self._video_source

    @video_source.setter
    def video_source(self, source:BayBase) -> None:
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

    async def select_edid_profile(self, profile:EdidProfile) -> bool:
        frame:FrameBase = FrameEDIDProfile.construct(mxr=self.device.registry, target=self.device, profile=profile)
        if frame is not None:
            self.device.registry.transmit(frame.frame)
            self.edid_profile = profile
            return True
        return False

    async def set_hidden(self, hidden:bool) -> bool:
        frame:FrameBase = FrameBayHide.construct(mxr=self.device.registry, target=self, hidden=hidden)
        if frame is not None:
            self.device.registry.transmit(frame.frame)
            self.hidden = hidden
            return True
        return False

    async def select_audio_source(self, source:int|BayBase|str) -> bool:
        if not self.is_v2ip_sink:
            return False
        if isinstance(source, int):
            source = self.device.get_by_portnum(source)
        frame:FrameBase = FrameV2IPSourceSwitch.construct(mxr=self.device.registry, target=self, audio=source)
        if frame is not None:
            self.device.registry.transmit(frame.frame)
            return True
        return False

    async def select_video_source(self, port:int, opt:bool=True) -> bool:
        if not self.is_output:
            return False
        if self.is_v2ip_sink:
            source_bay = self.device.get_by_portnum(port)
            if source_bay is not None:
                frame:FrameBase = FrameV2IPSourceSwitch.construct(mxr=self.device.registry, target=self, video=source_bay)
                if frame is not None:
                    self.device.registry.transmit(frame.frame)
                    return True
        return await self.device.get_api(f"port/set/{port}/{self.bay}/{1 if opt else 0}") is not None

    async def select_video_source_by_user_name(self, name:str, opt:bool=True) -> bool:
        source = None
        for _, bay in self.device.inputs.items():
            if bay.user_name == name:
                source = bay
                break
        if source is None:
            return False
        return await self.select_video_source(source.port, opt)

    async def set_name(self, name:str) -> bool:
        frame:FrameBase = FrameSetName.construct(mxr=self.device.registry, target=self, name=name)
        if frame is not None:
            self.device.registry.transmit(frame.frame)
            self.user_name = name
            return True
        return False

    @property
    def audio_source(self) -> BayBase:
        if not self.is_output:
            return None
        # current audio source bay
        if self._audio_source is None:
            return self.video_source
        return self._audio_source

    @audio_source.setter
    def audio_source(self, source:BayBase) -> None:
        if not self.is_output:
            return
        # set the cached audio source bay
        if source is None:
            self._audio_source = source
            return
        prev = self.audio_source
        if (self._audio_source is None) or (source != self._audio_source):
            self._audio_source = source
        if prev != self.audio_source:
            self.callbacks.on_audio_source_changed(self, self.audio_source)
            self.call_callbacks()

    @property
    def powered_on(self) -> bool:
        # connected device powered on
        return (self._power_status is not None) and (self._power_status == 'on')

    @property
    def powered_off(self) -> bool:
        # connected device powered off
        return (self._power_status is not None) and (self._power_status == 'off')

    @property
    def power_status(self) -> str:
        # device power status
        if not self.available or self.powered_off:
            return "off"
        if self.powered_on:
            return "on"
        if self.is_hdmi:
            if self.is_input:
                return "on" if self.signal_detected else "off"
            if self.is_output and not self.hpd_detected:
                return "off"
            if not self.signal_detected:
                return "off"
            if self.is_hdbaset and not self.hdbt_connected:
                return "off"
        elif self.is_audio:
            if self.muted:
                return "off"
            return "on" if (self.signal_detected) else "off"
        return "unknown"

    @power_status.setter
    def power_status(self, power:str) -> None:
        prev = self.power_status
        self._power_status = power
        if (self.power_status != prev):
            self.callbacks.on_power_changed(self, power)
            self.call_callbacks()

    async def tx_action(self, action:RCAction) -> bool:
        from ..proto.FrameRCAction import FrameRCAction
        pkt:FrameBase = FrameRCAction.construct(mxr=self.device.registry, target=self, action=action)
        return self.device.registry.transmit(pkt.frame)

    async def power_on(self) -> bool:
        if await self.tx_action(RCAction.ACTION_POWER_ON):
            self.power_status = 'on'
            return True
        return False

    async def power_off(self) -> bool:
        if await self.tx_action(RCAction.ACTION_POWER_OFF):
            self.power_status = 'off'
            return True
        return False

    @property
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
    def mirroring(self) -> str:
        return self._mirror

    @mirroring.setter
    def mirroring(self, val) -> None:
        prev = self.mirroring
        self._mirror = val
        if prev != val:
            self.callbacks.on_mirror_status_changed(self, val)
            self.call_callbacks()

    @property
    def filtered(self) -> str:
        return self._filtered

    @filtered.setter
    def filtered(self, val) -> None:
        prev = self.filtered
        self._filtered = val
        if prev != val:
            self.callbacks.on_filter_status_changed(self, val)
            self.call_callbacks()

    @property
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
    def volume_status(self) -> VolumeMuteStatus:
        # volume and mute status

        # # handle amp dolby modes
        # if self.device.is_amp:
        #     if self.is_output:
        #         if (self.bay >= self.device.amp_dolby_channels):
        #             return self.device.get_by_portname('Input {}'.format(self.bay + 1)).volume_status
        #         return self.device.get_by_portname('Input 9').volume_status

        # check mx_remote links
        primary = self.primary
        if primary != self:
            return primary.volume_status
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

        primary = self.primary
        if primary != self:
            primary.volume_status = other
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
                        self.callbacks.on_volume_changed(self.device.get_by_portname('Output {}'.format(nb + 1)), self.volume_status)
                        self.device.get_by_portname('Output {}'.format(nb + 1)).call_callbacks()
                        nb = nb + 1
                    return
                self.callbacks.on_volume_changed(self.device.get_by_portname('Output {}'.format(self.bay + 1)), self.volume_status)
                self.device.get_by_portname('Output {}'.format(nb + 1)).call_callbacks()

    @property
    def volume(self) -> int:
        # current volume
        vs = self.volume_status
        return vs.volume if vs is not None else None

    @property
    def muted(self) -> bool:
        # muted or not
        vs = self.volume_status
        return vs.muted if vs is not None else None

    @property
    def amp_settings(self) -> AmpZoneSettings|None:
        return self._amp_settings

    @amp_settings.setter
    def amp_settings(self, settings:AmpZoneSettings) -> None:
        changed = (self._amp_settings is None) or (self._amp_settings != settings)
        self._amp_settings = settings
        if changed:
            self.callbacks.on_amp_zone_settings_changed(self, settings)
            self.call_callbacks()

    def volume_up(self) -> bool:
        return self.volume_set(self.volume + 1)

    def volume_down(self) -> bool:
        return self.volume_set(self.volume - 1)

    def volume_set(self, volume:int, muted:bool=None) -> bool:
        ''' Change the volume on the remote device '''
        from ..proto.FrameVolumeSet import FrameVolumeSet
        if not self.has_volume_control:
            # remote device doesn't support volume control
            return False

        new_value = self.volume_status
        if new_value is None:
            # no known value, create a new one
            new_value = VolumeMuteStatus(volume_left=volume, volume_right=volume, muted_left=(volume != 0), muted_right=(volume != 0))
        else:
            # update the volume
            new_value.volume = volume
        self.volume_status = new_value

        if (self.volume is None) or (volume > self.volume):
            # unmute
            self.volume_status.muted = False

        if muted is not None:
            # update the mute value if provided
            new_value.muted = muted

        # send the update to the remote device
        pkt:FrameBase = FrameVolumeSet.construct(mxr=self.device.registry, target=self, volume=new_value)
        if self.device.registry.transmit(pkt.frame):
            self.callbacks.on_volume_changed(bay=self, volume=new_value)
            return True
        return False

    def mute_set(self, mute:bool) -> bool:
        return self.volume_set(self.volume, mute)

    async def send_key(self, key:int) -> bool:
        cmd = "key/sendkey/{}/{}/{}".format(str(key), self.mode, self.bay)
        _LOGGER.info(cmd)
        return await self.device.get_api(cmd) is not None

    @property
    def is_primary(self) -> bool:
        return self.device.registry.links.is_primary(self)

    @property
    def primary(self) -> BayBase:
        # primary bay if linked. this is the source type bay for linked bays. this bay is it's own primary if not linked
        if self.link_configured and not self.is_primary:
            return self.link.linked_bay
        return self

    @property
    def linked_bay(self) -> BayBase:
        # linked bay if linked, None if not linked
        if self.link_configured:
            return self.link.linked_bay
        return None

    @property
    def link(self) -> BayLink|None:
        return self.device.registry.links.get(self)

    @property
    def link_configured(self) -> bool:
        link = self.link
        return (link is not None) and (link.linked)

    @property
    def link_connected(self) -> bool:
        return self.link.connected

    @property
    def link_online(self) -> bool:
        return self.link.online

    def on_key_pressed(self, key:RCKey) -> None:
        self.callbacks.on_key_pressed(self, key)
        self.call_callbacks()

    def on_action_received(self, action:RCAction) -> None:
        self.callbacks.on_action_received(self, action)
        self.call_callbacks()

    def on_mxr_bay_status(self, data:BayStatusMask) -> None:
        self.faulty = data.fault
        self.hidden = data.hidden
        self.poe_powered = data.powered
        self.hdbt_connected = data.hdbt_connected
        self.hpd_detected = data.hpd_detected
        self.cec_detected = data.cec_detected
        self.signal_detected = data.signal_detected
        self.encoder_disabled = data.encoder_disabled
        self.decoder_disabled = data.decoder_disabled

        if not data.cec_detected:
            self.power_status = 'unknown'
        elif data.powered_on:
            self.power_status = 'on'
        elif data.powered_off:
            self.power_status = 'off'
        else:
            self.power_status = 'unknown'
        if data.audio_arc_hdmi:
            self.arc = self.ARC_HDMI
        elif data.audio_arc_optical:
            self.arc = self.ARC_OPTICAL
        elif data.audio_arc_analog:
            self.arc = self.ARC_ANALOG
        else:
            self.arc = self.ARC_NONE

    def on_mxr_bay_config(self, data:BayConfig) -> None:
        self.features_mask = data.features
        self.status_mask = data.status
        self.user_name = data.user_name
        self.bay = data.bay
        self.on_mxr_bay_status(data.status)
        if not data.status.signal_detected or not self.device.is_v2ip:
            self.signal_type = data.signal_type
        if self.is_output:
            self.video_source = self.device.get_by_portnum(data.video_source)
            self.audio_source = self.device.get_by_portnum(data.audio_source)
        else:
            self.rc_type = data.rc_type
            self.edid_profile = data.edid_profile

    def on_mxr_volume_update(self, data:VolumeMuteStatus) -> None:
        self.volume_status = data

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
