from __future__ import annotations
from .Link import Link
import mx_remote.api as api
import mx_remote.proto as proto
import mx_remote as remote
import logging
from typing import Any, Dict, List

_LOGGER = logging.getLogger(__name__)

class Bay:
    ARC_NONE = 'Inactive'
    ARC_HDMI = 'HDMI'
    ARC_OPTICAL = 'optical'
    ARC_ANALOG = 'analog'

    def __init__(self, dev:'mx_remote.remote.Device.Device', port_number:int, port_name:str):
        self._dev = dev
        self._port_number = port_number
        self._port_name = port_name
        self._user_name = None
        self._features = None
        self._is_input = None
        self._is_output = None
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
        self._link = None

    @property
    def mxr(self) -> remote.Remote:
        # mxremote instance
        return self._dev.mxr

    @property
    def dev(self) -> 'mx_remote.remote.Device.Device':
        # remote device
        return self._dev

    @property
    def online(self) -> bool:
        # check whether the device to which this bay belongs is online
        return self._dev.online

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
            self.mxr.on_name_changed(self, self.user_name)

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
    def dolby_input(self) -> int:
        # if dolby mode is set, the input bay that provides the audio source
        features = self.features_mask
        if (features & proto.MX_BAY_FEATURE_DOLBY):
            # TODO fix mx_remote offset
            return 'Input {}'.format('9') #((features >> proto.MX_BAY_FEATURE_DOLBY_IN_POS) & 0xF)
        return None

    @property
    def dolby_input_bay(self) -> Bay:
        db = self.dolby_input
        if db is None:
            return None
        return self.dev.get_by_portname(db)

    @property
    def features(self) -> List[str]:
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
        # source/input bay
        return (self.bay_name[0:5] == 'Input') if (self._is_input is None) \
            else self._is_input

    @is_input.setter
    def is_input(self, val:bool) -> None:
        if self._is_input is None:
            self._is_input = val

    @property
    def is_output(self) -> bool:
        # sink/output bay
        return (self.bay_name[0:6] == 'Output') if (self._is_output is None) \
            else self._is_output

    @is_output.setter
    def is_output(self, val:bool) -> None:
        if self._is_output is None:
            self._is_output = val

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
    def available(self):
        if self.faulty or self.hidden or not self.online:
            return False
        if self.is_hdbaset and not self.hdbt_connected:
            return False
        if self.dev.is_amp:
            if self.is_output:
                return (self.bay == 0) or (self.bay >= self.dev.amp_dolby_channels)
            return (self.bay > self.dev.amp_dolby_channels)
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
        return self.is_hdmi and self.is_output and (self.bay < self.dev.nb_hdbt)

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
    def video_source(self) -> Bay:
        # current video source bay
        return self._video_source

    @video_source.setter
    def video_source(self, source:Bay) -> None:
        # set the cached video source bay
        if source is None:
            self._video_source = source
            return
        if (self._video_source is None) or (source != self._video_source):
            self._video_source = source
            self.mxr.on_video_source_changed(self, source)

    async def select_video_source(self, port:int, opt:bool=True) -> bool:
        cmd = "port/set/{}/{}/{}".format(port, self.bay, "1" if opt else "0")
        return await self.dev.get_api(cmd) is not None

    async def select_video_source_by_user_name(self, name:str, opt:bool=True) -> bool:
        source = None
        for _, bay in self.dev.inputs.items():
            if bay.user_name == name:
                source = bay
                break
        if source is None:
            return False
        return await self.select_video_source(source.port, opt)

    @property
    def audio_source(self) -> Bay:
        # current audio source bay
        if self._audio_source is None:
            return self.video_source
        return self._audio_source

    @audio_source.setter
    def audio_source(self, source:Bay) -> None:
        # set the cached audio source bay
        if source is None:
            self._audio_source = source
            return
        prev = self.audio_source
        if (self._audio_source is None) or (source != self._audio_source):
            self._audio_source = source
        if prev != self.audio_source:
            self.mxr.on_audio_source_changed(self, self.audio_source)

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
            self.mxr.on_power_changed(self, power)

    async def power_on(self) -> bool:
        cmd = "key/sendcommand/1/{}/{}".format(self.mode, self.bay)
        if await self.dev.get_api(cmd) is not None:
            # TODO
            self.power_status = 'on'
            return True
        return False

    async def power_off(self) -> bool:
        cmd = "key/sendcommand/2/{}/{}".format(self.mode, self.bay)
        if await self.dev.get_api(cmd) is not None:
            # TODO
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
            self.mxr.on_status_faulty_changed(self, val)

    @property
    def hidden(self) -> bool:
        # bay is hidden
        return (self._hidden is not None) and self._hidden

    @hidden.setter
    def hidden(self, val:bool) -> None:
        prev = self.hidden
        self._hidden = val
        if prev != self.hidden and (prev or val):
            self.mxr.on_status_hidden_changed(self, val)

    @property
    def poe_powered(self) -> bool:
        # bay poe is powered
        return (self._poe_powered is not None) and self._poe_powered

    async def set_poe(self, val:bool) -> bool:
        cmd = "port/power/{}/{}".format(port, "1" if val else "0")
        return await self.dev.get_api(cmd) is not None

    @poe_powered.setter
    def poe_powered(self, val:bool) -> None:
        prev = self.poe_powered
        self._poe_powered = val
        if prev != self.poe_powered and (not prev or not val):
            self.mxr.on_status_poe_powered_changed(self, val)

    @property
    def hdbt_connected(self) -> bool:
        # hdbt link up
        return (self._hdbt_connected is not None) and self._hdbt_connected

    @hdbt_connected.setter
    def hdbt_connected(self, val:bool) -> None:
        prev = self.hdbt_connected
        self._hdbt_connected = val
        if prev != self.hdbt_connected:
            self.mxr.on_status_hdbt_connected_changed(self, val)

    @property
    def signal_detected(self) -> bool:
        # video/audio signal detected
        return (self._signal_detected is not None) and self._signal_detected

    @signal_detected.setter
    def signal_detected(self, val:bool) -> None:
        prev = self.signal_detected
        self._signal_detected = val
        if prev != self.signal_detected:
            self.mxr.on_status_signal_detected_changed(self, val)

    @property
    def signal_type(self) -> str:
        # video/audio signal type
        return self._signal_type if (self._signal_type is not None) else 'unknown'

    @signal_type.setter
    def signal_type(self, val:str) -> None:
        prev = self.signal_type
        self._signal_type = val
        if prev != self.signal_type:
            self.mxr.on_status_signal_type_changed(self, val)

    @property
    def hpd_detected(self) -> bool:
        # hotplug detected
        return (self._hpd_detected is not None) and self._hpd_detected

    @hpd_detected.setter
    def hpd_detected(self, val:bool) -> None:
        prev = self.hpd_detected
        self._hpd_detected = val
        if prev != self.hpd_detected:
            self.mxr.on_status_hpd_detected_changed(self, val)

    @property
    def cec_detected(self) -> bool:
        # CEC capable device detected
        return (self._cec_detected is not None) and self._cec_detected

    @cec_detected.setter
    def cec_detected(self, val:bool) -> None:
        prev = self.cec_detected
        self._cec_detected = val
        if prev != self.cec_detected:
            self.mxr.on_status_cec_detected_changed(self, val)

    @property
    def arc(self) -> str:
        # audio return channel status
        return self._arc

    @arc.setter
    def arc(self, val:str) -> None:
        prev = self.arc
        self._arc = val
        if prev != self.arc:
            self.mxr.on_status_arc_changed(self, val)

    @property
    def volume_status(self) -> proto.FrameVolume.VolumeMuteStatus:
        # volume and mute status

        # handle amp dolby modes
        if self.dev.is_amp:
            if self.is_output:
                if (self.bay >= self.dev.amp_dolby_channels):
                    return self.dev.get_by_portname('Input {}'.format(self.bay + 1)).volume_status
                return self.dev.get_by_portname('Input 9').volume_status

        # check mx_remote links
        primary = self.primary
        if primary != self:
            return primary.volume_status
        return self._audio_volume

    @volume_status.setter
    def volume_status(self, other:proto.FrameVolume.VolumeMuteStatus) -> None:
        # handle amp dolby modes
        if self.dev.is_amp:
            if self.is_output:
                if (self.bay >= self.dev.amp_dolby_channels):
                    self.dev.get_by_portname('Input {}'.format(self.bay + 1)).volume_status = other
                    return
                self.dev.get_by_portname('Input 9').volume_status = other
                return

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
            self.mxr.on_volume_changed(self, self.volume_status)
            lbay = self.linked_bay
            if lbay is not None:
                self.mxr.on_volume_changed(lbay, self.volume_status)

            if self.dev.is_amp and self.is_input:
                if (self.bay == 8):
                    nb = 0
                    while nb < self.dev.amp_dolby_channels:
                        self.mxr.on_volume_changed(self.dev.get_by_portname('Output {}'.format(nb + 1)), self.volume_status)
                        nb = nb + 1
                    return
                self.mxr.on_volume_changed(self.dev.get_by_portname('Output {}'.format(self.bay + 1)), self.volume_status)

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

    async def volume_up(self) -> bool:
        if self.dev.is_amp:
            return await self.volume_set(self.volume + 1)
        cmd = "key/sendcommand/3/{}/{}".format(self.mode, self.bay)
        return await self.dev.get_api(cmd) is not None

    async def volume_down(self) -> bool:
        if self.dev.is_amp:
            return await self.volume_set(self.volume - 1) if self.volume > 0 else True
        cmd = "key/sendcommand/4/{}/{}".format(self.mode, self.bay)
        return await self.dev.get_api(cmd) is not None

    async def volume_set(self, volume:int) -> bool:
        if not self.has_volume_control:
            return False
        if self.volume is None or (volume > self.volume):
            await self.mute_set(False)
        cmda = "amp" if self.dev.is_amp else "audio"
        cmd = "{}/volume/{}/{}".format(cmda, self.bay, volume)
        return await self.dev.get_api(cmd) is not None

    async def mute_set(self, mute:bool) -> bool:
        muted = self.muted
        if ((muted is not None) and (muted != mute)) or ((muted is None) and mute):
            if self.dev.is_amp:
                s = 3 if mute else 0
                cmd = "amp/mute/{}/{}".format(self.bay, s)
            else:
                cmd = "key/sendcommand/5/{}/{}".format(self.mode, self.bay)
            return await self.dev.get_api(cmd) is not None
        return True

    async def send_key(self, key:int) -> bool:
        cmd = "key/sendkey/{}/{}/{}".format(str(key), self.mode, self.bay)
        _LOGGER.warn(cmd)
        return await self.dev.get_api(cmd) is not None

    @property
    def is_primary(self) -> bool:
        # primary bay if linked. this is the source type bay for linked bays
        if not self.link_configured:
            return True
        return (self.primary == self)

    @property
    def primary(self) -> Bay:
        # primary bay if linked. this is the source type bay for linked bays. this bay is it's own primary if not linked
        if self.link_configured:
            return self._link.primary
        return self

    @property
    def linked_bay(self) -> Bay:
        # linked bay if linked, None if not linked
        if self._link is None:
            return None
        return self._link.other_bay(self)

    @property
    def link(self) -> Link:
        # link configuration. None if not linked
        return self._link

    @link.setter
    def link(self, link:Link) -> None:
        self._link = link

    @property
    def link_configured(self) -> bool:
        return (self.link is not None) and self.link.configured

    @property
    def link_connected(self) -> bool:
        return (self.link is not None) and self.link.connected

    def on_key_pressed(self, key:int) -> None:
        self.mxr.on_key_pressed(self, key)

    def on_mxr_bay_config(self, data:proto.BayConfig) -> None:
        had_signal = self.signal_detected

        self.features_mask = data.features
        self.user_name = data.user_name
        self.is_input = data.is_input
        self.is_output = data.is_output
        self.bay = data.bay
        self.faulty = data.status.fault
        self.hidden = data.status.hidden
        self.poe_powered = data.status.powered
        self.hdbt_connected = data.status.hdbt_connected
        self.hpd_detected = data.status.hpd_detected
        self.cec_detected = data.status.cec_detected
        self.signal_detected = data.status.signal_detected

        if data.status.powered_on:
            self.power_status = 'on'
        elif data.status.powered_off:
            self.power_status = 'off'
        else:
            self.power_status = 'unknown'
        if data.status.audio_arc_hdmi:
            self.arc = self.ARC_HDMI
        elif data.status.audio_arc_optical:
            self.arc = self.ARC_OPTICAL
        elif data.status.audio_arc_analog:
            self.arc = self.ARC_ANALOG
        else:
            self.arc = self.ARC_NONE
        self.signal_type = data.signal_type
        self.video_source = self.dev.get_by_portnum(data.video_source)
        self.audio_source = self.dev.get_by_portnum(data.audio_source)

    def on_mxr_volume_update(self, data:proto.FrameVolume.VolumeMuteStatus) -> None:
        self.volume_status = data

    def on_mxr_link_config(self, link_config:proto.LinkConfig.LinkConfig) -> None:
        link = Link(self, link_config)
        if self._link is None:
            self._link = link
            if link.configured:
                self.mxr.on_bay_linked(link)
            return
        self._link.update(self, link)

    def __str__(self) -> str:
        return "{} {}".format(self.dev.serial, self.bay_label)

    def __eq__(self, other:Any) -> bool:
        return isinstance(other, Bay) and \
                (self.dev == other.dev) and \
                (self.port == other.port)

    def __ne__(self, other:Any) -> bool:
        return not isinstance(other, Bay) or \
                (self.dev != other.dev) or \
                (self.port != other.port)

