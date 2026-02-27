##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from abc import ABC, abstractmethod
from functools import cached_property
import aiohttp
import ipaddress
import logging
import netifaces
from .proto import RCKey
from .proto.Constants import *
from .proto.Data import VolumeMuteStatus
from .proto.V2IPStats import V2IPDeviceStats
from .proto.Multiviewer import (
	MultiviewerViewMode,
	MultiviewerSource,
	MultiviewerBoolSetting,
	MultiviewerEDIDTemplate,
	MultiviewerPipSize,
	MultiviewerPipPosition,
	MultiviewerAspectRatio,
	MultiviewerOutputMode,
	MultiviewerITCMode,
	MultiviewerHDCPMode,
)
from .proto.Svd import SvdMap
from typing import Any, Callable
from .Uid import MxrDeviceUid, MxrBayUid

_LOGGER = logging.getLogger(__name__)

def mxr_valid_addresses() -> list[str]:
    """
    Get the list of valid local_ip addresses that can be used

    Returns:
        addresses (list[str]): list of IP addressses that can be used for the local_ip parameter
    """
    addresses = []
    for iface in netifaces.interfaces():
        if netifaces.AF_INET in netifaces.ifaddresses(iface):
            addr = netifaces.ifaddresses(iface)[netifaces.AF_INET][0]['addr']
            if not ipaddress.IPv4Address(addr).is_loopback:
                addresses.append(addr)
    return addresses

class DeviceStatus(Enum):
    """
    Status of a device on the network
    """

    ONLINE = 0
    """ unit is online """

    OFFLINE = 1
    """ unit is offline """

    REBOOTING = 2
    """ unit indicated that it is going to reboot """

    BOOTING = 3
    """ unit is booting """

    INACTIVE = 4
    """ bay is inactive (V2IP encoder/decoder idle) """

    def __str__(self) -> str:
        if self.value == DeviceStatus.ONLINE.value:
            return 'Online'
        if self.value == DeviceStatus.OFFLINE.value:
            return 'Offline'
        if self.value == DeviceStatus.REBOOTING.value:
            return 'Rebooting'
        if self.value == DeviceStatus.BOOTING.value:
            return 'Booting'
        if self.value == DeviceStatus.INACTIVE.value:
            return 'Inactive'
        return 'Unknown'

    def __repr__(self) -> str:
        return str(self)

class PowerStatus(Enum):
    UNKNOWN = 0
    ON = 1
    OFF = 2

    def __str__(self) -> str:
        if self.value == PowerStatus.ON.value:
            return 'on'
        if self.value == PowerStatus.OFF.value:
            return 'off'
        return 'unknown'

    def __repr__(self) -> str:
        return str(self)

class HiddenStatus(Enum):
    UNKNOWN = 0
    HIDDEN = 1
    VISIBLE = 2

    def __str__(self) -> str:
        if self.value == HiddenStatus.HIDDEN.value:
            return 'hidden'
        if self.value == HiddenStatus.VISIBLE.value:
            return 'visible'
        return 'unknown'

    def __repr__(self) -> str:
        return str(self)

class FirmwareVersion:
    def __init__(self, type:FirmwareType, timestamp:int, version:str, hash:int) -> None:
        self._firmware_type = type
        self._timestamp = timestamp
        self._version = version
        self._hash = hash

    @property
    def firmware_type(self) -> FirmwareType:
        return self._firmware_type

    @property
    def timestamp(self) -> int:
        return self._timestamp

    @property
    def version(self) -> str:
        return self._version

    @property
    def hash(self) -> int:
        return self._hash

    def __repr__(self) -> str:
        return f"firmware {self.firmware_type} version {self.version} hash {self.hash}"

class ConnectStatus(Enum):
    UNKNOWN = 0
    CONNECTED = 1
    DISCONNECTED = 2

    def __str__(self) -> str:
        if self.value == ConnectStatus.CONNECTED.value:
            return 'connected'
        if self.value == ConnectStatus.DISCONNECTED.value:
            return 'disconnected'
        return 'unknown'

    def __repr__(self) -> str:
        return str(self)

class SignalStatus:
    def __init__(self, detected:bool, description:str|None=None) -> None:
        self._detected = detected
        self._description = description

    @property
    def detected(self) -> bool:
        return self._detected

    @property
    def description(self) -> str|None:
        return self._description

class AmpDolbySettings:
    """
    Dolby Digital settings for an amplifier
    """

    mode:int
    """ Dolby mode """

    pcm_upmix:bool
    """ PCM upmixing enabled """

    dolby_detected:bool
    """ Dolby 5.1 signal detected """

    pcm_upmix_active:bool
    """ PCM upmixing active """

class AmpZoneSettings:
    """
    Zone specific settings for an amplifier input/output
    """

    gain_left: int
    """ gain level left channel """

    gain_right: int
    """ gain level right channel """

    volume_min: int
    """ minimum volume level """

    volume_max: int
    """ maximum volume level """

    delay_left: int
    """ audio delay left channel (ms) """

    delay_right: int
    """ audio delay right channel (ms) """

    bass: int
    """ bass level """

    treble: int
    """ treble level """

    bridged: int
    """ bridging mode setting """

    power_mode: int
    """ auto power off setting """

    power_level: int
    """ auto power off level """

    power_timeout: int
    """ auto power off timeout """

    eq_left: list[int]
    """ equalizer left channel """

    eq_right: list[int]
    """ equalizer right channel """

    def __str__(self) -> str:
        return f"gain:{self.gain_left}/{self.gain_left} volume:{self.volume_min}/{self.volume_max} delay:{self.delay_left}/{self.delay_right} bass:{self.bass} treble:{self.treble} bridged:{self.bridged} eqleft:{self.eq_left} eqright:{self.eq_right} power:{self.power_mode} pwrlevel:{self.power_level} pwrtimeout:{self.power_timeout}"

    def __repr__(self) -> str:
        return str(self)

class V2IPStreamSource(ABC):
    """
    V2IP multicast IP address and port number
    """
    @property
    @abstractmethod
    def label(self) -> str:
        """ user friendly description of this stream """

    @property
    @abstractmethod
    def ip(self) -> str:
        """ multicast IP address """

    @property
    @abstractmethod
    def port(self) -> int:
        """ UDP port number """

class V2IPStreamSources:
    """
    All V2IP multicast IP addresses and port numbers used by a device
    """

    @property
    @abstractmethod
    def video(self) -> V2IPStreamSource:
        ''' video stream source '''

    @property
    @abstractmethod
    def audio(self) -> V2IPStreamSource:
        ''' audio stream source '''

    @property
    @abstractmethod
    def anc(self) -> V2IPStreamSource:
        ''' ancillary stream source '''

    @property
    @abstractmethod
    def arc(self) -> V2IPStreamSource|None:
        ''' audio return stream source '''

class V2IPStreamSourcesList(list[V2IPStreamSources]):
    ''' list of V2IP sources '''

