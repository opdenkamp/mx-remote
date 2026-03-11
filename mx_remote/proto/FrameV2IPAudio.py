##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2025 Op den Kamp IT Solutions  ##
##################################################

from enum import Enum
from functools import cached_property
import logging
from typing import override

from proto.FrameHeader import FrameHeader
from .FrameBase import FrameBase
from ..Interface import DeviceRegistry, MxrDeviceUid, V2IPStreamSource, AudioFeatures, AudioEndpoint, AudioEndpoints, AudioChangeSource, AudioLink, AudioLinks

_LOGGER = logging.getLogger(__name__)

class AudioCommandOpcode(Enum):
    UNKNOWN = 0xFFFF
    FEATURES = 0
    MUTE = 1
    TRIGGER = 2
    SELECT_INPUT = 3
    VOLUME = 4
    LINKS = 5

class AudioEntryType(Enum):
    PROCESSOR = 0
    ENDPOINT = 1
    ADDRESS = 2
    ROUTE_IN = 3
    PARENT = 5
    UNKNOWN = 0xFF

class EndpointStatus:
    STATUS_TRIGGER = (1 << 7)
    STATUS_MUTE = (1 << 8)

    def __init__(self, value:int) -> None:
        self._value = value

    @property
    def muted(self) -> bool:
        return ((self._value & self.STATUS_MUTE) != 0)

    @property
    def trigger_active(self) -> bool:
        return ((self._value & self.STATUS_TRIGGER) != 0)

    def __str__(self) -> str:
        rv = ""
        if self.muted:
            rv += "[muted]"
        if self.trigger_active:
            rv += "[trigger]"
        if (rv == ""):
            return "[none]"
        return rv

    def __repr__(self) -> str:
        return str(self)

class StreamAddress(V2IPStreamSource):
    def __init__(self, data:bytes|None) -> None:
        self.data = data
        if (self.data is None) or (len(self.data) < 6):
            raise Exception("invalid data")

    @property
    @override
    def label(self) -> str:
        return "audio"

    @property
    @override
    def ip(self) -> str:
        return f"{self.data[0]}.{self.data[1]}.{self.data[2]}.{self.data[3]}" # pyright: ignore[reportOptionalSubscript]

    @property
    @override
    def port(self) -> int:
        return self.data[5] << 8 | self.data[4] # pyright: ignore[reportOptionalSubscript]

    def __str__(self) -> str:
        return f"{self.ip}:{self.port}"

    def __repr__(self) -> str:
        return str(self)

class AudioEntry:
    def __init__(self, frame:FrameBase, idx:int) -> None:
        self._frame = frame
        self._idx = idx

    @cached_property
    def id(self) -> int|None:
        return self._frame.payload_u8(idx=self._idx)

    @cached_property
    def entry_type(self) -> AudioEntryType:
        val = self._frame.payload_u8(idx=(self._idx + 1))
        if (val is None) or (val > AudioEntryType.PARENT.value):
            return AudioEntryType.UNKNOWN
        return AudioEntryType(value=val)

    @cached_property
    def features(self) -> AudioFeatures|None:
        if (self.entry_type != AudioEntryType.ENDPOINT):
            return None
        val = self._frame.payload_u32(idx=(self._idx + 8))
        if (val is None):
            return None
        return AudioFeatures(value=val)

    @cached_property
    def status(self) -> EndpointStatus|None:
        if (self.entry_type != AudioEntryType.ENDPOINT):
            return None
        val = self._frame.payload_u32(idx=(self._idx + 12))
        if (val is None):
            return None
        return EndpointStatus(value=val)

    @cached_property
    def supported_routes(self) -> int|None:
        if (self.entry_type != AudioEntryType.ROUTE_IN):
            return None
        return self._frame.payload_u32(idx=(self._idx + 8))

    @cached_property
    def active_routes(self) -> int|None:
        if (self.entry_type != AudioEntryType.ROUTE_IN):
            return None
        return self._frame.payload_u32(idx=(self._idx + 12))

    @cached_property
    def parent_id(self) -> int|None:
        if (self.entry_type != AudioEntryType.PARENT):
            return None
        return self._frame.payload_u8(idx=(self._idx + 8))

    @cached_property
    def stream_address(self) -> StreamAddress|None:
        if (self.entry_type != AudioEntryType.ADDRESS):
            return None
        b = self._frame.payload_bytes(idx=(self._idx + 8))
        if b is None:
            return None
        b = b[0:24]
        return StreamAddress(data=self._frame.payload_bytes(idx=(self._idx + 8)))

    def __str__(self) -> str:
        return f"{self.id}={self.entry_type}"

    def __repr__(self) -> str:
        return str(self)

