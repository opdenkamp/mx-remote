######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum
import time
import warnings
from functools import cached_property
import aiohttp
import ipaddress
import logging
import netifaces
from .proto import RCKey
from .proto.Constants import *
from .proto.Data import VolumeMuteStatus
from .proto.V2IPStats import OneIPDeviceStats
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
from .proto.Svd import SvdMap, lookup_svd
from typing import Any, Callable
from .Uid import MxrDeviceUid, MxrBayUid

_LOGGER = logging.getLogger(__name__)

def mxr_valid_addresses() -> list[str]:
    """
    Get the list of valid local_ip addresses that can be used

    Returns:
        list[str]: the IP addresses that can be used for the local_ip parameter
    """
    addresses:list[str] = []
    for iface in netifaces.interfaces():
        if netifaces.AF_INET in netifaces.ifaddresses(iface):
            addr = netifaces.ifaddresses(iface)[netifaces.AF_INET][0]['addr']
            if not ipaddress.IPv4Address(addr).is_loopback:
                addresses.append(addr)
    return addresses

def mxr_broadcast_address(local_ip:str|None=None) -> str|None:
    '''Get the broadcast address for the interface matching local_ip, or the first non-loopback interface.'''
    for iface in netifaces.interfaces():
        addrs = netifaces.ifaddresses(iface)
        if netifaces.AF_INET not in addrs:
            continue
        info = addrs[netifaces.AF_INET][0]
        addr = info.get('addr', '')
        if ipaddress.IPv4Address(addr).is_loopback:
            continue
        if (local_ip is not None) and (addr != local_ip):
            continue
        bcast = info.get('broadcast')
        if bcast is not None:
            return bcast
    return None

class DeviceStatus(IntEnum):
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
    """ bay is inactive (OneIP encoder/decoder idle) """

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

class PowerStatus(IntEnum):
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

class HiddenStatus(IntEnum):
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
    '''One firmware component's version. timestamp is when the image was built
    or installed, in seconds since 1970, or 0 when it carries none, and hash the
    image's checksum.'''
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

class ConnectStatus(IntEnum):
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

class VideoColourSpace(IntEnum):
    '''Video colour space encoding format.'''
    RGB = 0
    YUV444 = 1
    YUV422 = 2
    YUV420 = 3

    def __str__(self) -> str:
        if self.value == 0:
            return 'RGB'
        if self.value == 1:
            return '4:4:4'
        if self.value == 2:
            return '4:2:2'
        if self.value == 3:
            return '4:2:0'
        return 'unknown'

class VideoSignalDetails:
    """
    Video format of a bay: CTA-861 svd, colour space, bit depth, frame rate kind.

    ``from_report`` says where it came from, because the two sources do not carry
    the same currency. A signal status report is the live format and arrives on a
    signal change. The bay config snapshot is a fallback for a bay no report has
    been seen for: it refreshes on the bay config broadcast cycle, so it can lag a
    change by a broadcast interval.

    ``bpp`` is a bit depth in both cases, not a wire index. None means no format
    is set; 0 means one is set whose depth is not known, and those are different
    answers.
    """
    def __init__(self, svd:int|None, colour:VideoColourSpace|None, bpp:int|None,
                 non_int:bool|None, from_report:bool) -> None:
        self._svd = svd
        self._colour = colour
        self._bpp = bpp
        self._non_int = non_int
        self._from_report = from_report

    @property
    def svd(self) -> int|None:
        '''CTA-861 short video descriptor, or None when no format is set.'''
        return self._svd

    @property
    def colour(self) -> VideoColourSpace|None:
        '''Colour space, or None when no format is set or the value is unknown to this build.'''
        return self._colour

    @property
    def bpp(self) -> int|None:
        '''Bit depth, 0 when a format is set whose depth is not known.'''
        return self._bpp

    @property
    def non_int(self) -> bool|None:
        '''True for a non-integer (1000/1001) frame rate.'''
        return self._non_int

    @property
    def from_report(self) -> bool:
        '''True when this came from a signal status report rather than the bay config snapshot.'''
        return self._from_report

    def __eq__(self, other:Any) -> bool:
        if not isinstance(other, VideoSignalDetails):
            return NotImplemented
        return (self._svd == other._svd) and (self._colour == other._colour) \
            and (self._bpp == other._bpp) and (self._non_int == other._non_int)

    def __hash__(self) -> int:
        return hash((self._svd, self._colour, self._bpp, self._non_int))

    def __str__(self) -> str:
        if self._svd is None:
            return 'no format'
        src = 'report' if self._from_report else 'bay config'
        bpp = f', {self._bpp}bpp' if self._bpp else ''
        return f'svd {self._svd}, {self._colour}{bpp} ({src})'

    def __repr__(self) -> str:
        return str(self)

class SignalStatus:
    def __init__(self, detected:bool, description:str|None=None,
                 details:VideoSignalDetails|None=None) -> None:
        self._detected = detected
        self._description = description
        self._details = details

    @property
    def detected(self) -> bool:
        return self._detected

    @property
    def description(self) -> str|None:
        return self._description

    @property
    def details(self) -> VideoSignalDetails|None:
        '''Structured video format, or None when the report carried no valid stream.'''
        return self._details

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

    def __eq__(self, other:Any) -> bool:
        """Compare by value.

        Without this the on-change guards that hold one of these compare by
        identity, so a device re-broadcasting settings it already sent looks
        like a change and fires a callback every time. Driven off the
        annotations rather than a written-out field list, so a field added
        later cannot be left out of the comparison and quietly restore that.
        """
        if not isinstance(other, AmpDolbySettings):
            return NotImplemented
        return all(getattr(self, n, None) == getattr(other, n, None)
                   for n in type(self).__annotations__)

    def __ne__(self, other:Any) -> bool:
        result = self.__eq__(other)
        return result if (result is NotImplemented) else (not result)

    def __str__(self) -> str:
        """Render the values, not the identity.

        These are re-created from every frame that carries them, so the default
        object repr changes on each one and makes an unchanged setting look like
        a new value in a log or a diff.
        """
        fields = ', '.join(f'{n}={getattr(self, n, None)!r}'
                           for n in type(self).__annotations__)
        return f'AmpDolbySettings({fields})'

    def __repr__(self) -> str:
        return str(self)

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
        return f"gain:{self.gain_left}/{self.gain_right} volume:{self.volume_min}/{self.volume_max} delay:{self.delay_left}/{self.delay_right} bass:{self.bass} treble:{self.treble} bridged:{self.bridged} eqleft:{self.eq_left} eqright:{self.eq_right} power:{self.power_mode} pwrlevel:{self.power_level} pwrtimeout:{self.power_timeout}"

    def __repr__(self) -> str:
        return str(self)

    def __eq__(self, other:Any) -> bool:
        """Compare by value.

        Without this the on-change guards that hold one of these compare by
        identity, so a device re-broadcasting settings it already sent looks
        like a change and fires a callback every time. Driven off the
        annotations rather than a written-out field list, so a field added
        later cannot be left out of the comparison and quietly restore that.
        """
        if not isinstance(other, AmpZoneSettings):
            return NotImplemented
        return all(getattr(self, n, None) == getattr(other, n, None)
                   for n in type(self).__annotations__)

    def __ne__(self, other:Any) -> bool:
        result = self.__eq__(other)
        return result if (result is NotImplemented) else (not result)

    def __str__(self) -> str:
        """Render the values, not the identity.

        These are re-created from every frame that carries them, so the default
        object repr changes on each one and makes an unchanged setting look like
        a new value in a log or a diff.
        """
        fields = ', '.join(f'{n}={getattr(self, n, None)!r}'
                           for n in type(self).__annotations__)
        return f'AmpZoneSettings({fields})'

    def __repr__(self) -> str:
        return str(self)

class OneIPAudioFormat:
    '''OneIP audio format (sample rate + channels). Zero values mean "use firmware defaults".'''
    _WIRE_SIZE = 8

    def __init__(self, sample_rate:int=0, channels:int=0) -> None:
        self._sample_rate = sample_rate
        self._channels = channels

    @classmethod
    def from_bytes(cls, data:bytes) -> 'OneIPAudioFormat':
        if len(data) < cls._WIRE_SIZE:
            raise ValueError(f"invalid OneIPAudioFormat size: {len(data)}")
        return cls(
            sample_rate=int.from_bytes(data[0:4], "little"),
            channels=int(data[4]),
        )

    @property
    def sample_rate(self) -> int:
        '''Sample rate in Hz, or 0 to fall back to the firmware default (48000).'''
        return self._sample_rate

    @property
    def channels(self) -> int:
        '''Channel count 1..8, or 0 to fall back to the firmware default (2).'''
        return self._channels

    @property
    def value(self) -> bytes:
        return bytes([
            (self._sample_rate >> 0)  & 0xFF,
            (self._sample_rate >> 8)  & 0xFF,
            (self._sample_rate >> 16) & 0xFF,
            (self._sample_rate >> 24) & 0xFF,
            self._channels & 0xFF,
            0, 0, 0,
        ])

    def __eq__(self, other:Any) -> bool:
        if not isinstance(other, OneIPAudioFormat):
            return False
        return (self._sample_rate == other._sample_rate) and (self._channels == other._channels)

    def __hash__(self) -> int:
        return hash((self._sample_rate, self._channels))

    def __str__(self) -> str:
        return f"{self.sample_rate}Hz/{self.channels}ch"

    def __repr__(self) -> str:
        return str(self)