class AudioFeatures:
    FEATURE_INPUT = (1 << 0)
    FEATURE_OUTPUT = (1 << 1)
    FEATURE_V2IP_TX = (1 << 2)
    FEATURE_V2IP_RX = (1 << 3)
    FEATURE_HDMI = (1 << 4)
    FEATURE_RCA = (1 << 5)
    FEATURE_SPDIF = (1 << 6)
    FEATURE_TRIGGER = (1 << 7)
    FEATURE_MUTE = (1 << 8)
    FEATURE_ROUTE_INPUT = (1 << 9)
    FEATURE_ROUTE_OUTPUT = (1 << 10)
    FEATURE_ROUTE_INPUT_NONE = (1 << 11)
    FEATURE_AMP_OUTPUT = (1 << 12)
    FEATURE_VOLUME_CONTROL = (1 << 13)
    FEATURE_GAIN_CONTROL = (1 << 14)

    def __init__(self, value:int) -> None:
        self._value = value

    @property
    def is_input(self) -> bool:
        return ((self._value & self.FEATURE_INPUT) != 0)

    @property
    def is_output(self) -> bool:
        return ((self._value & self.FEATURE_OUTPUT) != 0)

    @property
    def is_v2ip_tx(self) -> bool:
        return ((self._value & self.FEATURE_V2IP_TX) != 0)

    @property
    def is_v2ip_rx(self) -> bool:
        return ((self._value & self.FEATURE_V2IP_RX) != 0)

    @property
    def is_hdmi(self) -> bool:
        return ((self._value & self.FEATURE_HDMI) != 0)

    @property
    def is_rca(self) -> bool:
        return ((self._value & self.FEATURE_RCA) != 0)

    @property
    def is_spdif(self) -> bool:
        return ((self._value & self.FEATURE_SPDIF) != 0)

    @property
    def has_trigger(self) -> bool:
        return ((self._value & self.FEATURE_TRIGGER) != 0)

    @property
    def support_mute(self) -> bool:
        return ((self._value & self.FEATURE_MUTE) != 0)

    @property
    def support_route_input(self) -> bool:
        return ((self._value & self.FEATURE_ROUTE_INPUT) != 0)

    @property
    def support_route_output(self) -> bool:
        return ((self._value & self.FEATURE_ROUTE_OUTPUT) != 0)

    @property
    def input_route_none(self) -> bool:
        return ((self._value & self.FEATURE_ROUTE_INPUT_NONE) != 0)

    @property
    def is_amp(self) -> bool:
        return ((self._value & self.FEATURE_AMP_OUTPUT) != 0)

    @property
    def support_volume_control(self) -> bool:
        return ((self._value & self.FEATURE_VOLUME_CONTROL) != 0)

    @property
    def support_gain_control(self) -> bool:
        return ((self._value & self.FEATURE_GAIN_CONTROL) != 0)

    @property
    def features(self) -> list[str]:
        rv = []
        if self.is_input:
            rv.append('input')
        if self.is_output:
            rv.append('output')
        if self.is_v2ip_tx:
            rv.append('v2ip tx')
        if self.is_v2ip_rx:
            rv.append('v2ip rx')
        if self.is_hdmi:
            rv.append('hdmi')
        if self.is_rca:
            rv.append('rca')
        if self.is_spdif:
            rv.append('spdif')
        if self.has_trigger:
            rv.append('trigger')
        if self.support_mute:
            rv.append('mute')
        if self.support_route_input:
            rv.append('route input')
        if self.support_route_output:
            rv.append('route output')
        if self.input_route_none:
            rv.append('input none')
        if self.is_amp:
            rv.append('amp')
        if self.support_volume_control:
            rv.append('volume')
        if self.support_gain_control:
            rv.append('gain')
        return rv

    def __str__(self) -> str:
        return str(self.features)

    def __repr__(self) -> str:
        return str(self)

class AudioChangeSource(ABC):
    @property
    @abstractmethod
    def source_uid(self) -> MxrDeviceUid|None:
        pass

    @property
    @abstractmethod
    def target_uid(self) -> MxrDeviceUid|None:
        pass

    @property
    @abstractmethod
    def source_id(self) -> int|None:
        pass

    @property
    @abstractmethod
    def target_id(self) -> int|None:
        pass

class AudioEndpoint(ABC):
    def __init__(self, container:'AudioEndpoints') -> None:
        self.children:list[AudioEndpoint] = []
        self.parent:AudioEndpoint|None = None
        self.container = container
        self._bay:'BayBase|None' = None
        self._linked_uid:MxrDeviceUid|None = None
        self._linked_ep:int|None = None

    def add_child(self, ep:'AudioEndpoint') -> None:
        if not ep in self.children:
            self.children.append(ep)

    def set_parent(self, ep:'AudioEndpoint') -> None:
        self.parent = ep

    def get(self, endpoint:int) -> 'AudioEndpoint|None':
        if (self.id == endpoint):
            return self
        for child in self.children:
            ep = child.get(endpoint=endpoint)
            if (ep is not None):
                return ep
        return None

    def link(self, registry:'DeviceRegistry') -> 'AudioEndpoint|None':
        if (self._linked_uid is None) or self._linked_uid.empty or (self._linked_ep is None):
            return None
        dev = registry.get_by_uid(self._linked_uid)
        if (dev is None):
            return None
        return dev.audio_endpoint_by_id(self._linked_ep)

    def set_link(self, uid:MxrDeviceUid|None, ep:int|None) -> None:
        self._linked_uid = uid
        self._linked_ep = ep

    @property
    def bay(self) -> 'BayBase|None':
        return self._bay

    @bay.setter
    def bay(self, bay:'BayBase') -> None:
        self._bay = bay
        for child in self.children:
            child.bay = bay

    @property
    @abstractmethod
    def id(self) -> int:
        pass

    @property
    @abstractmethod
    def features(self) -> AudioFeatures:
        pass

    @property
    @abstractmethod
    def is_v2ip(self) -> bool:
        pass

    @property
    @abstractmethod
    def is_hdmi(self) -> bool:
        pass

    @property
    @abstractmethod
    def is_spdif(self) -> bool:
        pass

    @property
    @abstractmethod
    def is_rca(self) -> bool:
        pass

    @property
    @abstractmethod
    def is_input(self) -> bool:
        pass

    @property
    @abstractmethod
    def is_output(self) -> bool:
        pass

    @property
    @abstractmethod
    def address(self) -> V2IPStreamSource|None:
        pass

    @property
    @abstractmethod
    def parent_id(self) -> int|None:
        pass

    @property
    @abstractmethod
    def inputs_available(self) -> list['AudioEndpoint']:
        pass

    @property
    @abstractmethod
    def input(self) -> 'AudioEndpoint|None':
        pass

class AudioLink(ABC):
    @cached_property
    @abstractmethod
    def endpoint(self) -> int:
        pass

    @cached_property
    @abstractmethod
    def link_endpoint(self) -> int:
        pass

    @cached_property
    @abstractmethod
    def link_device(self) -> MxrDeviceUid|None:
        pass

    @cached_property
    @abstractmethod
    def valid(self) -> bool:
        pass

class AudioLinks(ABC):
    @cached_property
    @abstractmethod
    def nb_links(self) -> int:
        pass

    @cached_property
    @abstractmethod
    def entries(self) -> list[AudioLink]:
        pass

class AudioEndpoints:
    def __init__(self) -> None:
        self.endpoints:dict[int,AudioEndpoint] = {}

    def add(self, endpoint:AudioEndpoint) -> None:
        self.endpoints[endpoint.id] = endpoint

    def get(self, id:int) -> AudioEndpoint|None:
        if id in self.endpoints:
            return self.endpoints[id]
        return None

    @cached_property
    def as_list(self) -> list[AudioEndpoint]:
        return [ep for _, ep in self.endpoints.items()]

    @cached_property
    def as_tree(self) -> list[AudioEndpoint]:
        rv:list[AudioEndpoint] = []
        for _, ep in self.endpoints.items():
            if (ep.parent is None):
                rv.append(ep)
        return rv

    @cached_property
    def tree_first_input(self) -> AudioEndpoint|None:
        for ep in self.as_tree:
            if ep.is_input:
                return ep
        return None

    @cached_property
    def tree_first_output(self) -> AudioEndpoint|None:
        for ep in self.as_tree:
            if ep.is_output:
                return ep
        return None

    def __eq__(self, value: object) -> bool:
        if (not isinstance(value, AudioEndpoints)):
            return False
        if (len(self.endpoints) != len(value.endpoints)):
            return False
        for k, v in self.endpoints.items():
            if not k in value.endpoints:
                return False
            if value.endpoints[k] != v:
                return False
        return True

    def __str__(self) -> str:
        return str(self.as_tree)

    def __repr__(self) -> str:
        return str(self)

class DeviceList(list[MxrDeviceUid]):
    def __init__(self, data:bytes|None=None):
        super().__init__(self)
        if (data is None):
            return
        while len(data) >= 16:
            self.append(MxrDeviceUid(data[0:16]))
            data = data[16:]

class FilteredDevices(DeviceList):
    ''' list of filtered devices '''

class BayMirrorStatus:
    def __init__(self, target:MxrBayUid|None=None) -> None:
        self._target = target

    @property
    def target(self) -> MxrBayUid|None:
        return self._target

    @property
    def is_mirroring(self) -> bool:
        return (self._target is not None)

    def __eq__(self, value: object) -> bool:
        if (self._target is None):
            return (value is None)
        if (not isinstance(value, BayMirrorStatus)):
            return False
        if (value.target is None):
            return False
        return (value.target == self.target)

    def __str__(self) -> str:
        return f"target={self.target}"

    def __repr__(self) -> str:
        return str(self)