class AudioEndpointImpl(AudioEndpoint):
    def __init__(self, container:AudioEndpoints, id:int, features:AudioFeatures) -> None:
        AudioEndpoint.__init__(self, container=container)
        self._id = id
        self._features = features
        self._address:V2IPStreamSource|None = None
        self._parent_id:int|None = None
        self._in_routes_supported:int|None = None
        self._in_routes:int|None = None

    @property
    def id(self) -> int:
        return self._id

    @property
    def features(self) -> AudioFeatures:
        return self._features

    @property
    def is_v2ip(self) -> bool:
        return self.features.is_v2ip_rx or self.features.is_v2ip_tx

    @property
    def is_hdmi(self) -> bool:
        return self.features.is_hdmi

    @property
    def is_spdif(self) -> bool:
        return self.features.is_spdif

    @property
    def is_rca(self) -> bool:
        return self.features.is_rca

    @property
    def is_input(self) -> bool:
        return self.features.is_input

    @property
    def is_output(self) -> bool:
        return self.features.is_output

    @property
    def address(self) -> V2IPStreamSource|None:
        return self._address

    @address.setter
    def address(self, address:V2IPStreamSource) -> None:
        self._address = address

    @property
    def parent_id(self) -> int|None:
        return self._parent_id

    @parent_id.setter
    def parent_id(self, parent:int) -> None:
        self._parent_id = parent

    @property
    def inputs_available(self) -> list['AudioEndpoint']:
        rv:list[AudioEndpoint] = []
        if (self.in_routes_supported is not None):
            for id in range(32):
                if (self.in_routes_supported & (1 << id)) != 0:
                    ep = self.container.get(id=id)
                    if (ep is not None):
                        rv.append(ep)
        return rv

    @property
    def input(self) -> 'AudioEndpoint|None':
        if (self.in_routes is None):
            return None
        for id in range(32):
            if (self.in_routes & (1 << id)) != 0:
                return self.container.get(id=id)
        return None

    @property
    def in_routes(self) -> int|None:
        return self._in_routes

    @in_routes.setter
    def in_routes(self, routes:int) -> None:
        self._in_routes = routes

    @property
    def in_routes_supported(self) -> int|None:
        return self._in_routes_supported

    @in_routes_supported.setter
    def in_routes_supported(self, routes:int) -> None:
        self._in_routes_supported = routes

    def __eq__(self, value: object) -> bool:
        if (not isinstance(value, AudioEndpoint) and not isinstance(value, AudioEndpointImpl)):
            return False
        return (self.id == value.id) and (self.features == value.features) and (self.parent_id == value.parent_id)

    def __str__(self) -> str:
        serial = ''
        if (self.bay is not None):
            serial = f'{self.bay.device.serial}-'
        if self.is_v2ip:
            address = self.address
            if (address is None):
                address = '<unknown>'
            else:
                address = str(address)
            return f"{serial}{str(self.id)}@{address}"
        return f"{serial}{str(self.id)}"

    def __repr__(self) -> str:
        return str(self)