class OneIPStreamSource(ABC):
    """
    OneIP multicast IP address and port number
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

class OneIPStreamSources:
    """
    All OneIP multicast IP addresses and port numbers used by a device
    """

    @property
    @abstractmethod
    def uid(self) -> MxrDeviceUid|None:
        ''' uid of the originating source device, when known '''

    @property
    @abstractmethod
    def video(self) -> OneIPStreamSource:
        ''' video stream source '''

    @property
    @abstractmethod
    def audio(self) -> OneIPStreamSource:
        ''' audio stream source '''

    @property
    @abstractmethod
    def anc(self) -> OneIPStreamSource:
        ''' ancillary stream source '''

    @property
    @abstractmethod
    def arc(self) -> OneIPStreamSource|None:
        ''' audio return stream source '''

    @property
    def valid(self) -> bool:
        """
        True when this entry carries a usable address.

        Video and anc must both be multicast with a non-zero port; audio is
        optional and rides along. A sender without MXR_FEATURE_CONFIG_INITIALISED
        can put stack contents in bay 0's addresses under its own uid, which
        rarely satisfy both halves of this test.
        """
        return oneip_av_source_valid(self.video, self.anc)

    @property
    def cleared(self) -> bool:
        """
        True when every stream is zeroed, which reports that the source is gone.

        Distinct from an entry that is neither valid nor cleared, which is
        malformed. Treating a cleared entry as unusable discards the only signal
        that a source went away.
        """
        return (oneip_stream_cleared(self.video)
                and oneip_stream_cleared(self.audio)
                and oneip_stream_cleared(self.anc))

class OneIPStreamSourcesList(list[OneIPStreamSources]):
    ''' list of OneIP sources '''

class AudioFeatures:
    FEATURE_INPUT = (1 << 0)
    FEATURE_OUTPUT = (1 << 1)
    FEATURE_ONEIP_TX = (1 << 2)
    FEATURE_ONEIP_RX = (1 << 3)
    FEATURE_V2IP_TX = FEATURE_ONEIP_TX
    '''Deprecated: use FEATURE_ONEIP_TX.'''
    FEATURE_V2IP_RX = FEATURE_ONEIP_RX
    '''Deprecated: use FEATURE_ONEIP_RX.'''
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
    FEATURE_AUDIO_LOCK = (1 << 15)
    '''Keeps its audio source when the video route changes, while locked.'''

    def __init__(self, value:int) -> None:
        self._value = value

    @property
    def value(self) -> int:
        return self._value

    def __eq__(self, other:object) -> bool:
        if not isinstance(other, AudioFeatures):
            return NotImplemented
        return (self._value == other._value)

    def __hash__(self) -> int:
        return hash(self._value)

    @property
    def is_input(self) -> bool:
        return ((self._value & self.FEATURE_INPUT) != 0)

    @property
    def is_output(self) -> bool:
        return ((self._value & self.FEATURE_OUTPUT) != 0)

    @property
    def is_oneip_tx(self) -> bool:
        return ((self._value & self.FEATURE_ONEIP_TX) != 0)

    @property
    def is_oneip_rx(self) -> bool:
        return ((self._value & self.FEATURE_ONEIP_RX) != 0)

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
    def support_audio_lock(self) -> bool:
        return ((self._value & self.FEATURE_AUDIO_LOCK) != 0)

    @property
    def features(self) -> list[str]:
        rv:list[str] = []
        if self.is_input:
            rv.append('input')
        if self.is_output:
            rv.append('output')
        if self.is_oneip_tx:
            rv.append('v2ip tx')
        if self.is_oneip_rx:
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
        if self.support_audio_lock:
            rv.append('audio lock')
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
        self._status:AudioFeatures|None = None

    @property
    def status(self) -> AudioFeatures|None:
        '''The state this endpoint reports, on the bits of its features:
        FEATURE_MUTE while it is muted, FEATURE_TRIGGER while its trigger is
        active, and FEATURE_AUDIO_LOCK while its audio source is locked. None
        when the device did not report one.'''
        return self._status

    @status.setter
    def status(self, status:AudioFeatures) -> None:
        self._status = status

    @property
    def audio_locked(self) -> bool|None:
        '''Whether this endpoint keeps its audio source when the video route
        changes, None when it has reported no status.'''
        return self._status.support_audio_lock if (self._status is not None) else None

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
    def is_oneip(self) -> bool:
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
    def address(self) -> OneIPStreamSource|None:
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
    def __init__(self, legacy_layout:bool|None=None) -> None:
        self.endpoints:dict[int,AudioEndpoint] = {}
        self.legacy_layout = legacy_layout
        '''Whether the report used the audio module layout of released firmware
        up to 4.4.2, None when it described no endpoint and so did not say.'''

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

    def same_status(self, other:'AudioEndpoints') -> bool:
        '''Whether every endpoint reports the same status in both.'''
        if (self.endpoints.keys() != other.endpoints.keys()):
            return False
        return all((ep.status == other.endpoints[k].status) for k, ep in self.endpoints.items())

    def __str__(self) -> str:
        return str(self.as_list)

    def __repr__(self) -> str:
        return str(self)

class DeviceList(list[MxrDeviceUid]):
    def __init__(self, data:bytes|None=None):
        super().__init__()
        if (data is None):
            return
        while len(data) >= 16:
            self.append(MxrDeviceUid(data[0:16]))
            data = data[16:]

    def append(self, item: MxrDeviceUid) -> None:
        super().append(item)

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
    def is_oneip_remote(self) -> bool:
        '''OneIP remote bay'''

    @property
    @abstractmethod
    def is_oneip_source(self) -> bool:
        pass

    @property
    @abstractmethod
    def is_oneip_sink(self) -> bool:
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
    def video_source(self) -> 'BayBase|None':
        '''Current video source (output only)'''

    @property
    @abstractmethod
    def video_route_endpoint(self) -> 'str|None':
        '''Current video route as 'ip:port' literal when the sink is subscribed to a
        multicast that does not map to any registered input bay; else None.'''

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
    def audio_route_endpoint(self) -> 'str|None':
        '''Current audio route as 'ip:port' literal when the sink is subscribed to a
        multicast that does not map to any registered input bay; else None.'''

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
    def zone_powered(self) -> bool:
        '''True if the amplifier zone the bay drives is powered on. Only a
        ProAmp8v2 reports it.'''

    @property
    def poe_powered(self) -> bool:
        '''Deprecated: use zone_powered. Bay status bit 2 says an amplifier
        zone is powered on, not that PoE is.'''
        warnings.warn("BayBase.poe_powered is deprecated, use zone_powered", DeprecationWarning, stacklevel=2)
        return self.zone_powered

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
    def video_details(self) -> VideoSignalDetails|None:
        '''Current video format, or None if neither source has carried one.

        Prefers the signal status report, which arrives on a signal change, and
        falls back to the bay config snapshot for a bay no report has been seen
        for. Read from_report to tell which one this is.'''

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
        '''True if audio has been muted, None if not available'''

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
    def oneip_source(self) -> OneIPStreamSources|None:
        '''OneIP source address information'''

    @property
    @abstractmethod
    def oneip_uid(self) -> MxrDeviceUid|None:
        '''Remote OneIP device uid'''

    @property
    @abstractmethod
    def oneip_device(self) -> 'DeviceBase|None':
        '''Remote OneIP device'''

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
    async def select_audio_source(self, source:'int|BayBase|str|None', endpoint:str|None=None, audio_fmt:'OneIPAudioFormat|None'=None) -> bool:
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
    def on_mxr_update(self, data:object) -> None:
        pass

class SelectedBays:
    '''A route a frame reports for an output. video and audio are None where the
    frame names no bay, and the port of a OneIP unit's input its mappings have
    yet to create; clear_video says the output shows nothing, and audio_follows
    that its audio follows its video again.'''
    def __init__(self, video:BayBase|int|None, audio:BayBase|int|None, clear_video:bool=False,
                 audio_follows:bool=False) -> None:
        self._video = video
        self._audio = audio
        self.clear_video = clear_video
        self.audio_follows = audio_follows

    @property
    def video(self) -> BayBase|int|None:
        return self._video

    @property
    def audio(self) -> BayBase|int|None:
        return self._audio


class DeviceOneIPScalingSettings(ABC):
    @property
    @abstractmethod
    def mode(self) -> int:
        '''Scaling mode, carried only when flags has MXR_SCALING_FLAG_MODE_VALID'''

    @property
    @abstractmethod
    def refresh(self) -> int:
        '''Refresh rate paired with mode, under the same MXR_SCALING_FLAG_MODE_VALID marker'''

    @property
    @abstractmethod
    def flags(self) -> int:
        '''mxr_scaling_config.flags.

        MXR_SCALING_FLAG_MODE_VALID, MXR_SCALING_FLAG_OPTIONS_VALID and
        MXR_SCALING_FLAG_OPTIONS2_VALID mark which part a sender meant to send,
        and are separately valid; a sender setting none of them is offering no
        scaling at all. MXR_SCALING_FLAG_AUTO_SCALING sits behind the first
        marker, MXR_SCALING_FLAG_MATCH_SOURCE and MXR_SCALING_FLAG_SKIP_420
        behind the second.
        '''

    @property
    def configured_mode(self) -> 'tuple[MxrSignalType, int]|None':
        '''The mode and refresh rate this sink scales to, None when it has none.

        The two are distinct on the wire: a sink with no mode configured leaves
        MXR_SCALING_FLAG_MODE_VALID clear, and never sets it over a zero mode.

        Trust it only from a peer whose hello carries CONFIG_INITIALISED
        (DeviceBase.config_initialised). Firmware without that builds this block
        over uninitialised stack, where the valid bit itself is noise.
        '''
        if ((self.flags & MXR_SCALING_FLAG_MODE_VALID) == 0):
            return None
        return (MxrSignalType(self.mode.to_bytes(2, 'little')), self.refresh)

    @property
    def auto_scaling(self) -> bool|None:
        '''Whether the output scales automatically, None when the sender did not say.'''
        if ((self.flags & MXR_SCALING_FLAG_OPTIONS_VALID) == 0):
            return None
        return ((self.flags & MXR_SCALING_FLAG_AUTO_SCALING) != 0)

    @property
    def match_source(self) -> bool|None:
        '''Whether the output follows its source's format, None when the device
        has never said.

        Firmware with this option announces it on every configuration it sends
        about itself, so a device that has reported it once is known to have it.
        The cached block accumulates its validity bit, so a later write carrying
        only the first options group does not take that back.

        Reported only from a sender announcing DeviceBase.config_initialised,
        which is why this needs no caveat of its own: no firmware has these
        options without that announcement, and one that lacks it would be
        reporting uninitialised stack. That is the difference from
        configured_mode, which is reported from any sender because a mode can be
        genuine on one of those.
        '''
        if ((self.flags & MXR_SCALING_FLAG_OPTIONS2_VALID) == 0):
            return None
        return ((self.flags & MXR_SCALING_FLAG_MATCH_SOURCE) != 0)

    @property
    def skip_420(self) -> bool|None:
        '''Whether the output declines 4:2:0 rather than scaling it, None when
        the device has never said. Reported on the same terms as match_source,
        which shares its validity bit.
        '''
        if ((self.flags & MXR_SCALING_FLAG_OPTIONS2_VALID) == 0):
            return None
        return ((self.flags & MXR_SCALING_FLAG_SKIP_420) != 0)

def oneip_stream_valid(stream:'OneIPStreamSource|None') -> bool:
    """
    True when a stream source carries an address a frame actually meant to send.

    Mirrors the firmware's own test: a multicast ip and a non-zero port. A
    controller write that offers no addresses leaves the block zeroed, which
    fails both tests.
    """
    if (stream is None):
        return False
    try:
        return ipaddress.IPv4Address(stream.ip).is_multicast and (stream.port != 0)
    except ValueError:
        return False

def oneip_av_source_valid(video:'OneIPStreamSource|None', anc:'OneIPStreamSource|None') -> bool:
    """
    True when an av source block carries addresses a frame meant to send.

    Mirrors the firmware's own test: video and anc must both be valid, audio
    is optional and is carried along with them.
    """
    return oneip_stream_valid(video) and oneip_stream_valid(anc)

def oneip_stream_cleared(stream:'OneIPStreamSource|None') -> bool:
    """True when a stream source is zeroed, which is how "no source" is spelled."""
    return (stream is not None) and (stream.ip == '0.0.0.0') and (stream.port == 0)

class OneIPOutputMode:
    """
    The output format to scale a OneIP sink to.

    Built from a depth and a colour space rather than from a packed
    mxr_signal_type word, so the word a caller sends cannot carry the unset bpp
    index a sink reports while it has no mode configured.
    """
    def __init__(self, svd:int, depth:int, colour:VideoColourSpace, refresh:int) -> None:
        self.svd = svd
        """CTA-861 short video descriptor to output."""
        self.depth = depth
        """Bit depth: 8, 10 or 12."""
        self.colour = colour
        """Colour space to output."""
        self.refresh = refresh
        """Refresh rate in Hz, ONEIP_SCALING_REFRESH_MIN to ONEIP_SCALING_REFRESH_MAX."""

    def validate(self) -> str|None:
        """
        Why a sink will refuse this mode, or None when it will take it.

        Checked here because a sink checks it and then says nothing: every value
        this rejects is one the receiver decodes cleanly and drops, leaving a
        caller with a send that succeeded and a setting that did not move.

        Passing is not a guarantee. A sink also weighs the format against the
        EDID of the display attached to it and against what its own clock and
        output stage can produce, and none of that is knowable from here.
        """
        if (self.svd == 0):
            return "svd 0 is how a mode is cleared, not a mode to set"
        if (lookup_svd(self.svd) is None):
            return "the svd names no known video descriptor"
        if (mxr_sig_bpp_index(self.depth) is None):
            return "a OneIP output stage takes 8, 10 or 12 bits per pixel"
        if (self.colour not in (VideoColourSpace.RGB, VideoColourSpace.YUV444,
                                VideoColourSpace.YUV422, VideoColourSpace.YUV420)):
            return "the colour space names none of RGB, 4:4:4, 4:2:2 or 4:2:0"
        if not (ONEIP_SCALING_REFRESH_MIN <= self.refresh <= ONEIP_SCALING_REFRESH_MAX):
            return f"the refresh rate is outside {ONEIP_SCALING_REFRESH_MIN}..{ONEIP_SCALING_REFRESH_MAX}Hz"
        return None

    @property
    def signal_type(self) -> MxrSignalType:
        """
        The packed signal type a scaling write carries for this mode.

        Call validate() first: an unvalidated depth packs as the index for
        "no depth", which a receiver drops.
        """
        return MxrSignalType.from_parts(svd=self.svd, colour=int(self.colour),
                                        bpp_index=(mxr_sig_bpp_index(self.depth) or 0))

    def __eq__(self, other:Any) -> bool:
        if not isinstance(other, OneIPOutputMode):
            return NotImplemented
        return (self.svd == other.svd) and (self.depth == other.depth) \
            and (self.colour == other.colour) and (self.refresh == other.refresh)

    def __str__(self) -> str:
        return f"svd {self.svd}, colour {self.colour}, {self.depth}bpp, {self.refresh}Hz"

    def __repr__(self) -> str:
        return str(self)

class OneIPScalingSettings(DeviceOneIPScalingSettings):
    """Plain holder for a merged mxr_scaling_config."""
    def __init__(self, mode:int, refresh:int, flags:int) -> None:
        self._mode = mode
        self._refresh = refresh
        self._flags = flags

    @property
    def mode(self) -> int:
        return self._mode

    @property
    def refresh(self) -> int:
        return self._refresh

    @property
    def flags(self) -> int:
        return self._flags

    def __str__(self) -> str:
        return f"mode:{self._mode} refresh:{self._refresh} flags:{self._flags:02X}"

    def __repr__(self) -> str:
        return str(self)

class OneIPDscpConfig:
    """
    Per-stream DSCP marking carried in a OneIP device configuration.

    DSCP 0 (CS0) is a legal marking, so each wire byte carries a set bit
    alongside its value and a stream whose byte is unset reads back as None
    here. A unit treats the marking as all-or-nothing: it keeps a frame's
    markings only when all three streams carry a value, and otherwise keeps
    the ones it had - ``complete`` reports which case a frame is in.
    """
    def __init__(self, video:int|None, audio:int|None, anc:int|None) -> None:
        self._video = video
        self._audio = audio
        self._anc = anc

    @property
    def video(self) -> int|None:
        return self._video

    @property
    def audio(self) -> int|None:
        return self._audio

    @property
    def anc(self) -> int|None:
        return self._anc

    @property
    def carried(self) -> bool:
        """
        True when this frame carried a marking for the video stream. A unit
        takes the markings only when they are ``complete``.
        """
        return (self._video is not None)

    @property
    def complete(self) -> bool:
        """
        True when all three streams carry a marking, the only case a unit
        takes the frame's markings in.
        """
        return (self._video is not None) and (self._audio is not None) and (self._anc is not None)

    def __eq__(self, other:Any) -> bool:
        if not isinstance(other, OneIPDscpConfig):
            return False
        return (self._video == other._video) and (self._audio == other._audio) and (self._anc == other._anc)

    def __str__(self) -> str:
        if not self.carried:
            return "no marking"
        def one(v:int|None) -> str:
            return str(v) if (v is not None) else "unset"
        rv = f"video:{one(self._video)} audio:{one(self._audio)} anc:{one(self._anc)}"
        # a partial set is decoded and reported, but no unit takes it
        return rv if self.complete else (rv + " (partial, not taken)")

    def __repr__(self) -> str:
        return str(self)

class DeviceOneIPDetails:
    """ OneIP stream source details for a device """
    def __init__(self, video:OneIPStreamSource|None, audio:OneIPStreamSource|None, anc:OneIPStreamSource|None, arc:OneIPStreamSource|None, tx_rate:int|None, scaling:DeviceOneIPScalingSettings|None, dscp:OneIPDscpConfig|None=None, whole_scaling:bool=False) -> None:
        '''whole_scaling says the scaling block is the sink's whole state rather
        than a write of one part of it, so a mode it does not carry is a mode
        the sink no longer has.'''
        self._whole_scaling = whole_scaling
        self._video = video
        self._audio = audio
        self._anc = anc
        self._arc = arc
        self._tx_rate = tx_rate
        self._scaling = scaling
        self._dscp = dscp

    @property
    def has_config(self) -> bool:
        return False

    @property
    def video(self) -> OneIPStreamSource|None:
        return self._video

    @property
    def audio(self) -> OneIPStreamSource|None:
        return self._audio

    @property
    def anc(self) -> OneIPStreamSource|None:
        return self._anc

    @property
    def arc(self) -> OneIPStreamSource|None:
        return self._arc

    @property
    def tx_rate(self) -> int|None:
        '''Source rate this device transmits at, or None if none is known.

        Only a rate within ONEIP_SOURCE_RATE_MIN..MAX is one a sender meant to
        send; anything else is an absent offer rather than a rate, and merge()
        keeps the previously known value instead of caching what was on the wire.
        '''
        return self._tx_rate

    @property
    def scaling(self) -> DeviceOneIPScalingSettings|None:
        return self._scaling

    @property
    def dscp(self) -> OneIPDscpConfig|None:
        """Per-stream DSCP marking, or None from peers that predate it."""
        return self._dscp

    def merge(self, previous:'DeviceOneIPDetails|None') -> 'DeviceOneIPDetails':
        """
        Carry forward every field this frame did not carry.

        A controller writing one field of a peer's config leaves the others
        zeroed on the wire, so each is applied only behind its own validity
        marker. See FrameV2IPDeviceConfiguration for the markers.
        """
        if (previous is None):
            return self

        if oneip_av_source_valid(self._video, self._anc):
            video, audio, anc = self._video, self._audio, self._anc
        else:
            video, audio, anc = previous._video, previous._audio, previous._anc
        arc = self._arc if oneip_stream_valid(self._arc) else previous._arc
        tx_rate = self._tx_rate if oneip_rate_valid(self._tx_rate) else previous._tx_rate
        # A unit keeps the markings only when all three carry their set bit.
        dscp = self._dscp if ((self._dscp is not None) and self._dscp.complete) else previous._dscp
        scaling = self._merge_scaling(previous._scaling)

        if (video is self._video) and (audio is self._audio) and (anc is self._anc)                 and (arc is self._arc) and (tx_rate == self._tx_rate)                 and (dscp is self._dscp) and (scaling is self._scaling):
            return self
        return DeviceOneIPDetails(video=video, audio=audio, anc=anc, arc=arc,
                                 tx_rate=tx_rate, scaling=scaling, dscp=dscp)

    def _merge_scaling(self, previous:DeviceOneIPScalingSettings|None) -> DeviceOneIPScalingSettings|None:
        """
        Merge a scaling config field by field, the way firmware applies it.

        The mode/refresh pair and the two options groups are separately valid,
        so a write carrying one of them must leave the others as they were. Each
        group is replaced whole behind its own marker, which is what keeps the
        marker itself - and so the knowledge that the device has those options -
        from being taken back by a later write that carries another group.

        A sink's own report with the options marker carries its whole scaling
        state, so there a missing mode is one the sink dropped rather than one
        the frame did not carry.
        """
        incoming = self._scaling
        if (incoming is None) or (previous is None):
            return incoming if (incoming is not None) else previous
        mode_valid = ((incoming.flags & MXR_SCALING_FLAG_MODE_VALID) != 0)
        options_valid = ((incoming.flags & MXR_SCALING_FLAG_OPTIONS_VALID) != 0)
        options2_valid = ((incoming.flags & MXR_SCALING_FLAG_OPTIONS2_VALID) != 0)
        if not mode_valid and not options_valid and not options2_valid:
            # carries no scaling at all
            return previous
        mode_dropped = self._whole_scaling and options_valid and not mode_valid
        mode = incoming.mode if (mode_valid or mode_dropped) else previous.mode
        refresh = incoming.refresh if (mode_valid or mode_dropped) else previous.refresh
        flags = previous.flags
        if mode_valid:
            flags |= MXR_SCALING_FLAG_MODE_VALID
        elif mode_dropped:
            flags &= ~MXR_SCALING_FLAG_MODE_VALID
        if options_valid:
            # Replace AUTO_SCALING alone rather than the whole upper nibble: on a
            # receiver-capable unit running firmware that leaves mxr_scaling_config
            # uninitialised, every other bit up there is stack noise the sender
            # only ever |= its flags onto, and the settings behind the second
            # marker are a group of their own that this write does not speak for.
            flags = (flags & ~MXR_SCALING_FLAG_AUTO_SCALING) | MXR_SCALING_FLAG_OPTIONS_VALID \
                    | (incoming.flags & MXR_SCALING_FLAG_AUTO_SCALING)
        if options2_valid:
            flags = (flags & ~MXR_SCALING_OPTIONS2_SETTINGS) | MXR_SCALING_FLAG_OPTIONS2_VALID \
                    | (incoming.flags & MXR_SCALING_OPTIONS2_SETTINGS)
        if (mode == incoming.mode) and (refresh == incoming.refresh) and (flags == incoming.flags):
            return incoming
        return OneIPScalingSettings(mode=mode, refresh=refresh, flags=flags)

class DeviceOneIPSink:
    """
    A OneIP sink's effective multicast subscriptions and resolved audio format.

    Mirrors the sink-side state broadcast alongside v2ip_device_config updates and
    manual-switch frames. ``addresses`` is None when no active route is announced;
    when present, each stream may still carry an all-zero ip when that stream is
    inactive. ``audio_fmt`` carries the resolved sink audio format (zero fields
    fall back to firmware defaults of 48kHz / 2 channels).

    **An address that reads as unset means "no route, or the sink could not work
    one out", never "definitely not subscribed".** This block is the one part of
    a device configuration with no validity marker of its own, so a sink with
    nothing to say sends zeros and they are stored. A sender leaves it
    empty whenever its own stream configuration does not resolve, which covers
    more than having no route: a selected source whose record has not arrived
    yet, the state after a restart at either end, missing audio bay
    configuration, or a stream failing its validity check. ``audio_fmt`` has a
    second gate of its own, so it can be absent while the addresses are not.

    Expect that reading rather than guarding against it. Any scaling change makes
    the device rebuild and rebroadcast this block, so an empty reading turns up
    most often during exactly the no-signal troubleshooting that prompted the
    change. A device's periodic report puts a real route back within a minute of
    it having one, so a reader that needs certainty should wait one out rather
    than treat the first empty reading as an answer.

    An empty reading is cached rather than dropped on purpose. A sink that has
    genuinely lost its route sends the same zeros, and so does every report after
    it, so refusing them would hold a route that nothing later could clear.

    Only the device's own report sets this. A controller writing another
    device's configuration sends the block zeroed, and that frame is ignored.
    """
    def __init__(self, addresses:OneIPStreamSources|None, audio_fmt:OneIPAudioFormat|None) -> None:
        self._addresses = addresses
        self._audio_fmt = audio_fmt

    @property
    def addresses(self) -> OneIPStreamSources|None:
        return self._addresses

    @property
    def audio_fmt(self) -> OneIPAudioFormat|None:
        return self._audio_fmt

    def __str__(self) -> str:
        return f"addresses=[{self._addresses}] audio_fmt={self._audio_fmt}"

@dataclass(frozen=True)
class TimeZone:
    """
    The time zone a device announces for its mesh.

    The mesh controller announces it with every periodic broadcast, and each
    device of the mesh keeps its clock and its power save windows by it. An
    empty zone and rule mean the controller has none, and the devices keep UTC.
    """
    zone: str
    """The IANA name, such as ``Europe/Amsterdam``."""
    rule: str
    """The POSIX TZ rule the devices keep time by, such as
    ``CET-1CEST,M3.5.0,M10.5.0/3``."""

    def __str__(self) -> str:
        return f"{self.zone} ({self.rule})"

@dataclass(frozen=True)
class DeviceClock:
    """The time a device last announced, and when that arrived here."""
    utc: int
    """Seconds since 1970 UTC, as the device announced them."""
    received: float
    """When the announcement arrived, as time.time() read it."""

    def now(self) -> datetime:
        """The device's clock as of now: the announced time, advanced by how long
        ago it arrived."""
        return datetime.fromtimestamp(self.utc + (time.time() - self.received), timezone.utc)

class OneIPPowerSaveSchedule:
    """
    A OneIP device's daily power save windows, Monday first, in the device's
    time zone.

    Day ``d`` powers down at ``start[d]`` and up again at ``end[d]``, both in
    minutes after midnight. A window belongs to the day it starts on and runs
    past midnight into the next when it ends before it starts; one that ends
    where it starts means no window that day.
    """
    def __init__(self, start:tuple[int, ...]=(0,) * 7, end:tuple[int, ...]=(0,) * 7) -> None:
        if (len(start) != 7) or (len(end) != 7):
            raise ValueError('a power save schedule has one start and one end time per weekday')
        self._start = tuple(start)
        self._end = tuple(end)

    @property
    def start(self) -> tuple[int, ...]:
        """When each day's window starts."""
        return self._start

    @property
    def end(self) -> tuple[int, ...]:
        """When each day's window ends."""
        return self._end

    def window(self, day:int) -> tuple[int, int]|None:
        """The window of ``day``, Monday being 0, or None for a day without one
        or past Sunday."""
        if not (0 <= day < 7) or (self._start[day] == self._end[day]):
            return None
        return (self._start[day], self._end[day])

    def is_valid(self) -> bool:
        """Whether every time is a time of day."""
        return all((0 <= m < ONEIP_MINUTES_PER_DAY) for m in (self._start + self._end))

    def __eq__(self, other:Any) -> bool:
        if not isinstance(other, OneIPPowerSaveSchedule):
            return NotImplemented
        return (self._start, self._end) == (other._start, other._end)

    def __hash__(self) -> int:
        return hash((self._start, self._end))

    def __str__(self) -> str:
        days = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')
        parts = [f"{days[d]} {w[0] // 60:02d}:{w[0] % 60:02d}-{w[1] // 60:02d}:{w[1] % 60:02d}"
                 for d in range(7) if ((w := self.window(d)) is not None)]
        return ", ".join(parts) if parts else "none"

    def __repr__(self) -> str:
        return str(self)