class BayBase(ABC):
    """
    A bay (input/output) of an mx_remote device
    """

    @property
    @abstractmethod
    def status(self) -> DeviceStatus:
        '''bay status'''

    @property
    @abstractmethod
    def callbacks(self) -> 'MxrCallbacks':
        ''' mx_remote callbacks '''

    @property
    @abstractmethod
    def device(self) -> 'DeviceBase':
        ''' device to which this bay belongs '''

    @property
    @abstractmethod
    def bay_uid(self) -> MxrBayUid:
        ''' unique id of this bay '''

    @property
    @abstractmethod
    def port(self) -> int:
        ''' port number '''

    @property
    @abstractmethod
    def is_local(self) -> bool:
        ''' local or remote bay '''

    @property
    @abstractmethod
    def bay_name(self) -> str:
        ''' bay name for logging (mode / number)'''

    @property
    @abstractmethod
    def user_name(self) -> str:
        ''' name set up by the user '''

    @user_name.setter
    @abstractmethod
    def user_name(self, val:str) -> None:
        ''' mx_remote update of the user set name '''

    @property
    @abstractmethod
    def has_default_name(self) -> bool:
        ''' default name not changed by the user '''

    @property
    @abstractmethod
    def edid_profile(self) -> EdidProfile|None:
        ''' edid profile used by the source '''

    @property
    @abstractmethod
    def bay_label(self) -> str:
        '''user friendly label for this bay'''

    @property
    @abstractmethod
    def features(self) -> BayFeaturesMask:
        '''List of supported features as strings'''

    @property
    @abstractmethod
    def is_v2ip_remote(self) -> bool:
        '''V2IP remote bay'''

    @property
    @abstractmethod
    def is_v2ip_source(self) -> bool:
        pass

    @property
    @abstractmethod
    def is_v2ip_sink(self) -> bool:
        pass

    @property
    @abstractmethod
    def dolby_input(self) -> str|None:
        '''Dolby Digital input'''

    @property
    def dolby_input_bay(self) -> 'BayBase|None':
        '''Dolby Digital input bay used by this audio output bay'''

    @property
    @abstractmethod
    def has_volume_control(self) -> bool:
        '''Volume control supported by this bay'''

    @property
    @abstractmethod
    def is_input(self) -> bool:
        '''Source bay'''

    @property
    @abstractmethod
    def is_output(self) -> bool:
        '''Sink bay'''

    @property
    @abstractmethod
    def mode(self) -> str:
        '''Bay mode name'''

    @property
    def other_mode(self) -> str|None:
        '''Bay mode name of the opposite side (so Output if this bay is an Input)'''

    @property
    @abstractmethod
    def bay(self) -> int:
        '''Bay number'''

    @property
    @abstractmethod
    def available(self) -> bool:
        '''True if available'''

    @property
    @abstractmethod
    def is_hdmi(self) -> bool:
        '''True if this is an HDMI input or output'''

    @property
    @abstractmethod
    def is_hdbaset(self) -> bool:
        '''True if this is a HDBaseT bay'''

    @property
    @abstractmethod
    def is_audio(self) -> bool:
        '''True if this is audio input or output bay'''

    @property
    @abstractmethod
    def video_source(self) -> 'BayBase|None':
        '''Current video source (output only)'''

    @property
    @abstractmethod
    def available_video_sources(self) -> 'list[BayBase]':
        '''Video sources that can be selected'''

    @property
    @abstractmethod
    def audio_source(self) -> 'BayBase|None':
        '''Current audio source (output only)'''

    @property
    @abstractmethod
    def available_audio_sources(self) -> 'list[BayBase]':
        '''Audio sources that can be selected'''

    @property
    @abstractmethod
    def powered_on(self) -> bool:
        '''True the connected device supports CEC and reports that the device is powered on'''

    @property
    @abstractmethod
    def powered_off(self) -> bool:
        '''True the connected device supports CEC and reports that the device is powered off'''

    @property
    @abstractmethod
    def power_status(self) -> PowerStatus:
        '''Power status'''

    @property
    @abstractmethod
    def faulty(self) -> bool:
        '''True if a fault was detected'''

    @property
    @abstractmethod
    def hidden(self) -> bool:
        '''True if flagged as hidden'''

    @property
    @abstractmethod
    def poe_powered(self) -> bool:
        '''True if PoE has been enabled (HDBaseT only)'''

    @property
    @abstractmethod
    def hdbt_connected(self) -> bool:
        '''HDBaseT receiver connected'''

    @property
    @abstractmethod
    def signal_detected(self) -> bool:
        '''Video signal detected (matrix/oneip) or audio signal detected (proamp)'''

    @property
    @abstractmethod
    def signal_type(self) -> str:
        '''Audio or video signal type'''

    @property
    @abstractmethod
    def hpd_detected(self) -> bool:
        '''Hotplug detected'''

    @property
    @abstractmethod
    def cec_detected(self) -> bool:
        '''Connected device supports HDMI-CEC'''

    @property
    @abstractmethod
    def mirroring(self) -> BayMirrorStatus:
        '''Bay mirroring status'''

    @property
    @abstractmethod
    def filtered(self) -> FilteredDevices:
        '''Filtered bays'''

    @property
    @abstractmethod
    def link_online(self) -> bool:
        pass

    @property
    @abstractmethod
    def arc(self) -> str:
        '''Audio return channel status'''

    @property
    @abstractmethod
    def volume(self) -> int|None:
        '''Current volume level (percentage)'''

    @property
    @abstractmethod
    def muted(self) -> bool|None:
        '''True if audio has been muted'''

    @property
    @abstractmethod
    def online(self) -> bool:
        '''True if online'''

    @property
    @abstractmethod
    def rebooting(self) -> bool:
        '''True if rebooting'''

    @property
    @abstractmethod
    def booting(self) -> bool:
        '''True if booting'''

    @property
    @abstractmethod
    def is_primary(self) -> bool:
        '''True if this bay is the primary bay in a mirroring setup'''

    @property
    @abstractmethod
    def primary(self) -> 'BayBase':
        '''The primary bay in a mirroring setup'''

    @property
    @abstractmethod
    def v2ip_source(self) -> V2IPStreamSources|None:
        '''V2IP source address information'''

    @property
    @abstractmethod
    def v2ip_uid(self) -> MxrDeviceUid|None:
        '''Remote V2IP device uid'''

    @property
    @abstractmethod
    def v2ip_device(self) -> 'DeviceBase|None':
        '''Remote V2IP device'''

    @property
    @abstractmethod
    def link(self) -> 'BayLink|None':
        '''mx-remote virtual link configuration (proamp<->matrix)'''

    @property
    @abstractmethod
    def linked_bay(self) -> 'BayBase|None':
        '''linked bay if an mx-remote virtual link has been set up'''

    @property
    @abstractmethod
    def link_configured(self) -> bool:
        '''mx-remote virtual link configured (proamp<->matrix)'''

    @property
    @abstractmethod
    def link_connected(self) -> bool:
        '''mx-remote virtual link connected (proamp<->matrix)'''

    @property
    @abstractmethod
    def volume_status(self) -> VolumeMuteStatus|None:
        '''volume and mute status'''

    @property
    @abstractmethod
    def amp_settings(self) -> AmpZoneSettings|None:
        '''proamp zone settings'''

    @abstractmethod
    def set_zone_settings(self, settings:AmpZoneSettings) -> bool:
        pass

    @property
    @abstractmethod
    def encoder_disabled(self) -> bool:
        ''' video/audio encoder disabled '''

    @property
    @abstractmethod
    def decoder_disabled(self) -> bool:
        ''' video/audio decoder disabled '''

    @property
    @abstractmethod
    def audio_endpoint(self) -> AudioEndpoint|None:
        ''' primary audio endpoint. currently v2ip only '''

    @property
    @abstractmethod
    def rc_type(self) -> RCType|None:
        pass

    @abstractmethod
    async def set_name(self, name:str) -> bool:
        '''change the name of abay'''

    @abstractmethod
    async def tx_action(self, action:RCAction) -> bool:
        pass

    @abstractmethod
    async def select_video_source(self, port:int, opt:bool=True) -> bool:
        '''change the video source of an output bay'''

    @abstractmethod
    async def select_video_source_by_user_name(self, name:str, opt:bool=True) -> bool:
        '''change the video source of an output bay'''

    @abstractmethod
    async def select_audio_source(self, source:'int|BayBase|str|None', endpoint:str|None=None) -> bool:
        '''change the audio source of an output bay'''

    @abstractmethod
    async def select_edid_profile(self, profile:EdidProfile) -> bool:
        '''change the edid profile of an input bay'''

    @abstractmethod
    async def set_hidden(self, hidden:bool) -> bool:
        '''change the hidden status of a bay'''

    @abstractmethod
    async def power_on(self) -> bool:
        '''power on the remote device if CEC is supported'''

    @abstractmethod
    async def power_off(self) -> bool:
        '''power off the remote device if CEC is supported'''

    @abstractmethod
    def volume_up(self) -> bool:
        '''change the volume if supported'''

    @abstractmethod
    def volume_down(self) -> bool:
        '''change the volume if supported'''

    @abstractmethod
    def volume_set(self, volume:int, muted:bool|None=None) -> bool:
        '''change the volume if supported'''

    @abstractmethod
    def mute_set(self, mute:bool) -> bool:
        '''change the mute status if supported'''

    @abstractmethod
    async def send_key(self, key:int) -> bool:
        '''send a remote control key press to the device'''

    @abstractmethod
    def register_callback(self, callback:'Callable[[BayBase], None]') -> None:
         '''register a callback, called when the bay state changed'''

    @abstractmethod
    def unregister_callback(self, callback:'Callable[[BayBase], None]') -> None:
         '''unregister a callback'''

    @abstractmethod
    def call_callbacks(self) -> None:
        '''notify callbacks that this bay has changed'''

    @abstractmethod
    def on_mxr_update(self, data:Any) -> None:
        pass