class AudioLinkImpl(AudioLink):
    def __init__(self, frame:FrameBase, idx:int) -> None:
        self._frame = frame
        self._idx = idx

    @cached_property
    def endpoint(self) -> int:
        val = self._frame.payload_u8(idx=self._idx)
        if (val is None):
            return -1
        return val

    @cached_property
    def link_endpoint(self) -> int:
        val = self._frame.payload_u8(idx=self._idx + 1)
        if (val is None):
            return -1
        return val

    @cached_property
    def link_device(self) -> MxrDeviceUid|None:
        return self._frame.payload_uuid(idx=self._idx + 4)

    @cached_property
    def valid(self) -> bool:
        ld = self.link_device
        if (ld is None):
            return False
        return not ld.empty

    def __str__(self) -> str:
        return f'link ep:{self.endpoint}->{self.link_device}:{self.link_endpoint}'

    def __repr__(self) -> str:
        return str(self)

class AudioLinksImpl(AudioLinks):
    def __init__(self, data:FrameBase, idx:int=0) -> None:
        self.data = data
        self._idx = idx

    @cached_property
    def nb_links(self) -> int:
        val = self.data.payload_u16(idx=self._idx)
        if (val is None):
            return 0
        return val

    @cached_property
    def entries(self) -> list[AudioLink]:
        rv = []
        for x in range(self.nb_links):
            link = AudioLinkImpl(frame=self.data, idx=(4 + self._idx + (x * 24)))
            if link.valid:
                rv.append(link)
        return rv

    def __str__(self) -> str:
        return str([str(link) for link in self.entries])

    def __repr__(self) -> str:
        return str(self)

class AudioConfig:
    def __init__(self, data:FrameBase) -> None:
        self.data = data

    @cached_property
    def features(self) -> int|None:
        return self.data.payload_u32(idx=20)

    @cached_property
    def status(self) -> int|None:
        return self.data.payload_u32(idx=24)

    @cached_property
    def nb_endpoints(self) -> int:
        val = self.data.payload_u16(idx=28)
        if (val is None):
            return 0
        return val

    @cached_property
    def entries(self) -> list[AudioEntry]:
        rv = []
        for x in range(self.nb_endpoints):
            rv.append(AudioEntry(frame=self.data, idx=(36 + (x * 16))))
        return rv

    @cached_property
    def control_address(self) -> StreamAddress|None:
        for entry in self.entries:
            if (entry.entry_type == AudioEntryType.ADDRESS) and (entry.id == 0xFF):
                return entry.stream_address
        return None

    @cached_property
    def endpoints(self) -> AudioEndpoints:
        rv = AudioEndpoints()
        eps:dict[int,AudioEndpointImpl] = {}

        for entry in self.entries:
            id = entry.id
            if (id is None):
                continue
            if (entry.entry_type == AudioEntryType.ENDPOINT):
                features = entry.features
                if (features is not None):
                    ep = AudioEndpointImpl(id=id, features=features, container=rv)
                    rv.add(ep)
                    eps[ep.id] = ep

        for entry in self.entries:
            id = entry.id
            if (id is None) or (not id in eps):
                continue
            if (entry.entry_type == AudioEntryType.ADDRESS):
                address = entry.stream_address
                if (address is not None):
                    eps[id].address = address
            elif (entry.entry_type == AudioEntryType.PARENT):
                parent = entry.parent_id
                if (parent is not None):
                    eps[id].parent_id = parent
                    parent_ep = rv.get(id=parent)
                    if (parent_ep is not None):
                        parent_ep.add_child(eps[id])
                        eps[id].set_parent(parent_ep)
            elif (entry.entry_type == AudioEntryType.ROUTE_IN):
                routes_supported = entry.supported_routes
                routes = entry.active_routes
                if (routes_supported is not None) and (routes is not None):
                    eps[id].in_routes_supported = routes_supported
                    eps[id].in_routes = routes

        return rv

    def __str__(self) -> str:
        return f"endpoint config: {self.endpoints}"

class AudioChangeSourceImpl(AudioChangeSource):
    def __init__(self, data:FrameBase) -> None:
        self.data = data

    @property
    def source_uid(self) -> MxrDeviceUid|None:
        return self.data.payload_uuid(idx=20)

    @property
    def target_uid(self) -> MxrDeviceUid|None:
        return self.data.payload_uuid(idx=36)

    @property
    def source_id(self) -> int|None:
        return self.data.payload_u16(idx=52)

    @property
    def target_id(self) -> int|None:
        return self.data.payload_u16(idx=54)

    def __str__(self) -> str:
        return f"source change {self.source_uid}:{self.source_id} -> {self.target_uid}:{self.target_id}"

    def __repr__(self) -> str:
        return str(self)