def _vlan_port_index(wire:int) -> int|None:
    '''A port index from its 1-based wire form.'''
    return (wire - 1) if (1 <= wire <= ONEIP_VLAN_PORTS) else None

@dataclass(frozen=True)
class UnitNetConfig:
    """An IP configuration: the addresses a unit uses, or is told to use."""
    ip: str = '0.0.0.0'
    """The address."""
    netmask: str = '0.0.0.0'
    """The netmask."""
    gateway: str = '0.0.0.0'
    """The gateway."""
    dns1: str = '0.0.0.0'
    """The primary DNS server."""
    dns2: str = '0.0.0.0'
    """The secondary DNS server."""

    @property
    def addresses(self) -> tuple[str, str, str, str, str]:
        """The five addresses, in the order the wire carries them."""
        return (self.ip, self.netmask, self.gateway, self.dns1, self.dns2)

    def is_valid(self) -> bool:
        """Whether every address parses, the address is one a unit can hold,
        and the netmask is a run of ones from the top."""
        try:
            for address in self.addresses:
                ipaddress.IPv4Address(address)
            ip = ipaddress.IPv4Address(self.ip)
            mask = int(ipaddress.IPv4Address(self.netmask))
        except ValueError:
            return False
        host = ~mask & 0xFFFFFFFF   # all ones from the bottom for a valid netmask
        return not (ip.is_unspecified or ip.is_multicast or (int(ip) == 0xFFFFFFFF)) \
            and (mask != 0) and ((host & (host + 1)) == 0)

    def __str__(self) -> str:
        return f"{self.ip}/{self.netmask} gw {self.gateway} dns {self.dns1} {self.dns2}"

