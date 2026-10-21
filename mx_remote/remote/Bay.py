######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Bay implementation for a single input/output port on an MX Remote device.'''

from __future__ import annotations
import logging
import socket
import struct
from typing import Any, Callable
from ..compat import override
from ..proto.Constants import MxrSignalType, BayStatusMask, BayFeaturesMask, EdidProfile, RCType, RCAction, RCKey, decode_enum
from ..proto.BayConfig import BayConfig
from ..proto.Data import VolumeMuteStatus
from ..proto.FrameV2IPSourceSwitch import FrameV2IPSourceSwitch
from ..proto.FrameV2IPManualSourceSwitch import FrameV2IPManualSourceSwitch
from ..proto.V2IPConfig import OneIPAudioFormat
from ..proto.FrameEDIDProfile import FrameEDIDProfile
from ..proto.FrameBayHide import FrameBayHide
from ..proto.FrameSetName import FrameSetName, stored_name
from ..proto.FrameRCAction import FrameRCAction
from ..proto.FrameVolumeSet import FrameVolumeSet
from ..proto.FrameAmpZoneSettings import FrameAmpZoneSettings
from ..proto.FrameV2IPAudio import FrameV2IPAudio
from ..Interface import (
    VideoColourSpace,
    VideoSignalDetails,
    BayBase,
    DeviceBase,
    BayLink,
    MxrCallbacks,
    OneIPStreamSources,
    AmpZoneSettings,
    DeviceStatus,
    SelectedBays,
    BayContent,
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
from ..const import V2IP_UDP_PORT_AUDIO

_LOGGER = logging.getLogger(__name__)

_MODE_INPUT = 0
_MODE_OUTPUT = 1
'''A bay record's mode for an input and for an output.'''

_AUDIO_FOLLOWS_SINCE = 0x27
'''The protocol from which every unit's audio follows its video for a source
switch naming no audio. Some units below it route no audio instead.'''

class _MeshMirroring:
    '''The callbacks of a bay, each change also reported for the mesh bays
    standing for it. A bay's registration and the requests that arrive on it
    concern that bay alone.'''
    _UNREPEATED = frozenset(('on_bay_registered', 'on_key_pressed', 'on_action_received'))

    def __init__(self, callbacks:MxrCallbacks, bay:'Bay') -> None:
        self._callbacks = callbacks
        self._bay = bay

    def __getattr__(self, name:str) -> Any:
        fn = getattr(self._callbacks, name)
        if (name in self._UNREPEATED) or not callable(fn):
            return fn
        bay = self._bay
        def mirrored(*args:Any, **kwargs:Any) -> Any:
            rv = fn(*args, **kwargs)
            for mesh in bay.mesh_bays:
                fn(*[(mesh if (a is bay) else a) for a in args],
                   **{k: (mesh if (v is bay) else v) for k, v in kwargs.items()})
            return rv
        return mirrored

class Bay(BayBase):
    '''Represents a single input or output bay on an MX Remote device.'''

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
        self._modenum = data.modenum
        self._mbay_id = None
        self._video_source = None
        self._audio_source = None
        # The port a route named before the unit's mappings created that bay.
        self._pending_video_port:int|None = None
        self._pending_audio_port:int|None = None
        self._power_status:PowerStatus|None = None
        self._faulty = None
        self._hidden = None
        self._zone_powered = None
        self._hdbt_connected = None
        self._signal_detected = None
        self._signal_type = None
        self._video_details:VideoSignalDetails|None = None
        self._signal_snapshot:MxrSignalType|None = None
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
        self._content:BayContent = BayContent()
        self._bay_callbacks:list[Callable[[BayBase],None]] = []

    @staticmethod
    def mesh(dev:DeviceBase, port:int, is_input:bool, number:int, owner:MxrDeviceUid) -> 'Bay':
        '''A OneIP bay standing for bay 0 of the same direction on owner, as a
        bay mapping names it: input or output number, on port.

        It carries only its identity. What it describes is read from the
        owner's own bay, since what a unit reports about another unit's bay is
        never refreshed.'''
        mode, features, name = (_MODE_INPUT, BayFeaturesMask.ONEIP_SOURCE_REMOTE, 'Input') if is_input \
            else (_MODE_OUTPUT, BayFeaturesMask.ONEIP_SINK_REMOTE, 'Output')
        record = (bytes([port, mode, number, 0, 0]) + f'{name} {number + 1}'.encode('ascii').ljust(16, b'\0')
                  + bytes(32) + struct.pack('<II', 0, int(features)))
        bay = Bay(dev=dev, data=BayConfig(record))
        bay._mbay_id = number
        bay._v2ip_uid = owner
        return bay

    @property
    def mesh_owner(self) -> 'Bay|None':
        '''The bay a mesh bay stands for: bay 0 in the same direction on the
        unit it maps to, once that unit has reported it. None for a bay that is
        not a mesh bay.'''
        if not self.is_oneip_remote or (self._v2ip_uid is None) or self._v2ip_uid.empty:
            return None
        if ((owner := self.device.registry.get_by_uid(self._v2ip_uid)) is None):
            return None
        return getattr(owner, 'local_bay')(self._modenum == _MODE_INPUT)

    def _acted_on(self, what:str) -> 'Bay|None':
        '''The bay a command about this one acts on: this bay, or for a mesh bay
        bay 0 of the unit it stands for, which holds everything the mesh bay
        reports. None, with the reason logged, while that unit has not reported
        the bay, as there is nowhere to send the command.'''
        if not self.is_oneip_remote:
            return self
        if ((owner := self.mesh_owner) is None):
            _LOGGER.warning(f"not sending {what} to {self}: the bay it stands for has not been reported")
        return owner

    @property
    def mesh_bays(self) -> list['Bay']:
        '''The mesh bays on other units standing for this bay.'''
        device = self.device
        if (getattr(device, 'local_bay')(self.is_input) is not self):
            return []
        owner = device.remote_id
        return [bay for dev in device.registry.remotes.values() if (dev is not device)
                for bay in dev.bays.values()
                if isinstance(bay, Bay) and (bay._v2ip_uid == owner) and (bay.mesh_owner is self)]

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
        for mesh in self.mesh_bays:
            for callback in mesh._bay_callbacks:
                callback(mesh)

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
    def oneip_source(self) -> OneIPStreamSources|None:
        return self.device.oneip_source(self)

    @property
    @override
    def callbacks(self) -> MxrCallbacks:
        '''The callbacks, with every change to this bay also reported for the
        mesh bays standing for it.'''
        return _MeshMirroring(self.device.callbacks, self) # type: ignore[return-value]

    @property
    @override
    def device(self) -> DeviceBase:
        '''Remote device.'''
        return self._dev

    @property
    @override
    def bay_uid(self) -> MxrBayUid:
        # In a OneIP mesh the same source can be advertised by multiple devices
        # (mesh forwarding etc.). Resolve a v2ip source bay to (source_uid, 0)
        # — every OneIP unit has at most one input, always at port 0 — using the
        # source uid from MXR_OP_SYS_BAY_V2IP_SOURCES, falling back to the bay
        # mapping uid if the sources frame hasn't supplied one. Yields a single
        # stable bay_uid regardless of who advertises the source.
        if self.is_oneip_source:
            src_uid:MxrDeviceUid|None = None
            stream = self.oneip_source
            if (stream is not None) and (stream.uid is not None) and not stream.uid.empty:
                src_uid = stream.uid
            elif (self._v2ip_uid is not None) and not self._v2ip_uid.empty:
                src_uid = self._v2ip_uid
            if src_uid is not None:
                return MxrBayUid(src_uid, 0)
        return MxrBayUid(self.device.remote_id, self.port)

    @property
    @override
    def oneip_uid(self) -> MxrDeviceUid|None:
        return self._v2ip_uid

    @oneip_uid.setter
    def oneip_uid(self, uid:MxrDeviceUid|None) -> None:
        self._v2ip_uid = uid

    @property
    @override
    def oneip_device(self) -> DeviceBase|None:
        return self.device.registry.get_by_uid(self._v2ip_uid)

    @property
    @override
    def online(self) -> bool:
        '''Check whether the device to which this bay belongs is online.'''
        return self.device.online

    @property
    @override
    def port(self) -> int:
        '''Port number used for mxremote operations.'''
        return self._port_number

    @property
    @override
    def bay_name(self) -> str:
        '''Bay name.'''
        return self._port_name

    @property
    @override
    def user_name(self) -> str:
        '''Name set by the user.'''
        if ((owner := self.mesh_owner) is not None):
            return owner.user_name
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
        '''True if the default name is set, False if a custom name is set.'''
        return (self.user_name == self.bay_name)

    @property
    @override
    def bay_label(self) -> str:
        '''Bay name + user name, used for logging.'''
        name = self.bay_name
        user_name = self.user_name
        if user_name != name:
            return "{} ({})".format(name, user_name)
        return name

    @property
    @override
    def is_local(self) -> bool:
        return not self.is_oneip_remote

    @property
    @override
    def is_oneip_remote(self) -> bool:
        return BayFeaturesMask.ONEIP_SINK_REMOTE in self.features or BayFeaturesMask.ONEIP_SOURCE_REMOTE in self.features

    @property
    @override
    def is_oneip_source(self) -> bool:
        return BayFeaturesMask.ONEIP_SOURCE_LOCAL in self.features \
            or BayFeaturesMask.ONEIP_SOURCE_REMOTE in self.features

    @property
    @override
    def is_oneip_sink(self) -> bool:
        return BayFeaturesMask.ONEIP_SINK_LOCAL in self.features \
            or BayFeaturesMask.ONEIP_SINK_REMOTE in self.features

    @property
    @override
    def dolby_input(self) -> str|None:
        '''If dolby mode is set, the input bay that provides the audio source.'''
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
        '''Whether a unit takes a volume for the bay. A OneIP output carries a
        digital audio output and takes one.'''
        return BayFeaturesMask.AUDIO_ANA_OUT in self.features \
            or BayFeaturesMask.AUDIO_DIG_OUT in self.features \
            or BayFeaturesMask.AUDIO_AMP_OUT in self.features \
            or BayFeaturesMask.AUDIO_ANA_IN in self.features \
            or BayFeaturesMask.AUDIO_DIG_IN in self.features

    @property
    @override
    def is_input(self) -> bool:
        '''Whether the bay is an input, as its record's mode says. The feature
        bits decide only for a mode that is neither.'''
        if (self._modenum in (_MODE_INPUT, _MODE_OUTPUT)):
            return (self._modenum == _MODE_INPUT)
        return BayFeaturesMask.HDMI_IN in self.features \
            or BayFeaturesMask.AUDIO_DIG_IN in self.features \
            or BayFeaturesMask.AUDIO_ANA_IN in self.features \
            or self.is_oneip_source

    @property
    @override
    def is_output(self) -> bool:
        '''Whether the bay is an output, as is_input decides.'''
        if (self._modenum in (_MODE_INPUT, _MODE_OUTPUT)):
            return (self._modenum == _MODE_OUTPUT)
        return BayFeaturesMask.HDMI_OUT in self.features \
            or BayFeaturesMask.AUDIO_AMP_OUT in self.features \
            or BayFeaturesMask.AUDIO_DIG_OUT in self.features \
            or BayFeaturesMask.AUDIO_ANA_OUT in self.features \
            or self.is_oneip_sink

    @property
    @override
    def mode(self) -> str:
        '''Bay mode used by the web API and logging.'''
        if self.is_output:
            return 'Output'
        if self.is_input:
            return 'Input'
        return 'unknown'

    @property
    @override
    def other_mode(self) -> str:
        '''Opposite bay mode, used by the web API and logging.'''
        if self.is_output:
            return 'Input'
        if self.is_input:
            return 'Output'
        return 'unknown'

    @property
    @override
    def bay(self) -> int:
        '''Bay number used by the web API.'''
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
        if ((owner := self.mesh_owner) is not None):
            return owner.edid_profile
        if not self.is_hdmi or not self.is_input:
            return None
        # the wire field is 12 bits, so most of its range is not a member: a
        # profile this build does not know is UNKNOWN, not a ValueError at the
        # caller. The raw value stays available on the bay config.
        return decode_enum(EdidProfile, self._edid_profile)

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
        if ((owner := self.mesh_owner) is not None):
            return owner.rc_type
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
        '''Current video source bay.'''
        if ((owner := self.mesh_owner) is not None):
            return owner.video_source
        if not self.is_output:
            return None
        return self._video_source

    @property
    @override
    def video_route_endpoint(self) -> str|None:
        return self._sink_route_endpoint(audio=False)

    @video_source.setter
    def video_source(self, source:BayBase|None) -> None:
        '''Set the video source, None for none. Audio that follows the video
        moves with it, and is reported as moving.'''
        if not self.is_output or (source == self._video_source):
            return
        audio = self.audio_source
        self._video_source = source
        self.callbacks.on_video_source_changed(self, source)
        self._report_audio_move(audio)
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
        '''Current audio source bay.'''
        if ((owner := self.mesh_owner) is not None):
            return owner.audio_source
        if not self.is_output:
            return None
        if self._audio_source is None:
            return self.video_source
        return self._audio_source

    @audio_source.setter
    def audio_source(self, source:BayBase|None) -> None:
        '''Set a separate audio source, or None for audio that follows the video.'''
        if not self.is_output:
            return
        audio = self.audio_source
        self._audio_source = source
        if self._report_audio_move(audio):
            self.call_callbacks()

    def _report_audio_move(self, previous:BayBase|None) -> bool:
        '''Report the audio source moving from previous, True when it did.'''
        if (previous == self.audio_source):
            return False
        self.callbacks.on_audio_source_changed(bay=self, audio_source=self.audio_source)
        return True

    @property
    @override
    def audio_route_endpoint(self) -> str|None:
        return self._sink_route_endpoint(audio=True)

    def _sink_route_endpoint(self, audio:bool) -> str|None:
        '''Return 'ip:port' for an active sink subscription that doesn't map to any
        known input bay; None otherwise (no sink state, no active stream, or the
        multicast resolves to a registered source bay).'''
        if not self.is_output or not self.is_oneip_sink:
            return None
        sink = self.device.oneip_sink
        if sink is None or sink.addresses is None:
            return None
        stream = sink.addresses.audio if audio else sink.addresses.video
        if stream is None or stream.port == 0:
            return None
        if self.device.registry.get_by_stream_ip(ip=stream.ip, audio=audio) is not None:
            return None
        return f"{stream.ip}:{stream.port}"

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
            # if self.is_oneip_sink:
            #     rv.append(bay)
            # elif (bay.is_audio):
            #     rv.append(bay)
            rv.append(bay)
        return rv

    @property
    @override
    def audio_endpoint(self) -> AudioEndpoint|None:
        if ((owner := self.mesh_owner) is not None):
            return owner.audio_endpoint
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
        '''Connected device powered on.'''
        if ((owner := self.mesh_owner) is not None):
            return owner.powered_on
        # return (self._power_status is not None) and (self._power_status == PowerStatus.ON)
        return (self._power_status == PowerStatus.ON)

    @property
    @override
    def powered_off(self) -> bool:
        '''Connected device powered off.'''
        if ((owner := self.mesh_owner) is not None):
            return owner.powered_off
        # return (self._power_status is not None) and (self._power_status == 'off')
        return (self._power_status == PowerStatus.OFF)

    @property
    @override
    def power_status(self) -> PowerStatus:
        '''Device power status.'''
        if ((owner := self.mesh_owner) is not None):
            return owner.power_status
        if not self.available or self.powered_off:
            return PowerStatus.OFF
        if self.powered_on:
            return PowerStatus.ON
        if self.is_hdmi:
            if self.is_input:
                return PowerStatus.ON if self.signal_detected else PowerStatus.OFF
            if not self.hpd_detected:
                return PowerStatus.OFF
            if not self.signal_detected:
                return PowerStatus.OFF
            if self.is_hdbaset and not self.hdbt_connected:
                return PowerStatus.OFF
            return PowerStatus.ON
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
        '''Bay is faulty.'''
        if ((owner := self.mesh_owner) is not None):
            return owner.faulty
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
        '''Bay is hidden.'''
        if ((owner := self.mesh_owner) is not None):
            return owner.hidden
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
    def zone_powered(self) -> bool:
        '''The amplifier zone the bay drives is powered on.'''
        if ((owner := self.mesh_owner) is not None):
            return owner.zone_powered
        return (self._zone_powered is not None) and self._zone_powered

    @zone_powered.setter
    def zone_powered(self, val:bool) -> None:
        prev = self.zone_powered
        self._zone_powered = val
        if prev != self.zone_powered and (not prev or not val):
            self.callbacks.on_status_zone_powered_changed(self, val)
            self.call_callbacks()

    @property
    @override
    def hdbt_connected(self) -> bool:
        '''HDBaseT link up.'''
        if ((owner := self.mesh_owner) is not None):
            return owner.hdbt_connected
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
        '''Video/audio signal detected.'''
        if ((owner := self.mesh_owner) is not None):
            return owner.signal_detected
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
        '''Video/audio encoder disabled.'''
        if ((owner := self.mesh_owner) is not None):
            return owner.encoder_disabled
        return (self._encoder_disabled is not None) and self._encoder_disabled

    @encoder_disabled.setter
    def encoder_disabled(self, val:bool) -> None:
        prev = self.encoder_disabled
        self._encoder_disabled = val
        if prev != self.encoder_disabled:
            self.callbacks.on_bay_update(self)
            self.call_callbacks()

    @property
    @override
    def decoder_disabled(self) -> bool:
        '''Video/audio decoder disabled.'''
        if ((owner := self.mesh_owner) is not None):
            return owner.decoder_disabled
        return (self._decoder_disabled is not None) and self._decoder_disabled

    @decoder_disabled.setter
    def decoder_disabled(self, val:bool) -> None:
        prev = self.decoder_disabled
        self._decoder_disabled = val
        if prev != self.decoder_disabled:
            self.callbacks.on_bay_update(self)
            self.call_callbacks()

    @property
    @override
    def video_details(self) -> VideoSignalDetails|None:
        """Current video format, or None if neither source has carried one.

        A signal status report is preferred, because it arrives on a signal
        change. The bay config snapshot is the fallback for a bay no report has
        been seen for, and refreshes on the bay config broadcast cycle, so it can
        lag a change by a broadcast interval. from_report says which you have.
        """
        if ((owner := self.mesh_owner) is not None):
            return owner.video_details
        if (self._video_details is not None):
            return self._video_details
        snapshot = self._signal_snapshot
        if (snapshot is None) or not snapshot.is_set:
            return None
        return VideoSignalDetails(svd=snapshot.svd,
                                  colour=decode_enum(VideoColourSpace, snapshot.color),
                                  bpp=snapshot.bpp,
                                  non_int=snapshot.non_int,
                                  from_report=False)

    @property
    @override
    def signal_type(self) -> str:
        '''Video/audio signal type.'''
        if ((owner := self.mesh_owner) is not None):
            return owner.signal_type
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
        '''Hotplug detected.'''
        if ((owner := self.mesh_owner) is not None):
            return owner.hpd_detected
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
        '''CEC capable device detected.'''
        if ((owner := self.mesh_owner) is not None):
            return owner.cec_detected
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
    def content(self) -> BayContent:
        if ((owner := self.mesh_owner) is not None):
            return owner.content
        return self._content

    @property
    @override
    def mirroring(self) -> BayMirrorStatus:
        if ((owner := self.mesh_owner) is not None):
            return owner.mirroring
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
        if ((owner := self.mesh_owner) is not None):
            return owner.filtered
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
        '''Audio return channel status.'''
        if ((owner := self.mesh_owner) is not None):
            return owner.arc
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
        '''Volume and mute status.'''
        if ((owner := self.mesh_owner) is not None):
            return owner.volume_status
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
        '''Current volume.'''
        vs = self.volume_status
        return vs.volume if vs is not None else None

    @property
    @override
    def muted(self) -> bool|None:
        '''Muted or not.'''
        vs = self.volume_status
        return vs.muted if vs is not None else None

    @property
    @override
    def amp_settings(self) -> AmpZoneSettings|None:
        if ((owner := self.mesh_owner) is not None):
            return owner.amp_settings
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
        '''Select the EDID profile for this bay.'''
        if self.is_oneip_remote:
            owner = self._acted_on('an EDID profile')
            return (await owner.select_edid_profile(profile)) if (owner is not None) else False
        frame = FrameEDIDProfile.construct(mxr=self.device.registry, target=self.device, profile=profile)
        if frame is not None:
            if self.device.registry.transmit(frame.frame) != len(frame.frame):
                return False
            self.edid_profile = profile.value
            return True
        return False

    @override
    async def set_hidden(self, hidden:bool) -> bool:
        '''Set the bay hidden state.'''
        if self.is_oneip_remote:
            owner = self._acted_on('a hide')
            return (await owner.set_hidden(hidden)) if (owner is not None) else False
        frame = FrameBayHide.construct(mxr=self.device.registry, target=self, hidden=hidden)
        if frame is not None:
            if self.device.registry.transmit(frame.frame) != len(frame.frame):
                return False
            self.hidden = hidden
            return True
        return False

    @override
    async def select_audio_source(self, source:int|BayBase|str|None, endpoint:str|None=None, audio_fmt:OneIPAudioFormat|None=None) -> bool:
        '''Select the audio source for this output bay.

        ``source`` may be an input port number, a source ``BayBase``, or a raw
        ``"ip[:port]"`` multicast address string. The manual OneIP source switch
        frame (0x24) is used when ``audio_fmt`` is provided (so the receiver's
        sample rate and channel count can be overridden) or when ``source`` is a
        raw address (so its destination port is carried -- the legacy 0x1F frame
        has no port field). A raw address without a port defaults to the standard
        OneIP audio port. video/anc are sent as 0.0.0.0:0 (no change).

        True means the frame was sent, not that the sink applied it: none of
        these frames is acknowledged, so a sink that declines the route answers
        nothing. Confirm by waiting for ``audio_source`` to change.
        '''
        if not self.is_oneip_sink:
            return False
        # A mesh output is routed on the unit it stands for; its sources are
        # named in the numbering of the unit listing it, which the caller used.
        if ((sink := self._acted_on('an audio route')) is None):
            return False
        if isinstance(source, int):
            source = self.device.get_by_portnum(source)
        elif isinstance(source, str):
            try:
                socket.inet_aton(source.split(':', 1)[0])
            except OSError:
                source = self.bay_by_user_name(name=source)
        if (source is None) or (not isinstance(source, (BayBase, str))):
            return False

        # A raw "ip[:port]" source string carries a destination port that only the
        # manual switch frame (0x24) can express; the legacy source-switch frame
        # (0x1F) has no port field, so the receiver resolves the address against
        # its known sources and, failing that, falls back to the *default* audio
        # port -- a custom stream on any other port never routes. Use the manual
        # frame whenever the source is a raw address or an audio format override
        # is requested; a known input bay with neither still uses 0x1F.
        if (audio_fmt is not None) or isinstance(source, str):
            if isinstance(source, BayBase):
                if (source.oneip_source is None) or (source.oneip_source.audio is None):
                    return False
                audio_ip = source.oneip_source.audio.ip
                audio_port = source.oneip_source.audio.port
            else:
                host, _, port_s = source.partition(':')
                audio_ip = host
                audio_port = int(port_s) if port_s else V2IP_UDP_PORT_AUDIO
            frame = FrameV2IPManualSourceSwitch.construct(
                mxr=self.device.registry, target=sink.device,
                video_ip="0.0.0.0", video_port=0,
                audio_ip=audio_ip, audio_port=audio_port,
                anc_ip="0.0.0.0", anc_port=0,
                audio_fmt=audio_fmt,
            )
        elif (endpoint is not None) and isinstance(source, BayBase):
            ep = source.device.audio_endpoint_by_name(name=endpoint)
            if (ep is None) or (sink.audio_endpoint is None):
                return False
            # A unit on released firmware up to 4.4.2 routes only between its
            # own endpoints, which the builder refuses otherwise.
            frame = FrameV2IPAudio.construct_select_input(mxr=self.device.registry, sink=sink.device.remote_id, sink_ep=sink.audio_endpoint,
                                                          source=source.device.remote_id, source_ep=ep,
                                                          legacy=getattr(sink.device, 'audio_legacy', False))
        else:
            frame = FrameV2IPSourceSwitch.construct(mxr=self.device.registry, target=sink, audio=source)
        if (frame is not None):
            if self.device.registry.transmit(frame.frame) != len(frame.frame):
                return False
            return True
        return False

    @override
    async def select_video_source(self, port:int, opt:bool=True) -> bool:
        '''Select the video source for this output bay by port number.

        On the OneIP path True means the switch frame was sent, not that the sink
        applied it: the frame carries no acknowledgement, so a sink that declines
        the route answers nothing. A sink that does switch announces it, so
        confirm by waiting for ``video_source`` to change. The HTTP path used for
        a non-OneIP output does check for a response.
        '''
        if not self.is_output:
            return False
        if self.is_oneip_sink:
            # A mesh output is routed on the unit it stands for; the port is in
            # the numbering of the unit listing it, which the caller used.
            if ((sink := self._acted_on('a video route')) is None):
                return False
            source_bay = self.device.get_by_portnum(port)
            if source_bay is not None:
                # The sink's audio then follows the video, dropping a separate
                # audio route. Firmware up to 4.4.4 routes no audio for that
                # instead, and no stamp tells those builds from later ones, so
                # a unit below 0x27 is told the source's audio stream, which
                # every version plays.
                audio = source_bay if (sink.device.protocol < _AUDIO_FOLLOWS_SINCE) else None
                frame = FrameV2IPSourceSwitch.construct(mxr=self.device.registry, target=sink, video=source_bay,
                                                        audio=audio)
                if frame is not None:
                    if self.device.registry.transmit(frame.frame) != len(frame.frame):
                        return False
                    return True
        return await self.device.get_api(f"port/set/{port}/{self.bay}/{1 if opt else 0}") is not None

    def bay_by_user_name(self, name:str) -> BayBase|None:
        '''The input carrying the given user-assigned name, a mesh input by the
        name of the bay it stands for. Hidden ones are skipped: this resolves
        the name a picker shows, and a picker does not offer what it does not
        list.'''
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
        '''Set the user-defined name for this bay.'''
        if self.is_oneip_remote:
            owner = self._acted_on('a rename')
            return (await owner.set_name(name)) if (owner is not None) else False
        frame = FrameSetName.construct(mxr=self.device.registry, target=self, name=name)
        if frame is not None:
            if self.device.registry.transmit(frame.frame) != len(frame.frame):
                return False
            self.user_name = stored_name(name)
            return True
        return False

    @override
    async def tx_action(self, action:RCAction) -> bool:
        if self.is_oneip_remote:
            owner = self._acted_on('an action')
            return (await owner.tx_action(action)) if (owner is not None) else False
        pkt = FrameRCAction.construct(mxr=self.device.registry, target=self, action=action)
        if pkt is None:
            return False
        return self.device.registry.transmit(pkt.frame) == len(pkt.frame)

    @override
    async def power_on(self) -> bool:
        '''Power on the connected device.'''
        if self.is_oneip_remote:
            owner = self._acted_on('power on')
            return (await owner.power_on()) if (owner is not None) else False
        if await self.tx_action(RCAction.ACTION_POWER_ON):
            self.power_status = PowerStatus.ON
            return True
        return False

    @override
    async def power_off(self) -> bool:
        '''Power off the connected device.'''
        if self.is_oneip_remote:
            owner = self._acted_on('power off')
            return (await owner.power_off()) if (owner is not None) else False
        if await self.tx_action(RCAction.ACTION_POWER_OFF):
            self.power_status = PowerStatus.OFF
            return True
        return False

    @override
    def volume_up(self) -> bool:
        '''Increase volume by one step.'''
        return self.volume_set(self.volume + 1) if self.volume is not None else False

    @override
    def volume_down(self) -> bool:
        '''Decrease volume by one step.'''
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
        if self.device.registry.transmit(pkt.frame) == len(pkt.frame):
            self.callbacks.on_volume_changed(bay=self, volume=new_value)
            return True
        return False

    @override
    def volume_set(self, volume:int, muted:bool|None=None) -> bool:
        ''' Change the volume on the remote device '''
        if self.is_oneip_remote:
            owner = self._acted_on('a volume')
            return (owner.volume_set(volume, muted)) if (owner is not None) else False
        if self._volume_set(volume=volume, muted=muted):
            return True

        if ((other := self.linked_bay) is not None):
            return other._volume_set(volume=volume, muted=muted) # pyright: ignore[reportAttributeAccessIssue]

        _LOGGER.warning(f"volume control is not supported by {self.device.serial}")
        return False

    @override
    def mute_set(self, mute:bool) -> bool:
        '''Set the mute state on the remote device.'''
        if (self.volume is None):
            return False
        return self.volume_set(self.volume, mute)

    @override
    async def send_key(self, key:int) -> bool:
        '''Send a key press to the connected device.'''
        if self.is_oneip_remote:
            owner = self._acted_on('a key')
            return (await owner.send_key(key)) if (owner is not None) else False
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
        '''Primary bay if linked; the source-type bay for linked bays, or self if not linked.'''
        if self.link_configured and not self.is_primary and self.link is not None and self.link.linked_bay is not None:
            return self.link.linked_bay
        return self

    @property
    @override
    def linked_bay(self) -> BayBase|None:
        '''Linked bay if linked, None if not linked.'''
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
        self.zone_powered = BayStatusMask.POWERED in data
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
        self._modenum = data.modenum
        self.status_mask = data.status
        self.user_name = data.user_name
        self.bay = data.bay
        self._on_mxr_bay_status(data.status)
        self._signal_snapshot = data.signal_snapshot
        if BayStatusMask.SIGNAL_DETECTED not in data.status or not self.device.is_oneip:
            self.signal_type = data.signal_type
        if self.is_output:
            self._route_to(self._routed(data.video_source), self._routed(data.audio_source))
        else:
            self.rc_type = data.rc_type
            self.edid_profile = data.edid_profile

    def _routed(self, port:int) -> BayBase|int|None:
        '''The source a route names by port, as the device resolves it.'''
        resolve = getattr(self.device, 'routed_source', None)
        return resolve(port) if (resolve is not None) else self.device.get_by_portnum(port)

    def _route_to(self, video:BayBase|int|None, audio:BayBase|int|None) -> None:
        '''Set the route to sources the device has resolved: a bay, or the port
        of one its mappings have yet to create, which is taken once they do.

        A source that names nothing, 0xFF among them, keeps the route: a unit
        writes 0xFF to both fields of its output's record whenever either is
        unrouted, or routed to a port too wide for the field. Its routing change
        report is what clears a route.'''
        if (video is not None):
            self._pending_video_port = video if isinstance(video, int) else None
            if not isinstance(video, int):
                self.video_source = video
        if (audio is not None):
            self._pending_audio_port = audio if isinstance(audio, int) else None
            if not isinstance(audio, int):
                self.audio_source = audio

    def adopt_pending_source(self, source:BayBase) -> None:
        '''Take source as the route a report named by its port before it existed.'''
        if (self._pending_video_port == source.port):
            self._pending_video_port = None
            self.video_source = source
        if (self._pending_audio_port == source.port):
            self._pending_audio_port = None
            self.audio_source = source

    @property
    def is_dolby(self) -> bool:
        if (not self.is_output):
            return False
        return BayFeaturesMask.DOLBY in self.features

    @override
    def set_zone_settings(self, settings:AmpZoneSettings) -> bool:
        if self.is_oneip_remote:
            owner = self._acted_on('zone settings')
            return (owner.set_zone_settings(settings)) if (owner is not None) else False
        frame = FrameAmpZoneSettings.construct(mxr=self.device.registry, target=self, settings=settings)
        if (frame is not None):
            if self.device.registry.transmit(frame.frame) != len(frame.frame):
                return False
            self.amp_settings = settings
            return True
        return False

    def on_mxr_audio_source_change(self, endpoint:AudioEndpoint, data:AudioChangeSource) -> None:
        # endpoint is this bay's endpoint, the one changing source; resolve what
        # it is being pointed at
        if (data.source_uid is not None) and (data.source_id is not None):
            source = self.device.registry.get_audio_endpoint(device=data.source_uid, id=data.source_id)
            if (source is not None):
                if (source.bay is not None) and (source.bay == self):
                    _LOGGER.debug(f"{str(self)} change local audio source of {endpoint} to source {source}")
                else:
                    _LOGGER.debug(f"{str(source.bay)} change audio source of {endpoint} to source {source}")

    @override
    def on_mxr_update(self, data:Any) -> None:
        # A mesh bay describes itself through the bay it stands for, so what
        # the unit listing it says about it is that unit's copy, and changes
        # nothing.
        if (data is None) or self.is_oneip_remote:
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
            # None means the report named no bay, not that the route was
            # cleared. A manual switch carrying a zero address resolves to no
            # advertising bay and arrives here as None, while the addressed sink
            # falls back to whatever it was using - so clearing the route on
            # None would invent a state no device is in.
            if data.clear_video:
                self._pending_video_port = None
                self.video_source = None
            else:
                self._route_to(data.video, None)
            if data.audio_follows:
                self._pending_audio_port = None
                self.audio_source = None
            else:
                self._route_to(None, data.audio)
        elif isinstance(data, PowerStatus):
            self.power_status = data
        elif isinstance(data, SignalStatus):
            self.signal_detected = data.detected
            self._video_details = data.details
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
        elif isinstance(data, BayContent):
            if (data != self._content):
                self._content = data
                self.callbacks.on_bay_content_changed(self, data)
                self.call_callbacks()

    def __str__(self) -> str:
        if self.is_oneip_source:
            if self.oneip_source is None:
                return f"{self.device.serial} {self.bay_label} <unknown mcast address>"
            return f"{self.device.serial} {self.bay_label} {self.oneip_source.video}"
        return f"{self.device.serial} {self.bay_label}"

    def __eq__(self, other:Any) -> bool:
        return isinstance(other, BayBase) and \
                (self.device == other.device) and \
                (self.port == other.port)