class SelectedBays:
    def __init__(self, video:BayBase|None, audio:BayBase|None) -> None:
        self._video = video
        self._audio = audio

    @property
    def video(self) -> BayBase|None:
        return self._video

    @property
    def audio(self) -> BayBase|None:
        return self._audio

class DeviceFeatures:
    """
    Features and status of an mx_remote device
    """

    def __init__(self, value:int) -> None:
        self._features = value

    @property
    def value(self) -> int:
        return self._features

    @property
    def ir_rx(self) -> bool:
        """ IR receive supported """
        return ((self._features & MXR_DEVICE_FEATURE_IR_RX) != 0)

    @property
    def ir_tx(self) -> bool:
        """ IR blast supported """
        return ((self._features & MXR_DEVICE_FEATURE_IR_TX) != 0)

    @property
    def cec(self) -> bool:
        """ HDMI-CEC supported """
        return ((self._features & MXR_DEVICE_FEATURE_CEC) != 0)

    @property
    def v2ip_source(self) -> bool:
        """ V2IP source """
        return ((self._features & MXR_DEVICE_FEATURE_V2IP_SOURCE) != 0)

    @property
    def v2ip_sink(self) -> bool:
        """ V2IP sink """
        return ((self._features & MXR_DEVICE_FEATURE_V2IP_SINK) != 0)

    @property
    def video_routing(self) -> bool:
        """ video routing supported """
        return ((self._features & MXR_DEVICE_FEATURE_VIDEO_ROUTING) != 0)

    @property
    def audio_routing(self) -> bool:
        """ (independent) audio routing supported """
        return ((self._features & MXR_DEVICE_FEATURE_AUDIO_ROUTING) != 0)

    @property
    def volume_control(self) -> bool:
        """ volume control supported """
        return ((self._features & MXR_DEVICE_FEATURE_VOLUME_CONTROL) != 0)

    @property
    def arc(self) -> bool:
        """ audio return channel supported """
        return ((self._features & MXR_DEVICE_FEATURE_AUDIO_RETURN) != 0)

    @property
    def remote_control(self) -> bool:
        """ remote contro pass through supported """
        return ((self._features & MXR_DEVICE_FEATURE_REMOTE_CONTROL) != 0)

    @property
    def setup_completed(self) -> bool:
        """ device setup flagged as completed """
        return ((self._features & MXR_DEVICE_FEATURE_SETUP_COMPLETED) != 0)

    @property
    def mesh_master(self) -> bool:
        """ master device of a V2IP mesh """
        return ((self._features & MXR_DEVICE_FEATURE_MESH_MASTER) != 0)

    @property
    def status_notify(self) -> bool:
        """ notification registered in system status """
        return ((self._features & MXR_DEVICE_FEATURE_STATUS_NOTIFY) != 0)

    @property
    def status_warning(self) -> bool:
        """ warning registered in system status """
        return ((self._features & MXR_DEVICE_FEATURE_STATUS_WARNING) != 0)

    @property
    def status_error(self) -> bool:
        """ error registered in system status """
        return ((self._features & MXR_DEVICE_FEATURE_STATUS_ERROR) != 0)

    @property
    def status_rebooting(self) -> bool:
        """ device is going to reboot """
        return ((self._features & MXR_DEVICE_FEATURE_STATUS_REBOOTING) != 0)

    @property
    def mesh_member(self) -> bool:
        """ member of a V2IP mesh """
        return ((self._features & MXR_DEVICE_FEATURE_MESH_MEMBER) != 0)

    @property
    def audio_amp(self) -> bool:
        """ audio amplifier """
        return ((self._features & MXR_DEVICE_FEATURE_AUDIO_AMPLIFIER) != 0)

    @property
    def booting(self) -> bool:
        """ device is booting """
        return ((self._features & MXR_DEVICE_FEATURE_BOOTING) != 0)

    @property
    def manager(self) -> bool:
        """ device is allowed to manage mx_remote devices """
        return ((self._features & MXR_DEVICE_FEATURE_MANAGER) != 0)

    @property
    def power_save(self) -> bool:
        """ device is in power saving mode """
        return ((self._features & MXR_DEVICE_FEATURE_STATUS_POWER_SAVE) != 0)

    @property
    def mesh_support(self) -> bool:
        """ device supports mesh operations """
        return ((self._features & MXR_DEVICE_FEATURE_MESH) != 0)

    @property
    def multiviewer(self) -> bool:
        """ device is a multiviewer """
        return ((self._features & MXR_DEVICE_FEATURE_MULTIVIEWER) != 0)

    @property
    def crashed_recently(self) -> bool:
        """ device crash caused this boot """
        return ((self._features & MXR_DEVICE_FEATURE_STATUS_CRASHED) != 0)

    @property
    def boot_bit(self) -> bool:
        """ bit that is flipped every time the device reboots """
        return ((self._features & MXR_DEVICE_FEATURE_BOOT_BIT) != 0)

    def __eq__(self, value: object) -> bool:
        if (not isinstance(value, DeviceFeatures)):
            return False
        return self._features == value._features

    @cached_property
    def features(self) -> list[str]:
        """ supported features as list of string descriptions """
        ft:list[str] = []
        if self.ir_rx:
            ft.append('IR RX')
        if self.ir_tx:
            ft.append('IR TX')
        if self.cec:
            ft.append('CEC')
        if self.v2ip_source:
            ft.append('V2IP source')
        if self.v2ip_sink:
            ft.append('V2IP sink')
        if self.video_routing:
            ft.append('video routing')
        if self.audio_routing:
            ft.append('audio routing')
        if self.volume_control:
            ft.append('volume control')
        if self.arc:
            ft.append('ARC')
        if self.remote_control:
            ft.append('remote control')
        if self.setup_completed:
            ft.append('setup completed')
        if self.mesh_master:
            ft.append('mesh master')
        if self.status_notify:
            ft.append('status notify')
        if self.status_warning:
            ft.append('status warning')
        if self.status_error:
            ft.append('status error')
        if self.status_rebooting:
            ft.append('status rebooting')
        if self.mesh_member:
            ft.append('mesh member')
        if self.audio_amp:
            ft.append('audio amp')
        if self.booting:
            ft.append('booting')
        if self.manager:
            ft.append('manager')
        return ft

    def __str__(self) -> str:
        return str(self.features)

    def __repr__(self) -> str:
        return str(self)

class DeviceV2IPScalingSettings(ABC):
    @property
    @abstractmethod
    def mode(self) -> int:
        pass

    @property
    @abstractmethod
    def refresh(self) -> int:
        pass

    @property
    @abstractmethod
    def flags(self) -> int:
        pass