@dataclass(frozen=True)
class UnitStatus:
    """
    A unit's health and IP configuration, as it last reported them.

    A unit reports this about itself with its periodic broadcast, and within a
    few seconds of a change to its flags, its status or its addresses.
    """
    flags: UnitFlag = UnitFlag(0)
    """The report's flags."""
    uptime: int = 0
    """Seconds since the unit booted."""
    boot_count: int|None = None
    """How often the unit has booted, None while it does not report it."""
    reboot_count: int = 0
    """How often the unit has rebooted."""
    encoder_health: int = 0
    """The encoder's health, a mask of the unit's encoder status bits."""
    decoder_health: int = 0
    """The decoder's health, a mask of the unit's decoder status and state bits."""
    network: UnitNetConfig = UnitNetConfig()
    """The IP configuration in use."""
    fan_rpm: int|None = None
    """The fan speed in RPM, None while the unit does not report it."""
    fan_duty: int = 0
    """The fan duty cycle, in percent."""
    status: int = 0
    """The unit's system status."""
    net_revert_s: int = 0
    """Seconds before a pending IP configuration is reverted."""
    temperatures: tuple[int, ...] = ()
    """Temperatures in degrees Celsius, at most UNIT_MAX_TEMPERATURES of them."""
    status_message: str = ''
    """The message of the current system status."""
    power_save: tuple[UnitPowerSave, ...] = ()
    """What the unit offers at each power save level, from
    OneIPPowerSaveLevel.REDUCED up; empty for a unit that predates the field. A
    route change or a command wakes the unit at every level it supports."""

    def power_save_level(self, level:OneIPPowerSaveLevel|int) -> UnitPowerSave:
        """What the unit offers at a power save level, empty for
        OneIPPowerSaveLevel.NONE or a level it does not report."""
        if not (1 <= int(level) <= len(self.power_save)):
            return UnitPowerSave(0)
        return self.power_save[int(level) - 1]

    @property
    def network_pending(self) -> bool:
        """Whether an IP configuration changed through the mesh waits for the
        mesh controller to confirm it."""
        return UnitFlag.NET_PENDING in self.flags

    def __str__(self) -> str:
        return (f"up {self.uptime}s boots {self.boot_count} reboots {self.reboot_count} "
                f"encoder {self.encoder_health:#x} decoder {self.decoder_health:#x} net [{self.network}] "
                f"fan {self.fan_rpm} rpm {self.fan_duty}% status {self.status} '{self.status_message}' "
                f"temperatures {list(self.temperatures)} flags {self.flags!r}"
                f"{f' power save {[int(p) for p in self.power_save]}' if self.power_save else ''}")

