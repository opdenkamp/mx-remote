##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from abc import ABC, abstractmethod
import ipaddress
import logging
import netifaces
from .proto import RCKey
from .proto.Constants import *
from .proto.Data import VolumeMuteStatus
from .proto.PDUState import PDUState
from .proto.V2IPStats import V2IPDeviceStats
import socket
import struct
from typing import Any
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

class AmpDolbySettings:
    """
    Dolby Digital settings for an amplifier
    """

    mode:int
    """ Dolby mode """

    pcm_upmix:bool
    """ PCM upmixing enabled """

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

class V2IPStreamSource:
    """
    V2IP multicast IP address and port number
    """
    def __init__(self, label:str, data:bytes) -> None:
        if len(data) < 6:
            raise Exception(f"invalid size: {len(data)}")
        self._label = label
        self._ip = int.from_bytes(data[0:4], "big")
        self._port = int(data[5]) << 8 | int(data[4])

    @property
    def label(self) -> str:
        """ user friendly description of this stream """
        return self._label

    @property
    def ip(self) -> str:
        """ multicast IP address """
        return socket.inet_ntoa(struct.pack('!L', self._ip))

    @property
    def port(self) -> int:
        """ UDP port number """
        return self._port

    def __eq__(self, value: object) -> bool:
        return (str(self) == str(value))

    def __str__(self) -> str:
        return f"{self.label}={self.ip}:{self.port}"

    def __repr__(self) -> str:
        return str(self)

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
    def arc(self) -> V2IPStreamSource:
        ''' audio return stream source '''

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
    def edid_profile(self) -> EdidProfile:
        ''' edid profile used by the source '''

    @property
    @abstractmethod
    def bay_label(self) -> str:
        '''user friendly label for this bay'''

    @property
    @abstractmethod
    def features_mask(self) -> BayStatusMask:
        ''' features/status '''

    @property
    @abstractmethod
    def is_v2ip_source(self) -> bool:
        '''V2IP source device'''

    @property
    @abstractmethod
    def is_v2ip_sink(self) -> bool:
        '''V2IP sink device'''

    @property
    @abstractmethod
    def is_v2ip_remote_sink(self) -> bool:
        '''V2IP remote sink bay'''

    @property
    @abstractmethod
    def is_v2ip_remote_source(self) -> bool:
        '''V2IP remote source bay'''

    @property
    @abstractmethod
    def is_v2ip_remote(self) -> bool:
        '''V2IP remote bay'''

    @property
    @abstractmethod
    def dolby_input(self) -> int:
        '''Dolby Digital input'''

    @property
    def dolby_input_bay(self) -> 'BayBase':
        '''Dolby Digital input bay used by this audio output bay'''

    @property
    @abstractmethod
    def features(self) -> list[str]:
        '''List of supported features as strings'''

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
    def other_mode(self) -> str:
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
    def video_source(self) -> 'BayBase':
        '''Current video source (output only)'''

    @property
    @abstractmethod
    def audio_source(self) -> 'BayBase':
        '''Current audio source (output only)'''

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
    def power_status(self) -> str:
        '''Power status as string'''

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
    def mirroring(self) -> str:
        '''The name of the bay if mirroring has been set up'''

    @property
    @abstractmethod
    def filtered(self) -> str:
        '''Filtered bays'''

    @property
    @abstractmethod
    def arc(self) -> str:
        '''Audio return channel status'''

    @property
    @abstractmethod
    def volume(self) -> int:
        '''Current volume level (percentage)'''

    @property
    @abstractmethod
    def muted(self) -> bool:
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
    def link(self) -> 'BayLink':
        '''mx-remote virtual link configuration (proamp<->matrix)'''

    @property
    @abstractmethod
    def linked_bay(self) -> 'BayBase':
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
    def volume_status(self) -> VolumeMuteStatus:
        '''volume and mute status'''

    @property
    @abstractmethod
    def amp_settings(self) -> AmpZoneSettings|None:
        '''proamp zone settings'''

    @property
    @abstractmethod
    def encoder_disabled(self) -> bool:
        ''' video/audio encoder disabled '''

    @property
    @abstractmethod
    def decoder_disabled(self) -> bool:
        ''' video/audio decoder disabled '''

    @abstractmethod
    async def set_name(self, name:str) -> bool:
        '''change the name of abay'''

    @abstractmethod
    async def select_video_source(self, port:int, opt:bool=True) -> bool:
        '''change the video source of an output bay'''

    @abstractmethod
    async def select_video_source_by_user_name(self, name:str, opt:bool=True) -> bool:
        '''change the video source of an output bay'''

    @abstractmethod
    async def select_audio_source(self, source:Any) -> bool:
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
    def volume_set(self, volume:int) -> bool:
        '''change the volume if supported'''

    @abstractmethod
    def mute_set(self, mute:bool) -> bool:
        '''change the mute status if supported'''

    @abstractmethod
    async def send_key(self, key:int) -> bool:
        '''send a remote control key press to the device'''

    @abstractmethod
    def on_mxr_bay_status(self, data:BayStatusMask) -> None:
        '''internal callback'''

    @abstractmethod
    def register_callback(self, callback:callable) -> None:
         '''register a callback, called when the bay state changed'''

    @abstractmethod
    def unregister_callback(self, callback:callable) -> None:
         '''unregister a callback'''

    @abstractmethod
    def call_callbacks(self) -> None:
        '''notify callbacks that this bay has changed'''

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
    def boot_bit(self) -> bool:
        """ bit that is flipped every time the device reboots """
        return ((self._features & MXR_DEVICE_FEATURE_BOOT_BIT) != 0)

    def __eq__(self, value: object) -> bool:
        if (not isinstance(value, DeviceFeatures)):
            return False
        return self._features == value._features

    @property
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