class AudioMute:
    def __init__(self, data:FrameBase) -> None:
        self.data = data

    @cached_property
    def endpoint(self) -> int|None:
        return self.data.payload_u16(idx=20)

    @cached_property
    def mute(self) -> bool|None:
        return self.data.payload_bool(idx=24)

    def __str__(self) -> str:
        return f"mute endpoint {self.endpoint}: {self.mute}"

class AudioTrigger:
    def __init__(self, data:FrameBase) -> None:
        self.data = data

    @cached_property
    def endpoint(self) -> int|None:
        return self.data.payload_u16(idx=20)

    @cached_property
    def trigger(self) -> bool|None:
        return self.data.payload_bool(idx=24)

    def __str__(self) -> str:
        return f"trigger endpoint {self.endpoint}: {self.trigger}"

class AudioVolume:
    def __init__(self, data:FrameBase) -> None:
        self.data = data

    @cached_property
    def endpoint(self) -> int|None:
        return self.data.payload_u16(idx=20)

    @cached_property
    def volume(self) -> int|None:
        return self.data.payload_u32(idx=24)

    def __str__(self) -> str:
        return f"volume endpoint {self.endpoint}: {self.volume}"

class FrameV2IPAudio(FrameBase):
    @cached_property
    def _frame(self) -> 'FrameV2IPAudio':
        if (self.opcode == AudioCommandOpcode.FEATURES):
            return FrameV2IPAudioConfig(header=self.header)
        elif (self.opcode == AudioCommandOpcode.MUTE):
            return FrameV2IPAudioMute(header=self.header)
        elif (self.opcode == AudioCommandOpcode.TRIGGER):
            return FrameV2IPAudioTrigger(header=self.header)
        elif (self.opcode == AudioCommandOpcode.SELECT_INPUT):
            return FrameV2IPAudioChangeSource(header=self.header)
        elif (self.opcode == AudioCommandOpcode.LINKS):
            return FrameV2IPAudioLinks(header=self.header)
        elif (self.opcode == AudioCommandOpcode.VOLUME):
            return FrameV2IPAudioVolume(header=self.header)
        raise Exception(f"unhandled audio opcode {self.opcode}")

    def process(self) -> None:
        if (self.remote_device is None):
            return
        try:
            self._frame.process()
        except Exception as e:
            _LOGGER.warning(e)

    @staticmethod
    def construct_select_input(mxr:DeviceRegistry, sink:MxrDeviceUid, sink_ep:AudioEndpoint, source:MxrDeviceUid, source_ep:AudioEndpoint) -> FrameBase|None:
        return FrameV2IPAudioChangeSource.construct(mxr=mxr, sink=sink, sink_ep=sink_ep, source=source, source_ep=source_ep)

    @cached_property
    def opcode(self) -> AudioCommandOpcode:
        val = self.payload_u16(idx=0)
        if (val is None) or (val > AudioCommandOpcode.LINKS.value):
            return AudioCommandOpcode.UNKNOWN
        return AudioCommandOpcode(value=val)

    @cached_property
    def uid(self) -> MxrDeviceUid|None:
        return self.payload_uuid(idx=2)

    def __str__(self) -> str:
        try:
            return str(self._frame)
        except Exception as e:
            return str(e)
class FrameV2IPAudioConfig(FrameV2IPAudio):
    def __init__(self, header: FrameHeader):
        super().__init__(header)
        if (self.opcode != AudioCommandOpcode.FEATURES):
            raise Exception(f"invalid opcode {self.opcode}")

    @cached_property
    def audio_config(self) -> AudioConfig:
        return AudioConfig(data=self)

    @cached_property
    def has_audio_links(self) -> bool:
        return (len(self) > 36 + (self.audio_config.nb_endpoints * 16))

    @cached_property
    def audio_links(self) -> AudioLinks|None:
        if self.has_audio_links:
            return AudioLinksImpl(data=self, idx=(36 + (self.audio_config.nb_endpoints * 16)))
        return None

    @override
    def process(self) -> None:
        if (self.remote_device is None):
            return
        self.remote_device.on_mxr_update(data=self.audio_config.endpoints)
        if self.has_audio_links:
            self.remote_device.on_mxr_update(data=self.audio_links)

    def __str__(self) -> str:
        links = self.audio_links
        links_str = f" links: {links}" if links is not None else ''
        return f"{str(self.remote_device)} audio config: {self.audio_config}{links_str}"