@dataclass(frozen=True)
class OneIPPtpState:
    """
    A OneIP device's PTP state, as it reports it about itself.

    Only the device can read its own video processor, so this is never written
    to a device, and a controller's frame about one carries none.
    """
    flags: OneIPPtpFlag = OneIPPtpFlag(0)
    """The block's flags."""
    mode: OneIPPtpMode|int = OneIPPtpMode.OFF
    """The mode the video processor runs; a raw int for one this library does
    not name."""
    domain: int = 0
    """The domain the video processor runs in."""
    port_state: int = 0
    """The IEEE 1588 portState."""
    lock: OneIPPtpLock|int = OneIPPtpLock.UNLOCKED
    """How far the clock has locked; a raw int for a value this library does
    not name."""
    clock_identity: bytes = bytes(8)
    """The device's own clock identity."""
    grandmaster_identity: bytes = bytes(8)
    """The clock identity of the grandmaster the device runs on, all zero
    while it runs on none."""

    @property
    def followed(self) -> bool:
        """Whether the device locked to a master since its PTP started, so its
        mesh holds a time."""
        return OneIPPtpFlag.FOLLOWED in self.flags

    @property
    def grandmaster(self) -> bytes|None:
        """The grandmaster the device runs on, None while it runs on none."""
        return self.grandmaster_identity if any(self.grandmaster_identity) else None

    def __str__(self) -> str:
        mode = self.mode.name.lower() if isinstance(self.mode, OneIPPtpMode) else self.mode
        lock = self.lock.name.lower() if isinstance(self.lock, OneIPPtpLock) else self.lock
        gm = self.grandmaster.hex(':') if (self.grandmaster is not None) else 'none'
        return (f"{mode} domain {self.domain} port state {self.port_state} {lock}"
                f"{' followed' if self.followed else ''} clock {self.clock_identity.hex(':')} grandmaster {gm}")

@dataclass(frozen=True)
class OneIPVlan:
    """
    VLAN tagging on a OneIP device's uplink.

    Only the device knows what it runs, so this is what it reported about
    itself. A change written to it is applied at once and stays PENDING until
    the mesh controller confirms it, which proves the device still reaches the
    mesh and the mesh still reaches it; unconfirmed, the device reverts it.
    """
    flags: OneIPVlanFlag = OneIPVlanFlag(0)
    """The block's flags."""
    device: int = 0
    """The VLAN id of the device's own traffic, 0 for untagged."""
    port: tuple[int, ...] = (0,) * ONEIP_VLAN_PORTS
    """The VLAN id each downlink port carries, 0 to share the device's untagged
    traffic, indexed as ONEIP_VLAN_PORTS orders them."""
    uplink: int = 0
    """The port pinned as the uplink as 1 + its index, 0 to detect it."""
    active_uplink: int = 0
    """Reported by the device: the port in use as the uplink, as 1 + its index."""
    revert_s: int = 0
    """Reported by the device: the seconds before a pending configuration is
    reverted."""

    @property
    def trunk(self) -> bool:
        """Whether untagged frames arriving on the uplink are dropped."""
        return OneIPVlanFlag.TRUNK in self.flags

    @property
    def is_pending(self) -> bool:
        """Whether the device reverts this configuration unless the mesh
        controller confirms it."""
        return OneIPVlanFlag.PENDING in self.flags

    @property
    def has_sfp(self) -> bool:
        """Whether the device has an SFP port."""
        return OneIPVlanFlag.HAS_SFP in self.flags

    @property
    def pinned_uplink_port(self) -> int|None:
        """The index of the port pinned as the uplink, None when the device
        detects it."""
        return _vlan_port_index(self.uplink)

    @property
    def active_uplink_port(self) -> int|None:
        """The index of the port the device uses as its uplink, None for a value
        that names no port."""
        return _vlan_port_index(self.active_uplink)

    def is_valid(self) -> bool:
        """Whether every VLAN id is at most ONEIP_VLAN_ID_MAX and the uplink is
        detected or names a port."""
        ids = (self.device,) + tuple(self.port)
        return (len(self.port) == ONEIP_VLAN_PORTS) \
            and all((0 <= i <= ONEIP_VLAN_ID_MAX) for i in ids) \
            and ((self.uplink == 0) or (self.pinned_uplink_port is not None))

    def __str__(self) -> str:
        uplink = f"port {self.pinned_uplink_port}" if (self.pinned_uplink_port is not None) else "detected"
        rv = f"device {self.device}, ports {'/'.join(str(p) for p in self.port)}, uplink {uplink}"
        if self.trunk:
            rv += ", trunk"
        if self.is_pending:
            rv += f", pending ({self.revert_s}s)"
        return rv

def _wire_enum(cls:Any, value:int) -> Any:
    '''The member value names, or the raw value where this library names none.'''
    try:
        return cls(value)
    except ValueError:
        return value

@dataclass(frozen=True)
class OneIPPtpMessages:
    """
    How a OneIP device paces its PTP messages, its SAP timings and its streams'
    TTL, which a frame carries in the same block. Each value is behind its own bit of
    OneIPDeviceSettings.valid, one of ONEIP_DEVICE_SETTINGS_BLOCK.

    Intervals are base-2 logarithms of seconds, so -3 is 125 ms and 1 is 2 s.
    """
    log_announce_interval: int = 0
    """Between announce messages, behind PTP_ANNOUNCE."""
    log_sync_interval: int = 0
    """Between sync messages, behind PTP_SYNC."""
    log_delay_req_interval: int = 0
    """Between delay requests, behind PTP_DELAY_REQ."""
    announce_timeout: int = 0
    """The announce intervals before a silent master is dropped, behind
    PTP_ANNOUNCE_TIMEOUT."""
    dscp: int = 0
    """The DSCP of the messages, at most ONEIP_DSCP_MAX, behind PTP_DSCP."""
    sap_expire_min: int = 0
    """The minutes after which a SAP announcement the device heard is
    forgotten, behind SAP_EXPIRE."""
    sap_interval_s: int = 0
    """The seconds between the device's SAP announcements, behind SAP_INTERVAL."""
    stream_ttl: int = 0
    """The TTL of the device's streams, 1 to 255, behind STREAM_TTL. A device
    whose video processor cannot change it keeps the setting and sends
    ONEIP_STREAM_TTL_DEFAULT."""

    def merge(self, other:'OneIPPtpMessages', which:OneIPDeviceSetting) -> 'OneIPPtpMessages':
        """The values behind the bits of which copied from other, the rest kept."""
        S = OneIPDeviceSetting
        return OneIPPtpMessages(
            log_announce_interval=(other if (S.PTP_ANNOUNCE in which) else self).log_announce_interval,
            log_sync_interval=(other if (S.PTP_SYNC in which) else self).log_sync_interval,
            log_delay_req_interval=(other if (S.PTP_DELAY_REQ in which) else self).log_delay_req_interval,
            announce_timeout=(other if (S.PTP_ANNOUNCE_TIMEOUT in which) else self).announce_timeout,
            dscp=(other if (S.PTP_DSCP in which) else self).dscp,
            sap_expire_min=(other if (S.SAP_EXPIRE in which) else self).sap_expire_min,
            sap_interval_s=(other if (S.SAP_INTERVAL in which) else self).sap_interval_s,
            stream_ttl=(other if (S.STREAM_TTL in which) else self).stream_ttl)

    def describe(self, valid:OneIPDeviceSetting) -> list[str]:
        """The values behind the bits of valid, one "name=value" each."""
        S = OneIPDeviceSetting
        return [f"{label}={value}" for bit, label, value in (
                    (S.PTP_ANNOUNCE, 'ptp_announce', self.log_announce_interval),
                    (S.PTP_SYNC, 'ptp_sync', self.log_sync_interval),
                    (S.PTP_DELAY_REQ, 'ptp_delay_req', self.log_delay_req_interval),
                    (S.PTP_ANNOUNCE_TIMEOUT, 'ptp_announce_timeout', self.announce_timeout),
                    (S.PTP_DSCP, 'ptp_dscp', self.dscp),
                    (S.SAP_EXPIRE, 'sap_expire_min', self.sap_expire_min),
                    (S.SAP_INTERVAL, 'sap_interval_s', self.sap_interval_s),
                    (S.STREAM_TTL, 'stream_ttl', self.stream_ttl))
                if (bit in valid)]

@dataclass(frozen=True)
class OneIPSinkSdp:
    """
    What a OneIP output plays from a session description, as it last reported
    it. The stream's fields are zero while it plays none.
    """
    flags: OneIPSdpFlag = OneIPSdpFlag(0)
    """The report's flags."""
    screen: int = 0
    """What the output shows while it plays audio alone, as the wire value."""
    encoding: OneIPSdpEncoding|int = OneIPSdpEncoding.NONE
    """The sample encoding; a raw int for one this library does not name."""
    channels: int = 0
    payload_type: int = 0
    """The RTP payload type."""
    media_clock: OneIPSdpMediaClock|int = OneIPSdpMediaClock.NONE
    ref_clock: OneIPSdpRefClock|int = OneIPSdpRefClock.NONE
    clock_mode: OneIPSdpClockMode|int = OneIPSdpClockMode.ARRIVAL
    """What the video processor times the stream by, behind OneIPSdpFlag.CLOCK."""
    clock_state: OneIPSdpClockState|int = OneIPSdpClockState.IDLE
    """How far the video processor has got with its timing, behind OneIPSdpFlag.CLOCK."""
    port: int = 0
    rate_hz: int = 0
    """The sample rate in Hz."""
    media_clock_offset: int = 0
    group: str = '0.0.0.0'
    """The multicast group."""
    name: str = ''
    """The session name."""
    layout: str = ''
    """The channel layout."""

    @property
    def active(self) -> bool:
        """Whether the output plays a stream from a description."""
        return OneIPSdpFlag.ACTIVE in self.flags

    def __str__(self) -> str:
        if not self.active:
            return "none"
        encoding = self.encoding.name if isinstance(self.encoding, OneIPSdpEncoding) else self.encoding
        return (f"'{self.name}' {self.group}:{self.port} {encoding} {self.channels}ch {self.rate_hz}Hz"
                f"{' audio only' if (OneIPSdpFlag.AUDIO_ONLY in self.flags) else ''}")

@dataclass(frozen=True)
class OneIPTestTone:
    """A OneIP sink's test tone."""
    mode: OneIPToneMode|int = OneIPToneMode.OFF
    """What plays; a raw int for a mode this library does not name."""
    freq: int = 0
    """The frequency, in Hz."""
    level: int = 0
    """The level, in dBFS."""
    channels: int = 0
    """The channels it plays on."""
    rate: int = 0
    """The sample rate, in Hz."""

    def is_valid(self) -> bool:
        """Whether a sink plays this tone: a mode it names, and every value in
        range. A line-up tone needs two channels or more."""
        min_channels = 2 if (self.mode == OneIPToneMode.LINEUP) else 1
        return isinstance(self.mode, OneIPToneMode) \
            and (ONEIP_TONE_FREQ_MIN <= self.freq <= ONEIP_TONE_FREQ_MAX) \
            and (ONEIP_TONE_LEVEL_MIN <= self.level <= 0) \
            and (min_channels <= self.channels <= ONEIP_TONE_CHANNELS_MAX) \
            and (self.rate in ONEIP_TONE_RATES)