class DeviceV2IPDetails:
    """ V2IP stream source details for a device """
    def __init__(self, video:V2IPStreamSource|None, audio:V2IPStreamSource|None, anc:V2IPStreamSource|None, arc:V2IPStreamSource|None, tx_rate:int|None, scaling:DeviceV2IPScalingSettings|None) -> None:
        self._video = video
        self._audio = audio
        self._anc = anc
        self._arc = arc
        self._tx_rate = tx_rate
        self._scaling = scaling

    @property
    def has_config(self) -> bool:
        return False

    @property
    def video(self) -> V2IPStreamSource|None:
        return self._video

    @property
    def audio(self) -> V2IPStreamSource|None:
        return self._audio

    @property
    def anc(self) -> V2IPStreamSource|None:
        return self._anc

    @property
    def arc(self) -> V2IPStreamSource|None:
        return self._arc

    @property
    def tx_rate(self) -> int|None:
        return self._tx_rate

    @property
    def scaling(self) -> DeviceV2IPScalingSettings|None:
        return self._scaling

class UtpLinkErrorStatus(ABC):
    ''' UTP link error status bits '''

    @property
    @abstractmethod
    def in_error(self) -> bool:
        ''' rx errors detected '''

    @property
    @abstractmethod
    def in_fcs_error(self) -> bool:
        ''' rx FCS errors detected '''

    @property
    @abstractmethod
    def in_collision(self) -> bool:
        ''' rx collisions detected '''

    @property
    @abstractmethod
    def out_deferred(self) -> bool:
        ''' tx deferred detected '''

    @property
    @abstractmethod
    def out_excessive(self) -> bool:
        ''' tx excessive detected '''

    @property
    @abstractmethod
    def polarity_error(self) -> bool:
        ''' polarity differences between pairs detected '''

    @property
    @abstractmethod
    def skew_warning(self) -> bool:
        ''' clock skew > 8 detected '''

    @property
    @abstractmethod
    def length_warning(self) -> bool:
        ''' different pair lengths detected '''

class UtpCableStatus(ABC):
    '''' UTP cable pair status '''

    @property
    @abstractmethod
    def polarity(self) -> bool:
        ''' positive or negative polarity '''

    @property
    @abstractmethod
    def pair(self) -> int:
        ''' pair number '''

    @property
    @abstractmethod
    def skew(self) -> int:
        ''' detected clock skew '''

    @property
    @abstractmethod
    def length(self) -> int:
        ''' detected length in meters '''

class NetworkPortStatus(ABC):
    ''' detailed status of a network port'''
    
    @cached_property
    @abstractmethod
    def port(self) -> int:
        '''port number'''

    @cached_property
    @abstractmethod
    def errors(self) -> UtpLinkErrorStatus|None:
        ''' link error status '''

    @cached_property
    @abstractmethod
    def vct_status(self) -> list[str]|None:
        ''' virtual cable test results '''

    @cached_property
    @abstractmethod
    def link_speed(self) -> UtpLinkSpeed:
        ''' link speed '''

    @cached_property
    @abstractmethod
    def link_full_duplex(self) -> bool:
        ''' full duplex or half duplex '''

    @cached_property
    @abstractmethod
    def name(self) -> str:
        ''' description of the port '''

    @cached_property
    @abstractmethod
    def ip(self) -> str|None:
        ''' IP address '''

    @cached_property
    @abstractmethod
    def querier(self) -> str|None:
        ''' detected IGMP querier or 0.0.0.0 if not detected'''

    @cached_property
    @abstractmethod
    def cable_status(self) -> list[UtpCableStatus]|None:
        ''' utp cable pair status '''

    @cached_property
    @abstractmethod
    def mac_address(self) -> str|None:
        ''' mac address of supported devices '''

class SystemTemperature(list[int]):
    ''' system temperature '''

class DeviceBase(ABC):
    ''' an mx_remote device on the network '''

    @property
    @abstractmethod
    def status(self) -> DeviceStatus:
        '''device status'''

    @property
    @abstractmethod
    def name(self) -> str:
        '''device name'''

    @property
    @abstractmethod
    def registry(self) -> 'DeviceRegistry':
        '''local device information registry'''

    @property
    @abstractmethod
    def configuration_complete(self) -> bool:
        '''check whether all configuration info for this device has been received'''

    @property
    @abstractmethod
    def model_name(self) -> str:
        '''Model name'''

    @property
    @abstractmethod
    def callbacks(self) -> 'MxrCallbacks':
        '''callbacks for this device'''

    @property
    @abstractmethod
    def remote_id(self) -> MxrDeviceUid:
        '''unique id'''

    @property
    @abstractmethod
    def version(self) -> str:
        '''firmware version'''

    @property
    @abstractmethod
    def address(self) -> str:
        '''IP address'''

    @property
    @abstractmethod
    def features(self) -> DeviceFeatures|None:
        '''supported features'''

    @property
    @abstractmethod
    def serial(self) -> str:
        '''serial number'''

    @property
    @abstractmethod
    def bays(self) -> dict[int, BayBase]:
        '''device inputs and outputs'''

    @property
    @abstractmethod
    def inputs(self) -> dict[str, BayBase]:
        '''device inputs'''

    @property
    @abstractmethod
    def nb_inputs(self) -> int:
        '''number of inputs'''

    @property
    @abstractmethod
    def first_input(self) -> BayBase|None:
        '''the first local input'''

    @property
    @abstractmethod
    def outputs(self) -> dict[str, BayBase]:
        '''device outputs'''

    @property
    @abstractmethod
    def nb_outputs(self) -> int:
        '''number of outputs'''

    @property
    @abstractmethod
    def first_output(self) -> BayBase|None:
        '''the first local output'''

    @property
    @abstractmethod
    def online(self) -> bool:
        '''True if online'''

    @property
    @abstractmethod
    def rebooting(self) -> bool:
        '''True if rebooting'''

    @property
    @abstractmethod
    def booting(self) -> bool:
        '''True if booting'''

    @property
    @abstractmethod
    def is_amp(self) -> bool:
        '''True if as an audio amplifier'''

    @property
    @abstractmethod
    def amp_dolby_channels(self) -> int:
        '''number of dolby input channels'''

    @property
    @abstractmethod
    def nb_hdbt(self) -> int:
        '''number of HDBaseT inputs and outputs'''

    @property
    @abstractmethod
    def is_v2ip(self) -> bool:
        '''True if this a OneIP device'''

    @property
    @abstractmethod
    def has_local_source(self) -> bool:
         '''True if this device has at least 1 local source'''

    @property
    @abstractmethod
    def has_local_sink(self) -> bool:
         '''True if this device has at least 1 local sink'''

    @property
    @abstractmethod
    def is_video_matrix(self) -> bool:
        '''True if this device supports video matrixing'''

    @property
    @abstractmethod
    def is_audio_matrix(self) -> bool:
        '''True if thie device supports audio matrixing'''

    @property
    @abstractmethod
    def temperatures(self) -> dict[str,int]:
        ''' temperature sensor reports '''

    @property
    @abstractmethod
    def v2ip_sources(self) -> V2IPStreamSourcesList|None:
        '''V2IP stream source addresses'''

    @property
    @abstractmethod
    def v2ip_stats(self) -> V2IPDeviceStats|None:
         '''V2IP encoder/decoder statistics'''

    @property
    @abstractmethod
    def v2ip_details(self) -> DeviceV2IPDetails|None:
        '''V2IP encoder/decoder configuration'''

    @property
    @abstractmethod
    def v2ip_source_local(self) -> V2IPStreamSources|None:
         ''' local v2ip source addresses '''

    @property
    @abstractmethod
    def mesh_master(self) -> 'DeviceBase|None':
        '''The device that is the master device in the V2IP mesh to which this device belongs'''

    @mesh_master.setter
    @abstractmethod
    def mesh_master(self, master:MxrDeviceUid) -> None:
        '''Change the master device of this device'''

    @property
    @abstractmethod
    def protocol(self) -> int:
        pass

    @property
    @abstractmethod
    def is_mesh_master(self) -> bool:
        '''True if this device is the master device of a V2IP mesh'''

    @property
    @abstractmethod
    def is_mesh_member(self) -> bool:
        '''True if this device is a member of a V2IP mesh'''

    @property
    @abstractmethod
    def is_oneip_multiviewer(self) -> bool:
        '''True if this device is a OneIP Multiviewer'''

    @property
    @abstractmethod
    def is_oneip_tz(self) -> bool:
        '''True if this device is a OneIP Transceiver'''

    @property
    @abstractmethod
    def is_oneip_tx(self) -> bool:
        '''True if this device is a OneIP Transmitter'''

    @property
    @abstractmethod
    def is_oneip_rx(self) -> bool:
        '''True if this device is a OneIP Receiver'''

    @property
    @abstractmethod
    def crashed_recently(self) -> bool:
        ''' True if a crash caused this device to reboot '''

    @property
    @abstractmethod
    def dolby_settings(self) -> AmpDolbySettings|None:
        '''Dolby Digital settings (proamp)'''

    @property
    @abstractmethod
    def v2ip_firmware_versions(self) -> dict[FirmwareType,FirmwareVersion]|None:
        '''V2IP FPGA firmware versions'''

    @property
    @abstractmethod
    def mac_address(self) -> str|None:
        pass

    @abstractmethod
    def audio_endpoint_by_name(self, name:str) -> AudioEndpoint|None:
        pass

    @abstractmethod
    def audio_endpoint_by_id(self, id:int) -> AudioEndpoint|None:
        pass

    @abstractmethod
    def v2ip_source(self, bay:BayBase) -> V2IPStreamSources|None:
        '''Get the V2IP source addresses for the given bay'''

    @abstractmethod
    def get_by_portnum(self, portnum: int) -> BayBase|None:
        '''Get the bay with the given number on this device'''

    @abstractmethod
    def get_by_portname(self, portname: str) -> BayBase|None:
        '''Get the bay with the given port name (not user set name) on this device'''

    @abstractmethod
    def get_by_mode_bay(self, mode:str, bay: int) -> BayBase|None:
        pass

    @property
    @abstractmethod
    def network_status(self) -> dict[int, NetworkPortStatus]:
        '''network status for all ports'''

    @property
    @abstractmethod
    def status_message(self) -> str:
        '''system health status'''

    @abstractmethod
    def on_link_config_received(self) -> None:
        '''internal callback'''

    @abstractmethod
    async def get_api(self, uri:str) -> Any:
        '''call an HTTP API method and return the result'''

    @abstractmethod
    def register_callback(self, callback:'Callable[[DeviceBase],None]') -> None:
         '''register a callback, called when the device state changed'''

    @abstractmethod
    def unregister_callback(self, callback:'Callable[[DeviceBase],None]') -> None:
         '''unregister a callback'''

    @abstractmethod
    async def reboot(self) -> bool:
        '''reboot this device'''

    @abstractmethod
    async def mesh_promote(self) -> bool:
        '''promote to mesh master'''

    @abstractmethod
    async def mesh_remove(self) -> bool:
        '''remove from mesh'''

    @abstractmethod
    async def read_stats(self, enable:bool) -> bool:
        '''start or stop dumping stats'''

    @abstractmethod
    async def get_log(self) -> str|None:
        '''read the log from the device and return it as string'''

    @abstractmethod
    def on_mxr_update(self, data:Any) -> None:
        pass

    @property
    @abstractmethod
    def multiviewer(self) -> 'Multiviewer':
        pass