class FrameV2IPAudioChangeSource(FrameV2IPAudio):
    def __init__(self, header: FrameHeader):
        super().__init__(header)
        if (self.opcode != AudioCommandOpcode.SELECT_INPUT):
            raise Exception(f"invalid opcode {self.opcode}")

    @cached_property
    def select_input(self) -> AudioChangeSource:
        if (self.opcode == AudioCommandOpcode.SELECT_INPUT):
            return AudioChangeSourceImpl(data=self)
        raise Exception(f"{self.opcode} is not an AudioChangeSource frame")

    @override
    def process(self) -> None:
        if (self.remote_device is None):
            return
        self.remote_device.on_mxr_update(data=self.select_input)

    @staticmethod
    def construct(mxr:DeviceRegistry, sink:MxrDeviceUid, sink_ep:AudioEndpoint, source:MxrDeviceUid, source_ep:AudioEndpoint) -> FrameBase|None:
        payload = bytes([AudioCommandOpcode.SELECT_INPUT.value >> 8, AudioCommandOpcode.SELECT_INPUT.value & 0xF, 0, 0]) \
            + sink.byte_value \
            + source.byte_value \
            + sink.byte_value \
            + bytes([source_ep.id >> 8, source_ep.id & 0xF]) \
            + bytes([sink_ep.id >> 8, sink_ep.id & 0xF])
        return FrameBase.construct_base(mxr=mxr, opcode=0x43, payload=payload)

    def __str__(self) -> str:
        return f"{str(self.remote_device)} audio route: {self.select_input}"

class FrameV2IPAudioLinks(FrameV2IPAudio):
    def __init__(self, header: FrameHeader):
        super().__init__(header)
        if (self.opcode != AudioCommandOpcode.LINKS):
            raise Exception(f"invalid opcode {self.opcode}")

    @cached_property
    def audio_links(self) -> AudioLinks:
        return AudioLinksImpl(data=self)

    @override
    def process(self) -> None:
        if (self.remote_device is None):
            return
        self.remote_device.on_mxr_update(data=self.audio_links)

    def __str__(self) -> str:
        return f"{str(self.remote_device)} audio links: {self.audio_links}"

class FrameV2IPAudioMute(FrameV2IPAudio):
    def __init__(self, header: FrameHeader):
        super().__init__(header)
        if (self.opcode != AudioCommandOpcode.MUTE):
            raise Exception(f"invalid opcode {self.opcode}")

    @cached_property
    def param(self) -> AudioMute:
        return AudioMute(data=self)

    def __str__(self) -> str:
        return f"{str(self.remote_device)} {self.param}"

class FrameV2IPAudioTrigger(FrameV2IPAudio):
    def __init__(self, header: FrameHeader):
        super().__init__(header)
        if (self.opcode != AudioCommandOpcode.TRIGGER):
            raise Exception(f"invalid opcode {self.opcode}")

    @cached_property
    def param(self) -> AudioTrigger:
        return AudioTrigger(data=self)

    def __str__(self) -> str:
        return f"{str(self.remote_device)} {self.param}"

class FrameV2IPAudioVolume(FrameV2IPAudio):
    def __init__(self, header: FrameHeader):
        super().__init__(header)
        if (self.opcode != AudioCommandOpcode.VOLUME):
            raise Exception(f"invalid opcode {self.opcode}")

    @cached_property
    def param(self) -> AudioVolume:
        return AudioVolume(data=self)

    def __str__(self) -> str:
        return f"{str(self.remote_device)} {self.param}"