@dataclass(frozen=True)
class OneIPTestSync:
    """
    A OneIP sink's lip-sync flash: a pattern frame is marked every ``period``, the
    frame ``lead`` after a mark flashes white, and a BEEP tone starts ``offset``
    sample periods after it.

    The offset is a calibration: nothing measures the sink's own delay between
    a picture and a sample reaching the HDMI link, and a display adds its own.
    """
    period: int = 0
    """Every this many pattern frames is marked, 0 for none."""
    lead: int = 0
    """The frame this many after a mark flashes."""
    offset: int = 0
    """The sample periods between a mark and the beep."""
    beep_ms: int = 0
    """How long the beep lasts, in milliseconds."""

    def is_valid(self) -> bool:
        """Whether a sink takes these settings: the lead is below the period, or
        0 without one, and the period, offset and beep are in range."""
        lead_ok = (self.lead == 0) if (self.period == 0) else (0 <= self.lead < self.period)
        return lead_ok and (0 <= self.period <= 0xFFFF) \
            and (0 <= self.offset <= ONEIP_SYNC_OFFSET_MAX) \
            and (ONEIP_SYNC_BEEP_MS_MIN <= self.beep_ms <= ONEIP_SYNC_BEEP_MS_MAX)

@dataclass(frozen=True)
class OneIPTestcard:
    """
    The test card a OneIP sink draws on its output, as it last reported it.

    A sink reports it only when asked, with request_oneip_testcard() or in answer
    to a change. The counters run free and wrap.
    """
    flags: OneIPTestcardFlag = OneIPTestcardFlag(0)
    """What the sink reports about its test card."""
    pattern: OneIPTestPattern|int = OneIPTestPattern.OFF
    """The pattern; a raw int for a pattern this library does not name."""
    colour: int = 0
    """The colour of a FLAT pattern, 0xRRGGBB."""
    tone: OneIPTestTone = OneIPTestTone()
    """The tone."""
    sync: OneIPTestSync = OneIPTestSync()
    """The lip-sync flash."""
    frames: int = 0
    """Pattern frames sent."""
    periods: int = 0
    """Sample periods since the tone started."""
    marks: int = 0
    """Lip-sync marks the tone has seen."""

    @property
    def supported(self) -> bool:
        """Whether the sink can draw the test card."""
        return OneIPTestcardFlag.SUPPORTED in self.flags