class DeviceV2IPDetailsBase(ABC):
    """ V2IP stream source details for a device """

    @property
    @abstractmethod
    def has_config(self) -> bool:
        """ configuation known """

    @property
    @abstractmethod
    def video(self) -> V2IPStreamSource|None:
        """ video stream source """

    @property
    @abstractmethod
    def audio(self) -> V2IPStreamSource:
        """ audio stream source """

    @property
    @abstractmethod
    def anc(self) -> V2IPStreamSource:
        """ ancillary stream source """

    @property
    @abstractmethod
    def arc(self) -> V2IPStreamSource:
        """ audio return channel stream source """

    @property
    @abstractmethod
    def tx_rate(self) -> int:
        """ transmit rate in Mbit/s """

    def __eq__(self, value: object) -> bool:
        if isinstance(value, DeviceV2IPDetailsBase):
            return (self.video == value.video) \
                and (self.audio == value.audio) \
                and (self.anc == value.anc) \
                and (self.arc == value.arc) \
                and (self.tx_rate == value.tx_rate)
        return False

class UtpLinkSpeed(Enum):
    ''' UTP link speed '''

    UNKNOWN = 0
    ''' unknown speed '''

    L_10M = 1
    ''' 10Mbit/s '''

    L_100M = 2
    ''' 100Mbit/s '''

    L_200M = 3
    ''' 200Mbit/s '''

    L_1G = 4
    ''' 1Gbit/s '''

    def __str__(self) -> str:
        if self.value == 1:
            return '10Mbit/s'
        if self.value == 2:
            return '100Mbit/s'
        if self.value == 3:
            return '200Mbit/s'
        if self.value == 4:
            return '1Gbit/s'
        return 'Unknown'

    def __repr__(self) -> str:
        return str(self)