class Multiviewer(ABC):
    @property
    @abstractmethod
    def device(self) -> DeviceBase:
        pass

    @property
    @abstractmethod
    def mcu_version(self) -> str:
        pass

    @property
    @abstractmethod
    def scaler_version(self) -> str:
        pass

    @property
    @abstractmethod
    def view_mode(self) -> MultiviewerViewMode:
        pass

    @abstractmethod
    def video_source(self, screen:int) -> MultiviewerSource:
        pass

    @property
    @abstractmethod
    def audio_source(self) -> MultiviewerSource:
        pass

    @property
    @abstractmethod
    def audio_volume(self) -> int:
        pass

    @property
    @abstractmethod
    def audio_muted(self) -> MultiviewerBoolSetting:
        pass

    @property
    @abstractmethod
    def edid_template(self) -> MultiviewerEDIDTemplate:
        pass

    @property
    @abstractmethod
    def remote_control(self) -> MultiviewerSource:
        pass

    @property
    @abstractmethod
    def pip_size(self) -> MultiviewerPipSize:
        pass

    @property
    @abstractmethod
    def pip_position(self) -> MultiviewerPipPosition:
        pass

    @property
    @abstractmethod
    def screen_aspect(self) -> MultiviewerAspectRatio:
        pass

    @property
    @abstractmethod
    def auto_switch(self) -> MultiviewerBoolSetting:
        pass

    @property
    @abstractmethod
    def output_mode(self) -> MultiviewerOutputMode:
        pass

    @property
    @abstractmethod
    def output_itc_mode(self) -> MultiviewerITCMode:
        pass

    @property
    @abstractmethod
    def hdcp_mode(self) -> MultiviewerHDCPMode:
        pass

    @abstractmethod
    def connected_source(self, input:int) -> MxrDeviceUid|None:
        pass

    @abstractmethod
    async def set_view_mode(self, view_mode:MultiviewerViewMode) -> bool:
        pass

    @abstractmethod
    async def set_video_source(self, screen:int, source:MultiviewerSource) -> bool:
        pass

    @abstractmethod
    async def set_audio_source(self, source:MultiviewerSource) -> bool:
        pass

    @abstractmethod
    async def set_audio_volume(self, volume:int, muted:bool) -> bool:
        pass

    @abstractmethod
    async def set_edid_template(self, edid:MultiviewerEDIDTemplate) -> bool:
        pass

    @abstractmethod
    async def set_remote_control(self, source:MultiviewerSource) -> bool:
        pass

    @abstractmethod
    async def set_pip_size(self, size:MultiviewerPipSize) -> bool:
        pass

    @abstractmethod
    async def set_pip_position(self, position:MultiviewerPipPosition) -> bool:
        pass

    @abstractmethod
    async def set_screen_aspect(self, aspect:MultiviewerAspectRatio) -> bool:
        pass

    @abstractmethod
    async def set_auto_switch(self, enable:bool) -> bool:
        pass

    @abstractmethod
    async def set_output_mode(self, mode:MultiviewerOutputMode) -> bool:
        pass

    @abstractmethod
    async def set_output_itc_mode(self, mode:MultiviewerITCMode) -> bool:
        pass

    @abstractmethod
    async def set_hdcp_mode(self, mode:MultiviewerHDCPMode) -> bool:
        pass

    @abstractmethod
    async def set_connected_source(self, input:int, source:MxrDeviceUid|None) -> bool:
        pass

    @abstractmethod
    async def auto_route(self) -> bool:
        pass