class OneIPDeviceSettings:
    """
    The device settings of a OneIP unit, as it reports them and as its controller
    changes them.

    Each setting is carried only behind its bit in ``valid``, so a frame changes
    one setting without restating the others, and a device reports only the
    settings it has. Read a setting through ``get()`` and the profile
    properties, which answer None for one the device has not reported.
    """
    def __init__(self, valid:OneIPDeviceSetting=OneIPDeviceSetting(0),
                 flags:OneIPDeviceSetting=OneIPDeviceSetting(0), ir_profiles:int=0,
                 ir_profile:int=0, ir_profile_sink:int=0, auto_power_save:int=0,
                 power_save:OneIPPowerSaveSchedule|None=None, ptp_mode:OneIPPtpMode|int=OneIPPtpMode.OFF,
                 ptp_domain:int=0, ptp_priority1:int=0,
                 power_save_level:OneIPPowerSaveLevel|int=OneIPPowerSaveLevel.NONE,
                 ptp_messages:OneIPPtpMessages|None=None) -> None:
        self._valid = OneIPDeviceSetting(valid)
        self._flags = OneIPDeviceSetting(flags)
        self._ir_profiles = ir_profiles
        self._ir_profile = ir_profile
        self._ir_profile_sink = ir_profile_sink
        self._auto_power_save = auto_power_save
        self._power_save = power_save if (power_save is not None) else OneIPPowerSaveSchedule()
        self._ptp_mode = int(ptp_mode)
        self._ptp_domain = ptp_domain
        self._ptp_priority1 = ptp_priority1
        self._power_save_level = int(power_save_level)
        self._ptp_messages = ptp_messages if (ptp_messages is not None) else OneIPPtpMessages()

    @property
    def valid(self) -> OneIPDeviceSetting:
        """The settings reported so far."""
        return self._valid

    @property
    def flags(self) -> OneIPDeviceSetting:
        """The values of the on/off settings among ``valid``."""
        return self._flags

    def get(self, setting:OneIPDeviceSetting) -> bool|None:
        """Whether an on/off setting is on, None while the device has not reported it."""
        if ((self._valid & setting) != setting):
            return None
        return ((self._flags & setting) == setting)

    @property
    def ir_profile(self) -> int|None:
        """The global infrared port's profile, None while it is not reported."""
        if (OneIPDeviceSetting.IR_PROFILE not in self._valid):
            return None
        return self._ir_profile

    @property
    def ir_profile_sink(self) -> int|None:
        """The output infrared port's profile, None while it is not reported.
        ONEIP_IR_PROFILE_NOT_SET means the port follows the global one."""
        if (OneIPDeviceSetting.IR_PROFILE_SINK not in self._valid):
            return None
        return self._ir_profile_sink

    @property
    def stored_ir_profiles(self) -> int|None:
        """The infrared profiles stored on the device, bit n for profile n, None
        while it is not reported."""
        if (OneIPDeviceSetting.IR_PROFILES not in self._valid):
            return None
        return self._ir_profiles

    @property
    def auto_power_save(self) -> int|None:
        """The idle minutes before the device powers down by itself, 0 for never,
        None while it is not reported."""
        if (OneIPDeviceSetting.AUTO_POWER_SAVE not in self._valid):
            return None
        return self._auto_power_save

    @property
    def power_save_schedule(self) -> OneIPPowerSaveSchedule|None:
        """The daily power save windows, None while they are not reported."""
        if (OneIPDeviceSetting.POWER_SAVE_SCHEDULE not in self._valid):
            return None
        return self._power_save

    @property
    def ptp_mode(self) -> OneIPPtpMode|int|None:
        """The PTP mode, a raw int for one this library does not name, None
        while it is not reported."""
        if (OneIPDeviceSetting.PTP_MODE not in self._valid):
            return None
        return _wire_enum(OneIPPtpMode, self._ptp_mode)

    @property
    def ptp_domain(self) -> int|None:
        """The PTP domain, up to ONEIP_PTP_DOMAIN_MAX, None while it is not reported."""
        if (OneIPDeviceSetting.PTP_DOMAIN not in self._valid):
            return None
        return self._ptp_domain

    @property
    def ptp_priority1(self) -> int|None:
        """The priority1 the device announces as a PTP grandmaster, lower
        winning, None while it is not reported."""
        if (OneIPDeviceSetting.PTP_PRIORITY1 not in self._valid):
            return None
        return self._ptp_priority1

    @property
    def power_save_level(self) -> OneIPPowerSaveLevel|int|None:
        """The level the device powers down to in power save, a raw int for one
        this library does not name, None while it is not reported."""
        if (OneIPDeviceSetting.POWER_SAVE_LEVEL not in self._valid):
            return None
        return _wire_enum(OneIPPowerSaveLevel, self._power_save_level)

    @property
    def ptp_messages(self) -> OneIPPtpMessages|None:
        """The settings carried in the block of their own the device has
        reported, None while it has reported none of them; each value is
        meaningful only behind its own bit of valid."""
        if not (self._valid & ONEIP_DEVICE_SETTINGS_BLOCK):
            return None
        return self._ptp_messages

    def merge(self, previous:'OneIPDeviceSettings|None') -> 'OneIPDeviceSettings':
        """
        Fold this received block onto the cached one.

        Each bit in this block's ``valid`` replaces its own setting and leaves
        the others alone, so a write about one setting does not clear what was
        known about the rest. The exception is POWER_SAVE_DISABLED: a device
        takes a power save level as switching it off.
        """
        if (previous is None):
            previous = OneIPDeviceSettings()
        valid = self._valid
        flags = (previous._flags & ~valid) | (self._flags & valid)
        if (OneIPDeviceSetting.POWER_SAVE_LEVEL in valid) and (OneIPDeviceSetting.POWER_SAVE_DISABLED not in valid):
            flags &= ~OneIPDeviceSetting.POWER_SAVE_DISABLED
        return OneIPDeviceSettings(
            valid=(previous._valid | valid),
            flags=flags,
            ir_profiles=(self._ir_profiles if (OneIPDeviceSetting.IR_PROFILES in valid)
                         else previous._ir_profiles),
            ir_profile=(self._ir_profile if (OneIPDeviceSetting.IR_PROFILE in valid)
                        else previous._ir_profile),
            ir_profile_sink=(self._ir_profile_sink if (OneIPDeviceSetting.IR_PROFILE_SINK in valid)
                             else previous._ir_profile_sink),
            auto_power_save=(self._auto_power_save if (OneIPDeviceSetting.AUTO_POWER_SAVE in valid)
                             else previous._auto_power_save),
            power_save=(self._power_save if (OneIPDeviceSetting.POWER_SAVE_SCHEDULE in valid)
                        else previous._power_save),
            ptp_mode=(self._ptp_mode if (OneIPDeviceSetting.PTP_MODE in valid)
                      else previous._ptp_mode),
            ptp_domain=(self._ptp_domain if (OneIPDeviceSetting.PTP_DOMAIN in valid)
                        else previous._ptp_domain),
            ptp_priority1=(self._ptp_priority1 if (OneIPDeviceSetting.PTP_PRIORITY1 in valid)
                           else previous._ptp_priority1),
            power_save_level=(self._power_save_level if (OneIPDeviceSetting.POWER_SAVE_LEVEL in valid)
                              else previous._power_save_level),
            ptp_messages=previous._ptp_messages.merge(self._ptp_messages, valid))

    def as_applied_to(self, reported:OneIPDeviceSetting) -> 'OneIPDeviceSettings':
        """
        This block limited to what a device takes from a write about it.

        A device applies a setting only if it has it, a profile, PTP mode, PTP
        domain, power save level or PTP DSCP only within its range, a stream
        TTL only when it is not 0, and never what only it can report about
        itself.
        """
        valid = (self._valid & reported) & ~ONEIP_DEVICE_SETTINGS_REPORTED_ONLY
        if not (0 <= self._ir_profile < ONEIP_IR_PROFILE_MAX):
            valid &= ~OneIPDeviceSetting.IR_PROFILE
        if not (ONEIP_IR_PROFILE_NOT_SET <= self._ir_profile_sink < ONEIP_IR_PROFILE_MAX):
            valid &= ~OneIPDeviceSetting.IR_PROFILE_SINK
        if (self._ptp_mode > OneIPPtpMode.AUTO):
            valid &= ~OneIPDeviceSetting.PTP_MODE
        if (self._ptp_domain > ONEIP_PTP_DOMAIN_MAX):
            valid &= ~OneIPDeviceSetting.PTP_DOMAIN
        if (self._power_save_level > OneIPPowerSaveLevel.OFF):
            valid &= ~OneIPDeviceSetting.POWER_SAVE_LEVEL
        if (self._ptp_messages.dscp > ONEIP_DSCP_MAX):
            valid &= ~OneIPDeviceSetting.PTP_DSCP
        if (self._ptp_messages.stream_ttl == 0):
            valid &= ~OneIPDeviceSetting.STREAM_TTL
        return OneIPDeviceSettings(valid=valid, flags=self._flags, ir_profiles=self._ir_profiles,
                                  ir_profile=self._ir_profile, ir_profile_sink=self._ir_profile_sink,
                                  auto_power_save=self._auto_power_save, power_save=self._power_save,
                                  ptp_mode=self._ptp_mode, ptp_domain=self._ptp_domain,
                                  ptp_priority1=self._ptp_priority1,
                                  power_save_level=self._power_save_level,
                                  ptp_messages=self._ptp_messages)

    def __eq__(self, other:Any) -> bool:
        if not isinstance(other, OneIPDeviceSettings):
            return NotImplemented
        return ((self._valid, self._flags, self._ir_profiles, self._ir_profile, self._ir_profile_sink,
                 self._auto_power_save, self._power_save, self._ptp_mode, self._ptp_domain,
                 self._ptp_priority1, self._power_save_level, self._ptp_messages)
                == (other._valid, other._flags, other._ir_profiles, other._ir_profile, other._ir_profile_sink,
                    other._auto_power_save, other._power_save, other._ptp_mode, other._ptp_domain,
                    other._ptp_priority1, other._power_save_level, other._ptp_messages))

    def __ne__(self, other:Any) -> bool:
        result = self.__eq__(other)
        return result if (result is NotImplemented) else (not result)

    def __str__(self) -> str:
        parts = [f"{setting.name}={'on' if self.get(setting) else 'off'}"
                 for setting in OneIPDeviceSetting
                 if (setting in ONEIP_DEVICE_SETTING_SWITCHES) and (self.get(setting) is not None)]
        if (self.ir_profile is not None):
            parts.append(f"ir_profile={self.ir_profile}")
        if (self.ir_profile_sink is not None):
            parts.append(f"ir_profile_sink={self.ir_profile_sink}")
        if (self.stored_ir_profiles is not None):
            parts.append(f"ir_profiles={self.stored_ir_profiles:#x}")
        if ((clock_set := self.get(OneIPDeviceSetting.CLOCK_SET)) is not None):
            parts.append(f"clock_set={'yes' if clock_set else 'no'}")
        if (self.auto_power_save is not None):
            parts.append(f"auto_power_save={self.auto_power_save}")
        if (self.power_save_schedule is not None):
            parts.append(f"power_save=[{self.power_save_schedule}]")
        if ((mode := self.ptp_mode) is not None):
            parts.append(f"ptp_mode={mode.name.lower() if isinstance(mode, OneIPPtpMode) else mode}")
        if (self.ptp_domain is not None):
            parts.append(f"ptp_domain={self.ptp_domain}")
        if (self.ptp_priority1 is not None):
            parts.append(f"ptp_priority1={self.ptp_priority1}")
        if ((level := self.power_save_level) is not None):
            parts.append(f"power_save_level={level.name.lower() if isinstance(level, OneIPPowerSaveLevel) else level}")
        parts += self._ptp_messages.describe(self._valid)
        return " ".join(parts)

    def __repr__(self) -> str:
        return str(self)

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
    def features(self) -> DeviceFeature|None:
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
    def is_oneip(self) -> bool:
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
        '''True if this device supports audio matrixing'''

    @property
    @abstractmethod
    def temperatures(self) -> dict[str,int]:
        ''' temperature sensor reports '''

    @property
    @abstractmethod
    def oneip_features(self) -> 'OneIPVideoProcessorFeature|None':
        '''What this device's video processor supports, None until it has said.

        A device reports the mask only on a configuration it sends about itself,
        and reports nothing at all until its processor has answered - which
        looks the same on the wire as a processor without any of the optional
        commands, so neither is read as a capability set.
        '''

    @property
    @abstractmethod
    def oneip_sources(self) -> OneIPStreamSourcesList|None:
        '''OneIP stream source addresses'''

    @property
    @abstractmethod
    def oneip_stats(self) -> OneIPDeviceStats|None:
         '''OneIP encoder/decoder statistics'''

    @property
    @abstractmethod
    def oneip_details(self) -> DeviceOneIPDetails|None:
        '''OneIP encoder/decoder configuration'''

    @property
    @abstractmethod
    def oneip_sink(self) -> DeviceOneIPSink|None:
        '''OneIP sink-side multicast subscriptions and resolved audio format (None until first announced)'''

    @property
    @abstractmethod
    def oneip_settings(self) -> OneIPDeviceSettings|None:
        '''The OneIP device settings, None until the device has reported any.

        A device reports only the settings it has, so one missing from valid
        once the rest have arrived is one the device does not have.
        '''

    @property
    @abstractmethod
    def oneip_vlan(self) -> OneIPVlan|None:
        '''The VLAN configuration this OneIP device last reported about itself,
        None until it has reported one.'''

    @property
    @abstractmethod
    def unit_status(self) -> UnitStatus|None:
        '''The health and IP configuration this unit last reported, None until
        it has reported them.'''

    @abstractmethod
    async def clear_unit_status(self) -> bool:
        '''clear the unit's current system status'''

    @abstractmethod
    async def upgrade_unit_video_processor(self, force:bool=False) -> bool:
        '''upgrade the unit's video processor to the latest image it holds'''

    @abstractmethod
    async def set_unit_dhcp(self) -> bool:
        '''switch the unit to an IP configuration from DHCP'''

    @abstractmethod
    async def set_unit_network(self, network:UnitNetConfig) -> bool:
        '''give the unit a static IP configuration'''

    @abstractmethod
    async def confirm_unit_network(self) -> bool:
        '''keep the unit's pending IP configuration'''

    @property
    @abstractmethod
    def oneip_ptp(self) -> OneIPPtpState|None:
        '''The PTP state this OneIP device last reported about itself, None
        until it has reported one, and while it has no PTP to report: none on
        its video processor, or in power save.'''

    @property
    @abstractmethod
    def oneip_testcard(self) -> OneIPTestcard|None:
        '''The test card this OneIP sink last reported, None until it has.

        A sink reports it only when asked or in answer to a change.'''

    @property
    @abstractmethod
    def time_zone(self) -> TimeZone|None:
        '''The time zone this device announced for its mesh, None until it has.

        The mesh controller announces it with every periodic broadcast, empty
        when it has none.'''

    @property
    @abstractmethod
    def clock(self) -> datetime|None:
        '''This device's clock as of now, None until it has announced one.

        The time it last announced, advanced by how long ago that arrived. The
        mesh controller announces its clock with every periodic broadcast, and
        only once it has been set.'''

    @property
    @abstractmethod
    def oneip_source_local(self) -> OneIPStreamSources|None:
         ''' local v2ip source addresses '''

    @property
    @abstractmethod
    def mesh_master(self) -> 'DeviceBase|None':
        '''The device that is the master device in the OneIP mesh to which this device belongs'''

    @mesh_master.setter
    @abstractmethod
    def mesh_master(self, master:MxrDeviceUid) -> None:
        '''Change the master device of this device'''

    @property
    @abstractmethod
    def mesh_master_uid(self) -> MxrDeviceUid|None:
        '''UID of the mesh controller this device reports, None while it has named none.

        Distinct from mesh_master, which falls back to the device itself. A
        device that has named no controller is not a device that follows nobody:
        a client that has just started knows nothing about anyone for as long as
        a broadcast period.
        '''

    @property
    @abstractmethod
    def protocol(self) -> int:
        """Highest protocol version this device advertises, or 0 if none has been seen."""

    @abstractmethod
    def supports_opcode(self, opcode:int) -> bool:
        """True when this device can receive opcode.

        Each opcode has a minimum protocol version, and a device whose cap is
        lower drops the frame without answering - there is no NAK at any layer,
        so an ungated send looks like success. A device that has advertised no
        version yet returns True: refusing on that would break every send made
        before the first hello arrives, and the firmware itself only compares
        against a version it has.
        """

    @property
    @abstractmethod
    def is_mesh_master(self) -> bool:
        '''True if this device is the master device of a OneIP mesh'''

    @property
    @abstractmethod
    def is_management(self) -> bool:
        '''True when this device announces itself as a writer of other devices'
        configuration: MANAGER, which external management applications set and
        no device firmware does, or MESH_MASTER, which a controlling device sets.

        Whether a unit takes a write from it is the unit's question, not this
        device's. A unit takes one from a MANAGER, or from the controller it
        follows (its mesh_master_uid), whatever bits that controller announces;
        MESH_MASTER stands in for that only until the unit has named one.
        '''

    @property
    @abstractmethod
    def is_oneip_sink(self) -> bool:
        '''True if this device decodes a OneIP stream, which is what carries the scaling settings'''

    @property
    @abstractmethod
    def is_mesh_member(self) -> bool:
        '''True if this device is a member of a OneIP mesh'''

    @property
    @abstractmethod
    def is_oneip_multiviewer(self) -> bool:
        '''True if this device is a OneIP Multiviewer'''

    @property
    @abstractmethod
    def supports_video_wall(self) -> bool:
        '''True if this sink can crop its source to a video wall window (MXR_FEATURE_VIDEO_WALL)'''

    @property
    @abstractmethod
    def config_initialised(self) -> bool:
        '''True if every configuration block this device broadcasts is fully written.

        A device without MXR_FEATURE_CONFIG_INITIALISED builds some config
        payloads from stack locals it never zeroes, so these are unreliable from
        it: the scaling block in V2IP_DEVICE_CFG, bay 0's addresses in
        SYS_BAY_V2IP_SOURCES, and the padding beside the rc target in
        RC_SETTINGS. None of that is detectable within a frame.
        '''

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
    def oneip_firmware_versions(self) -> dict[FirmwareType,FirmwareVersion]|None:
        '''OneIP video processor firmware versions'''

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
    def oneip_source(self, bay:BayBase) -> OneIPStreamSources|None:
        '''Get the OneIP source addresses for the given bay'''

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
    def merge_oneip_sources(self, first:int, total:int, page:'OneIPStreamSourcesList') -> None:
        '''merge one frame of this device's OneIP source list into the cached list'''

    @abstractmethod
    def note_link_config(self) -> None:
        '''internal callback: a page of the link configuration was received'''

    @abstractmethod
    def note_bay_config(self) -> None:
        '''internal callback: the primary bay configuration was received'''

    @abstractmethod
    async def get_api(self, uri:str) -> dict[str, Any]|None:
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
    async def ping(self) -> bool:
        '''ask this device to announce itself now'''

    @abstractmethod
    async def mesh_promote(self) -> bool:
        '''promote to mesh master'''

    @abstractmethod
    async def auto_assign_oneip_source_addresses(self) -> bool:
        '''hand this OneIP source's stream addresses back to automatic assignment'''

    @abstractmethod
    async def mesh_remove(self) -> bool:
        '''remove from mesh'''

    @abstractmethod
    async def read_stats(self, enable:bool) -> bool:
        '''start or stop dumping stats'''

    @abstractmethod
    async def set_oneip_auto_scaling(self, enabled:bool) -> bool:
        '''turn this sink's automatic scaling on or off'''

    @abstractmethod
    async def set_oneip_output_mode(self, mode:'OneIPOutputMode') -> bool:
        '''set the output format this sink scales to'''

    @abstractmethod
    async def clear_oneip_output_mode(self) -> bool:
        '''clear the output format this sink is configured to scale to'''

    @abstractmethod
    async def set_oneip_setting(self, setting:OneIPDeviceSetting, enabled:bool) -> bool:
        '''switch on/off OneIP device settings, all to the same value'''

    @abstractmethod
    async def set_oneip_ir_profile(self, profile:int) -> bool:
        '''set the infrared profile of the device's global infrared port'''

    @abstractmethod
    async def set_oneip_sink_ir_profile(self, profile:int) -> bool:
        '''set the infrared profile of the device's output infrared port'''

    @abstractmethod
    async def set_oneip_auto_power_save(self, minutes:int) -> bool:
        '''set the idle minutes before the device powers down by itself, 0 for never'''

    @abstractmethod
    async def set_oneip_power_save_schedule(self, schedule:OneIPPowerSaveSchedule) -> bool:
        '''set the device's daily power save windows'''

    @abstractmethod
    async def set_oneip_ptp_mode(self, mode:OneIPPtpMode) -> bool:
        '''set the PTP mode the device runs'''

    @abstractmethod
    async def set_oneip_ptp_domain(self, domain:int) -> bool:
        '''set the PTP domain the device runs in'''

    @abstractmethod
    async def set_oneip_ptp_priority1(self, priority1:int) -> bool:
        '''set the priority1 the device announces as a PTP grandmaster'''

    @abstractmethod
    async def set_oneip_power_save_level(self, level:OneIPPowerSaveLevel) -> bool:
        '''set the level the device powers down to in power save'''

    @abstractmethod
    async def set_oneip_ptp_messages(self, which:OneIPDeviceSetting, messages:OneIPPtpMessages) -> bool:
        '''set how the device paces its PTP messages, its SAP timings and its streams' TTL: the values of messages behind the bits of which'''

    @abstractmethod
    async def set_oneip_vlan(self, vlan:OneIPVlan) -> bool:
        '''change the device's VLAN configuration'''

    @abstractmethod
    async def set_audio_endpoint_locked(self, endpoint:int, locked:bool) -> bool:
        '''lock or unlock the audio source of one of this device's audio endpoints'''

    @abstractmethod
    async def request_oneip_testcard(self) -> bool:
        '''ask this sink for its test card'''

    @property
    @abstractmethod
    def oneip_sink_sdp(self) -> OneIPSinkSdp|None:
        '''What this OneIP output plays from a session description, as it last
        reported it, None until it has. It reports when that changes and at
        least once a minute.'''

    @abstractmethod
    async def play_oneip_sdp(self, sdp:str) -> bool:
        '''have this OneIP output play the stream a session description describes'''

    @abstractmethod
    async def stop_oneip_sdp(self) -> bool:
        '''stop the stream this OneIP output plays from a session description'''

    @abstractmethod
    async def set_oneip_sdp_screen(self, screen:int) -> bool:
        '''set what this OneIP output shows while it plays audio alone, as the wire value'''

    @abstractmethod
    async def request_oneip_sink_sdp(self) -> bool:
        '''ask this OneIP output what it plays from a session description now'''

    @abstractmethod
    async def set_oneip_test_pattern(self, pattern:OneIPTestPattern, colour:int=0) -> bool:
        '''show a test pattern on this sink's output'''

    @abstractmethod
    async def set_oneip_test_tone(self, tone:OneIPTestTone) -> bool:
        '''play a test tone on this sink's output'''

    @abstractmethod
    async def set_oneip_test_sync(self, sync:OneIPTestSync) -> bool:
        '''set this sink's lip-sync flash'''

    @abstractmethod
    async def get_log(self) -> str|None:
        '''read the log from the device and return it as string'''

    @abstractmethod
    def on_mxr_update(self, data:object) -> None:
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
        return LinkFeature.AUDIO_OPTICAL in m or LinkFeature.AUDIO_ANALOG in m

    @property
    def is_video(self) -> bool:
        ''' True if this is a video link '''
        return LinkFeature.VIDEO_HDMI in self.features_mask

    @property
    def features(self) -> list[str]:
        ''' supported link features as list of string '''
        ft:list[str] = []
        m = self.features_mask
        if LinkFeature.VIDEO_HDMI in m:
            ft.append("HDMI")
        if LinkFeature.AUDIO_OPTICAL in m:
            ft.append("optical audio")
        if LinkFeature.AUDIO_ANALOG in m:
            ft.append("analog audio")
        if LinkFeature.IR in m:
            ft.append("IR")
        if LinkFeature.RC in m:
            ft.append("RC")
        return ft

    @property
    def features_mask(self) -> LinkFeature:
        ''' supported link features as bitmask '''
        if not self.connected:
            return LinkFeature(0)
        left = self.bay.features
        right = self.linked_bay.features if (self.linked_bay is not None) else BayFeaturesMask(0)
        rv = LinkFeature(0)
        if BayFeaturesMask.HDMI_OUT in left:
            if BayFeaturesMask.HDMI_IN in right:
                rv |= LinkFeature.VIDEO_HDMI
        if BayFeaturesMask.HDMI_IN in left:
            if BayFeaturesMask.HDMI_OUT in right:
                rv |= LinkFeature.VIDEO_HDMI
        if BayFeaturesMask.AUDIO_DIG_OUT in left:
            if BayFeaturesMask.AUDIO_DIG_IN in right:
                rv |= LinkFeature.AUDIO_OPTICAL
        if BayFeaturesMask.AUDIO_DIG_IN in left:
            if BayFeaturesMask.AUDIO_DIG_OUT in right:
                rv |= LinkFeature.AUDIO_OPTICAL
        if BayFeaturesMask.AUDIO_ANA_OUT in left:
            if BayFeaturesMask.AUDIO_ANA_IN in right:
                rv |= LinkFeature.AUDIO_ANALOG
        if BayFeaturesMask.AUDIO_ANA_IN in left:
            if BayFeaturesMask.AUDIO_ANA_OUT in right:
                rv |= LinkFeature.AUDIO_ANALOG
        if BayFeaturesMask.IR_OUT in left:
            if BayFeaturesMask.IR_IN in right:
                rv |= LinkFeature.IR
        if BayFeaturesMask.IR_IN in left:
            if BayFeaturesMask.IR_OUT in right:
                rv |= LinkFeature.IR
        if BayFeaturesMask.RC_OUT in left:
            if BayFeaturesMask.RC_IN in right:
                rv |= LinkFeature.RC
        if BayFeaturesMask.RC_IN in left:
            if BayFeaturesMask.RC_OUT in right:
                rv |= LinkFeature.RC
        return rv

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, BayLink):
            return False
        # A record names the far unit and its bay, so a link moved to another
        # bay of the same unit is a change, not a repeat.
        return (self.serial == value.serial) and (self.linked_bay_name == value.linked_bay_name) \
            and (self.bay == value.bay) and (self.features == value.features)

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
    def uid_to_user_string(self, remote_id:str|MxrDeviceUid|bytes|None) -> str:
        ''' return the serial of the unit if the uid is known, or the uid as string if it isn't '''

    @abstractmethod
    def get_bay_by_portnum(self, remote_id:str|MxrDeviceUid, portnum:int) -> BayBase|None:
        ''' get a bay of a device by its unique id and port number '''

    @abstractmethod
    def get_bay_by_portname(self, remote_id:str|MxrDeviceUid, portname:str) -> BayBase|None:
        ''' get a bay of a device by its unique id and port name '''

    @abstractmethod
    def get_by_stream_ip(self, ip:str, audio:bool=False) -> BayBase|None:
        ''' get a bay of a device by its OneIP stream address '''

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
    def on_mxr_update(self, data:object) -> None:
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

    def on_status_zone_powered_changed(self, bay:BayBase, val:bool) -> None:
        ''' called when the amplifier zone 'bay' drives is powered on or off '''
        if (type(self).on_status_poe_powered_changed is not MxrCallbacks.on_status_poe_powered_changed):
            warnings.warn("MxrCallbacks.on_status_poe_powered_changed is deprecated, "
                          "use on_status_zone_powered_changed", DeprecationWarning, stacklevel=2)
            self.on_status_poe_powered_changed(bay, val)
            return
        lval = "on" if val else "off"
        _LOGGER.debug(f"{bay} zone power {lval}")
        self.on_bay_update(bay)

    def on_status_poe_powered_changed(self, bay:BayBase, val:bool) -> None:
        ''' Deprecated: override on_status_zone_powered_changed. A subclass
        that still overrides this is called in its place. '''
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
        if volume is not None:
            volume_str = f" volume {volume.volume}%"
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