class UtpLinkErrorStatus(ABC):
    ''' UTP link error status bits '''

    @property
    @abstractmethod
    def in_error(self):
        ''' rx errors detected '''

    @property
    @abstractmethod
    def in_fcs_error(self):
        ''' rx FCS errors detected '''

    @property
    @abstractmethod
    def in_collision(self):
        ''' rx collisions detected '''

    @property
    @abstractmethod
    def out_deferred(self):
        ''' tx deferred detected '''

    @property
    @abstractmethod
    def out_excessive(self):
        ''' tx excessive detected '''

    @property
    @abstractmethod
    def polarity_error(self):
        ''' polarity differences between pairs detected '''

    @property
    @abstractmethod
    def skew_warning(self):
        ''' clock skew > 8 detected '''

    @property
    @abstractmethod
    def length_warning(self):
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
    
    @property
    @abstractmethod
    def port(self) -> int:
        '''port number'''

    @property
    @abstractmethod
    def errors(self) -> UtpLinkErrorStatus:
        ''' link error status '''

    @property
    @abstractmethod
    def vct_status(self) -> list[str]:
        ''' virtual cable test results '''

    @property
    @abstractmethod
    def link_speed(self) -> UtpLinkSpeed:
        ''' link speed '''

    @property
    @abstractmethod
    def link_full_duplex(self) -> bool:
        ''' full duplex or half duplex '''

    @property
    @abstractmethod
    def name(self) -> str:
        ''' description of the port '''

    @property
    @abstractmethod
    def ip(self) -> str:
        ''' IP address '''

    @property
    @abstractmethod
    def querier(self) -> str:
        ''' detected IGMP querier or 0.0.0.0 if not detected'''

    @property
    @abstractmethod
    def cable_status(self) -> UtpCableStatus:
        ''' utp cable pair status '''

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
    def features(self) -> DeviceFeatures:
        '''supported features'''

    @property
    @abstractmethod
    def serial(self) -> str:
        '''serial number'''

    @property
    @abstractmethod
    def bays(self) -> dict[str, BayBase]:
        '''device inputs and outputs'''

    @property
    @abstractmethod
    def inputs(self) -> dict[str, BayBase]:
        '''device inputs'''

    @abstractmethod
    def nb_inputs(self) -> int:
        '''number of inputs'''

    @property
    @abstractmethod
    def first_input(self) -> BayBase:
        '''the first local input'''

    @property
    @abstractmethod
    def outputs(self) -> dict[str, BayBase]:
        '''device outputs'''

    @abstractmethod
    def nb_outputs(self) -> int:
        '''number of outputs'''

    @property
    @abstractmethod
    def first_output(self) -> BayBase:
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
    def registry(self) -> 'DeviceRegistry':
        '''local device registry'''

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
    def v2ip_sources(self) -> list[V2IPStreamSources]:
        '''V2IP stream source addresses'''

    @property
    @abstractmethod
    def v2ip_stats(self) -> V2IPDeviceStats:
         '''V2IP encoder/decoder statistics'''

    @property
    @abstractmethod
    def v2ip_details(self) -> DeviceV2IPDetailsBase:
        '''V2IP encoder/decoder configuration'''

    @property
    @abstractmethod
    def v2ip_source_local(self) -> V2IPStreamSources|None:
         ''' local v2ip source addresses '''

    @property
    @abstractmethod
    def mesh_master(self) -> 'DeviceBase':
        '''The device that is the master device in the V2IP mesh to which this device belongs'''

    @mesh_master.setter
    @abstractmethod
    def mesh_master(self, master:MxrDeviceUid) -> None:
        '''Change the master device of this device'''

    @property
    @abstractmethod
    def is_mesh_master(self) -> bool:
        '''True if this device is the master device of a V2IP mesh'''

    @property
    @abstractmethod
    def dolby_settings(self) -> AmpDolbySettings|None:
        '''Dolby Digital settings (proamp)'''

    @abstractmethod
    def v2ip_source(self, bay:BayBase) -> V2IPStreamSources|None:
        '''Get the V2IP source addresses for the given bay'''

    @abstractmethod
    def get_by_portnum(self, portnum: int) -> BayBase:
        '''Get the bay with the given number on this device'''

    @abstractmethod
    def get_by_portname(self, portname: str) -> BayBase:
        '''Get the bay with the given port name (not user set name) on this device'''

    @property
    @abstractmethod
    def network_status(self) -> dict[int, NetworkPortStatus]:
        '''network status for all ports'''

    @abstractmethod
    def update_network_status(self, status:NetworkPortStatus):
        '''internal callback'''

    @abstractmethod
    def on_link_config_received(self) -> None:
        '''internal callback'''

    @abstractmethod
    async def get_api(self, uri:str) -> Any:
        '''call an HTTP API method and return the result'''

    @abstractmethod
    def register_callback(self, callback:callable) -> None:
         '''register a callback, called when the device state changed'''

    @abstractmethod
    def unregister_callback(self, callback:callable) -> None:
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
        if self.connected:
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
        left = self.bay.features_mask
        right = self.linked_bay.features_mask
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
            self.callbacks.on_bay_linked(bay, new_link.serial, new_link.bay, new_link.features),
            other_bay = new_link.linked_bay
            if other_bay is not None:
                self.callbacks.on_bay_linked(other_bay, bay.device.serial, bay.bay_name, new_link.features)

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
                    self.callbacks.on_bay_unlinked(bay, old.serial, old.bay)
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
    def local_ip(self) -> str:
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
    def uid_raw(self) -> bytes:
        ''' uid of this device as bytes '''

    @property
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
    def get_by_uid(self, remote_id:str|MxrDeviceUid) -> DeviceBase|None:
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