class BayLink:
    ''' a virtual mx_remote link between bays, like an amp output that's linked to a oneip sink '''

    def __init__(self, registry:'DeviceRegistry', bay:BayBase, linked_serial:str, linked_bay:str, features:int) -> None:
        self._bay = bay
        self._registry = registry
        self._linked_serial = linked_serial
        self._linked_bay = linked_bay
        self._features = features

    @property
    def serial(self) -> str:
        ''' serial number of the linked device '''
        return self._linked_serial

    @property
    def linked_bay_name(self) -> str:
        ''' bay name of the linked bay '''
        return self._linked_bay

    @property
    def bay(self) -> BayBase:
        ''' origin bay '''
        return self._bay

    @property
    def linked_bay(self) -> BayBase|None:
        ''' linked bay '''
        if not self.linked:
            return None
        return self._registry.get_bay_by_portname(remote_id=self.serial, portname=self.linked_bay_name)

    @property
    def linked(self) -> bool:
        ''' True if a link has been set up '''
        return (len(self.serial) != 0) and (len(self.linked_bay_name) != 0)

    @property
    def other_link(self) -> 'BayLink|None':
        ''' the link instance of the linked bay '''
        return self._registry.links.get(self.linked_bay)

    @property
    def connected(self) -> bool:
        ''' True if both sides have been set up '''
        other_link = self.other_link
        return (other_link is not None) and (other_link.linked) and (other_link.serial == self.bay.device.serial) and (other_link.linked_bay_name == self.bay.bay_name)

    @property
    def online(self) -> bool:
        ''' True if both sides are online '''
        if self.connected and (self.other_link is not None):
            return self.bay.device.online and self.other_link.bay.device.online
        return False

    @property
    def is_audio(self) -> bool:
        ''' True if this is an audio link '''
        m = self.features_mask
        return (m & MX_LINK_FEATURE_AUDIO_OPTICAL) != 0 or \
            (m & MX_LINK_FEATURE_AUDIO_ANALOG) != 0

    @property
    def is_video(self) -> bool:
        ''' True if this is a video link '''
        m = self.features_mask
        return (m & MX_LINK_FEATURE_VIDEO_HDMI) != 0

    @property
    def features(self) -> list[str]:
        ''' supported link features as list of string '''
        ft = []
        m = self.features_mask
        if (m & MX_LINK_FEATURE_VIDEO_HDMI):
            ft.append("HDMI")
        if (m & MX_LINK_FEATURE_AUDIO_OPTICAL):
            ft.append("optical audio")
        if (m & MX_LINK_FEATURE_AUDIO_ANALOG):
            ft.append("analog audio")
        if (m & MX_LINK_FEATURE_IR):
            ft.append("IR")
        if (m & MX_LINK_FEATURE_RC):
            ft.append("RC")
        return ft

    @property
    def features_mask(self) -> int:
        ''' supported link features as bitmask '''
        if not self.connected:
            return 0
        left = self.bay.features.mask
        right = self.linked_bay.features.mask if (self.linked_bay is not None) else 0
        rv = 0
        if (left & MX_BAY_FEATURE_HDMI_OUT):
            if (right & MX_BAY_FEATURE_HDMI_IN):
                rv |= MX_LINK_FEATURE_VIDEO_HDMI
        if (left & MX_BAY_FEATURE_HDMI_IN):
            if (right & MX_BAY_FEATURE_HDMI_OUT):
                rv |= MX_LINK_FEATURE_VIDEO_HDMI
        if (left & MX_BAY_FEATURE_AUDIO_DIG_OUT):
            if (right & MX_BAY_FEATURE_AUDIO_DIG_IN):
                rv |= MX_LINK_FEATURE_AUDIO_OPTICAL
        if (left & MX_BAY_FEATURE_AUDIO_DIG_IN):
            if (right & MX_BAY_FEATURE_AUDIO_DIG_OUT):
                rv |= MX_LINK_FEATURE_AUDIO_OPTICAL
        if (left & MX_BAY_FEATURE_AUDIO_ANA_OUT):
            if (right & MX_BAY_FEATURE_AUDIO_ANA_IN):
                rv |= MX_LINK_FEATURE_AUDIO_ANALOG
        if (left & MX_BAY_FEATURE_AUDIO_ANA_IN):
            if (right & MX_BAY_FEATURE_AUDIO_ANA_OUT):
                rv |= MX_LINK_FEATURE_AUDIO_ANALOG
        if (left & MX_BAY_FEATURE_IR_OUT):
            if (right & MX_BAY_FEATURE_IR_IN):
                rv |= MX_LINK_FEATURE_IR
        if (left & MX_BAY_FEATURE_IR_IN):
            if (right & MX_BAY_FEATURE_IR_OUT):
                rv |= MX_LINK_FEATURE_IR
        if (left & MX_BAY_FEATURE_RC_OUT):
            if (right & MX_BAY_FEATURE_RC_IN):
                rv |= MX_LINK_FEATURE_RC
        if (left & MX_BAY_FEATURE_RC_IN):
            if (right & MX_BAY_FEATURE_RC_OUT):
                rv |= MX_LINK_FEATURE_RC
        return rv

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, BayLink):
            return False
        return (self.serial == value.serial) and (self.bay == value.bay) and (self.features == value.features)

    def __str__(self) -> str:
        return f"{self.serial}:{self.bay}:{self.features}"

    def __hash__(self) -> int:
        return hash(str(self))

class BayLinks:
    ''' linked bay configurations for all devices '''

    def __init__(self, registry:'DeviceRegistry') -> None:
        self._registry = registry
        self._links:dict[MxrBayUid, BayLink] = {}

    @property
    def callbacks(self) -> 'MxrCallbacks':
        return self._registry.callbacks

    @property
    def registry(self) -> 'DeviceRegistry':
        return self._registry

    def _on_link(self, bay:BayBase, new_link:BayLink) -> None:
        if new_link.linked:
            self.callbacks.on_bay_linked(bay, new_link.serial, new_link.bay.bay_name, new_link.features_mask)
            other_bay = new_link.linked_bay
            if other_bay is not None:
                self.callbacks.on_bay_linked(other_bay, bay.device.serial, bay.bay_name, new_link.features_mask)

    def is_primary(self, bay:BayBase) -> bool:
        if not bay.bay_uid in self._links.keys():
            return True
        link = self._links[bay.bay_uid]
        other_bay = link.linked_bay
        if other_bay is None:
            return True
        if bay.device.is_amp != other_bay.device.is_amp:
            return bay.device.is_amp
        return str(bay.device.remote_id) < str(other_bay.device.remote_id)
        

    def update(self, bay:BayBase, linked_serial:str, linked_bay:str, features:int) -> None:
        new_link = BayLink(bay=bay, registry=self.registry, linked_serial=linked_serial, linked_bay=linked_bay, features=features)
        if bay.bay_uid in self._links.keys():
            old = self._links[bay.bay_uid]
            if old != new_link:
                if old.linked:
                    self.callbacks.on_bay_unlinked(bay, old.serial, old.bay.bay_name)
                    old_bay = old.linked_bay
                    if old_bay is not None:
                        self.callbacks.on_bay_unlinked(old_bay, bay.device.serial, bay.bay_name)
                self._on_link(bay=bay, new_link=new_link)
                self._links[bay.bay_uid] = new_link
        else:
            self._on_link(bay=bay, new_link=new_link)
            self._links[bay.bay_uid] = new_link

    def get(self, bay:BayBase|None) -> BayLink|None:
        if bay is None:
            return None
        if bay.bay_uid in self._links.keys():
            return self._links[bay.bay_uid]
        return None

class DeviceRegistry(ABC):
    ''' all mx_remote devices on the network '''

    @property
    @abstractmethod
    def local_ip(self) -> str|None:
         '''local ip address'''

    @property
    @abstractmethod
    def broadcast(self) -> bool:
         '''broadcast or multicast'''

    @property
    @abstractmethod
    def library_version(self) -> str:
        ''' version of the mx_remote library '''

    @property
    @abstractmethod
    def protocol_version(self) -> int:
        ''' protocol version used by this library '''

    @property
    @abstractmethod
    def net_protocol_version_max(self) -> int:
        ''' highest protocol version used by devices on the network '''

    @property
    @abstractmethod
    def net_protocol_version_min(self) -> int:
        ''' lowest protocol version used by devices on the network '''

    @property
    @abstractmethod
    def uid_raw(self) -> bytes|None:
        ''' uid of this device as bytes '''

    @cached_property
    @abstractmethod
    def uid(self) -> MxrDeviceUid:
        ''' uid of this device '''

    @property
    @abstractmethod
    def name(self) -> str:
        ''' device name '''

    @property
    @abstractmethod
    def callbacks(self) -> 'MxrCallbacks':
        ''' callbacks to call when the device is updated '''

    @abstractmethod
    def transmit(self, data: bytes) -> int:
        ''' transmit data to this device (broadcast/multicast) '''

    @property
    @abstractmethod
    def links(self) -> BayLinks:
        ''' linked bay configurations for all devices '''

    @abstractmethod
    def get_by_serial(self, serial:str) -> DeviceBase|None:
        ''' get a device by its serial number '''

    @abstractmethod
    def get_by_uid(self, remote_id:str|MxrDeviceUid|None) -> DeviceBase|None:
        ''' get a device by its unique id '''

    @abstractmethod
    def get_bay_by_portnum(self, remote_id:str|MxrDeviceUid, portnum:int) -> BayBase|None:
        ''' get a bay of a device by its unique id and port number '''

    @abstractmethod
    def get_bay_by_portname(self, remote_id:str|MxrDeviceUid, portname:str) -> BayBase|None:
        ''' get a bay of a device by its unique id and port name '''

    @abstractmethod
    def get_by_stream_ip(self, ip:str, audio:bool=False) -> BayBase|None:
        ''' get a bay of a device by its V2IP stream address '''

    @abstractmethod
    def get_audio_endpoint(self, device:MxrDeviceUid, id:int) -> AudioEndpoint|None:
        pass

    @property
    @abstractmethod
    def http_session(self) -> aiohttp.ClientSession:
        pass

    @property
    @abstractmethod
    def svd_map(self) -> SvdMap:
        pass

    @abstractmethod
    def on_mxr_update(self, data:Any) -> None:
        pass