# The V2IP spelling of a name here, from before the rename to OneIP.
from .deprecated import alias_members as _alias_members, module_getattr as _module_getattr
# Installed through globals() so the generated stubs carry no __getattr__, which
# would make a type checker read every unknown name as Any instead of reporting
# it; to a type checker the old names do not exist.
globals()['__getattr__'] = _module_getattr(__name__, globals())
_alias_members(AudioEndpoint, 'is_v2ip')
_alias_members(AudioFeatures, 'is_v2ip_tx', 'is_v2ip_rx')
_alias_members(BayBase, 'is_v2ip_remote', 'is_v2ip_source', 'is_v2ip_sink', 'v2ip_source',
               'v2ip_uid', 'v2ip_device')
_alias_members(DeviceBase, 'is_v2ip', 'v2ip_features', 'v2ip_sources', 'v2ip_stats',
               'v2ip_details', 'v2ip_sink', 'v2ip_settings', 'v2ip_source_local',
               'is_v2ip_sink', 'v2ip_firmware_versions', 'v2ip_source', 'merge_v2ip_sources',
               'set_v2ip_auto_scaling', 'set_v2ip_output_mode', 'clear_v2ip_output_mode',
               'set_v2ip_setting', 'set_v2ip_ir_profile', 'set_v2ip_sink_ir_profile',
               'set_v2ip_auto_power_save', 'set_v2ip_power_save_schedule')