class ConnectionCallbacks(ABC):
    @property
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

    def on_power_changed(self, bay:BayBase, power:str) -> None:
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

    def on_volume_changed(self, bay:BayBase, volume:VolumeMuteStatus) -> None:
        ''' called when the volume/mute status of 'bay' changed '''
        muted_str = ""
        volume_str = ""
        if volume.muted is not None:
            muted_str = " not muted" if not volume.muted else " muted"
        if volume.volume is not None:
            volume_str = " volume {}%".format(volume.volume)
        _LOGGER.debug(f"{bay}{volume_str}{muted_str}")
        self.on_bay_update(bay)

    def on_key_pressed(self, bay:BayBase, key:RCKey) -> None:
        ''' called when a key press was detected on 'bay' '''
        _LOGGER.debug(f"{bay} key pressed: {key}")

    def on_action_received(self, bay:BayBase, action:RCAction) -> None:
        ''' called when a remote control action was detected on 'bay' '''
        _LOGGER.debug(f"{bay} action: {action}")

    def on_video_source_changed(self, bay:BayBase, video_source:BayBase) -> None:
        ''' called when a video source changed was detected on 'bay' '''
        _LOGGER.debug(f"{bay} video routed to {video_source}")
        self.on_bay_update(bay)

    def on_audio_source_changed(self, bay:BayBase, audio_source:BayBase) -> None:
        ''' called when an audio source changed was detected on 'bay' '''
        _LOGGER.debug(f"{bay} audio routed to {audio_source}")
        self.on_bay_update(bay)

    def on_pdu_registered(self, pdu:PDUState) -> None:
        ''' called when a Pulse-Eight PDU was detected that's connected to an mx_remote device '''
        _LOGGER.debug(f"{pdu.dev} pdu registered: {pdu}")

    def on_pdu_changed(self, pdu:PDUState) -> None:
        ''' called when a state of 'pdu' changed '''
        _LOGGER.debug(f"{pdu.dev} pdu: {pdu}")

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

    def on_mirror_status_changed(self, bay:BayBase, mirror:MxrDeviceUid|None) -> None:
        ''' called when a bay mirroring setup change was detected '''
        _LOGGER.debug(f"{bay} mirror {mirror}")
        self.on_bay_update(bay)

    def on_filter_status_changed(self, bay:BayBase, filtered:list[MxrDeviceUid]) -> None:
        ''' called when a bay filtering setup change was detected '''
        _LOGGER.debug(f"{bay} filtered {filtered}")
        self.on_bay_update(bay)

    def on_edid_profile_changed(self, bay:BayBase, profile:EdidProfile) -> None:
        ''' called when a source EDID profile was changed '''
        _LOGGER.debug(f"{bay} edid profile changed to {profile}")
        self.on_bay_update(bay)

    def on_rc_type_changed(self, bay:BayBase, rc_type:RCType) -> None:
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