class ConnectionCallbacks(ABC):
    @cached_property
    @abstractmethod
    def target_ip(self) -> str:
         '''target ip address'''

    @abstractmethod
    def on_connection_made(self) -> None:
        '''called when the socket was opened'''

    @abstractmethod
    def on_datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
         '''called when a datagram was received'''

class MxrCallbacks:
    ''' callbacks that can be used by an external application to get notified when a status changes '''

    def on_device_update(self, dev:DeviceBase) -> None:
        ''' called when properties of 'dev' have been updated '''
        pass

    def on_bay_update(self, bay:BayBase) -> None:
        ''' called when properties of 'bay' have been updated '''
        pass

    def on_device_config_changed(self, dev:DeviceBase) -> None:
        ''' called when device configuration properties of 'dev' have been updated '''
        self.on_device_update(dev)

    def on_device_config_complete(self, dev:DeviceBase) -> None:
        ''' called when device configuration of 'dev' had been received fully '''
        _LOGGER.debug(f"{dev} configuration complete")
        self.on_device_update(dev)

    def on_device_online_status_changed(self, dev:DeviceBase, online:bool) -> None:
        ''' called when the online status of 'dev' changed '''
        _LOGGER.debug(f"{dev} online status changed to {online}")
        self.on_device_update(dev)

    def on_bay_registered(self, bay:BayBase) -> None:
        ''' called when a new bay was registered by mx_remote '''
        _LOGGER.debug(f"{bay} registered: {bay.features}")
        self.on_bay_update(bay)

    def on_device_temperature_changed(self, dev:DeviceBase) -> None:
        ''' called when the temperature values of 'dev' changed '''
        _LOGGER.debug(f"{dev} temperature: {dev.temperatures}")
        self.on_device_update(dev)

    def on_power_changed(self, bay:BayBase, power:PowerStatus) -> None:
        ''' called when the power status of 'bay' changed '''
        _LOGGER.debug(f"{bay} power status {power}")
        self.on_bay_update(bay)

    def on_name_changed(self, bay:BayBase, user_name:str) -> None:
        ''' called when the name that's set up by the user of 'bay' changed '''
        _LOGGER.debug(f"{bay} name changed: {user_name}")
        self.on_bay_update(bay)

    def on_status_signal_detected_changed(self, bay:BayBase, val:bool) -> None:
        ''' called when the signal detect status of 'bay' changed '''
        lval = "signal detected" if val else "no signal"
        _LOGGER.debug(f"{bay} {lval}")
        self.on_bay_update(bay)

    def on_status_faulty_changed(self, bay:BayBase, val:bool) -> None:
        ''' called when the fault status of 'bay' changed '''
        lval = "FAULT" if val else "healthy"
        _LOGGER.debug(f"{bay} {lval}")
        self.on_bay_update(bay)

    def on_status_hidden_changed(self, bay:BayBase, val:bool) -> None:
        ''' called when the hidden status of 'bay' changed '''
        lval = "hidden" if val else "visible"
        _LOGGER.debug(f"{bay} {lval}")
        self.on_bay_update(bay)

    def on_status_poe_powered_changed(self, bay:BayBase, val:bool) -> None:
        ''' called when the PoE power status of 'bay' changed '''
        lval = "on" if val else "off"
        _LOGGER.debug(f"{bay} PoE {lval}")
        self.on_bay_update(bay)

    def on_status_hdbt_connected_changed(self, bay:BayBase, val:bool) -> None:
        ''' called when the HDBaseT connection status of 'bay' changed '''
        lval = "up" if val else "down"
        _LOGGER.debug(f"{bay} HDBaseT link {lval}")
        self.on_bay_update(bay)

    def on_status_signal_type_changed(self, bay:BayBase, val:str) -> None:
        ''' called when the detected signal of 'bay' changed '''
        _LOGGER.debug(f"{bay} signal type: {val}")
        self.on_bay_update(bay)

    def on_status_hpd_detected_changed(self, bay:BayBase, val:bool) -> None:
        ''' called when the HPD value of 'bay' changed '''
        lval = "detected" if val else "lost"
        _LOGGER.debug(f"{bay} hotplug {lval}")
        self.on_bay_update(bay)

    def on_status_cec_detected_changed(self, bay:BayBase, val: bool) -> None:
        ''' called when a CEC device was detected on 'bay' '''
        lval = "detected" if val else "not found"
        _LOGGER.debug(f"{bay} HDMI-CEC device {lval}")
        self.on_bay_update(bay)

    def on_status_arc_changed(self, bay:BayBase, val:str) -> None:
        ''' called when the audio return channel status of 'bay' changed '''
        _LOGGER.info(f"{bay} ARC: {val}")
        self.on_bay_update(bay)

    def on_volume_changed(self, bay:BayBase, volume:VolumeMuteStatus|None) -> None:
        ''' called when the volume/mute status of 'bay' changed '''
        muted_str = ""
        volume_str = ""
        if (volume is not None) and (volume.muted is not None):
            muted_str = " not muted" if not volume.muted else " muted"
        if (volume is not None) and (volume.volume is not None):
            volume_str = " volume {}%".format(volume.volume)
        _LOGGER.debug(f"{bay}{volume_str}{muted_str}")
        self.on_bay_update(bay)

    def on_key_pressed(self, bay:BayBase, key:RCKey) -> None:
        ''' called when a key press was detected on 'bay' '''
        _LOGGER.debug(f"{bay} key pressed: {key}")

    def on_action_received(self, bay:BayBase, action:RCAction) -> None:
        ''' called when a remote control action was detected on 'bay' '''
        _LOGGER.debug(f"{bay} action: {action}")

    def on_video_source_changed(self, bay:BayBase, video_source:BayBase|None) -> None:
        ''' called when a video source changed was detected on 'bay' '''
        _LOGGER.debug(f"{bay} video routed to {video_source}")
        self.on_bay_update(bay)

    def on_audio_source_changed(self, bay:BayBase, audio_source:BayBase|None) -> None:
        ''' called when an audio source changed was detected on 'bay' '''
        _LOGGER.debug(f"{bay} audio routed to {audio_source}")
        self.on_bay_update(bay)

    def on_bay_linked(self, bay:BayBase, linked_serial:str, linked_bay:str, features:int) -> None:
        ''' called when a bay link was detected '''
        _LOGGER.debug(f"{bay} linked to {linked_serial}:{linked_bay}")
        self.on_device_update(bay.device)
        self.on_bay_update(bay)

    def on_bay_unlinked(self, bay:BayBase, linked_serial:str, linked_bay:str) -> None:
        ''' called when a bay link was removed '''
        _LOGGER.debug(f"{bay} unlinked from {linked_serial}:{linked_bay}")
        self.on_device_update(bay.device)
        self.on_bay_update(bay)

    def on_mirror_status_changed(self, bay:BayBase, mirror:BayMirrorStatus) -> None:
        ''' called when a bay mirroring setup change was detected '''
        _LOGGER.debug(f"{bay} mirror {mirror}")
        self.on_bay_update(bay)

    def on_filter_status_changed(self, bay:BayBase, filtered:list[MxrDeviceUid]) -> None:
        ''' called when a bay filtering setup change was detected '''
        _LOGGER.debug(f"{bay} filtered {filtered}")
        self.on_bay_update(bay)

    def on_edid_profile_changed(self, bay:BayBase, profile:EdidProfile|None) -> None:
        ''' called when a source EDID profile was changed '''
        _LOGGER.debug(f"{bay} edid profile changed to {profile}")
        self.on_bay_update(bay)

    def on_rc_type_changed(self, bay:BayBase, rc_type:RCType|None) -> None:
        ''' called when a source remote control type was changed '''
        _LOGGER.debug(f"{bay} rc type changed to {rc_type}")
        self.on_bay_update(bay)

    def on_amp_zone_settings_changed(self, bay:BayBase, settings:AmpZoneSettings) -> None:
        ''' called when amp zone settings were changed '''
        _LOGGER.debug(f"{bay} amp zone settings changed")
        self.on_bay_update(bay)

    def on_amp_dolby_settings_changed(self, device:DeviceBase, settings:AmpDolbySettings) -> None:
        ''' called when amp dolby settings were changed '''
        _LOGGER.debug(f"{device} dolby settings changed")
        self.on_device_update(device)
