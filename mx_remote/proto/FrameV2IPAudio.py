##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2025 Op den Kamp IT Solutions  ##
##################################################

from enum import Enum
from functools import cached_property
from typing import override
from .FrameBase import FrameBase
from ..Interface import DeviceRegistry, MxrDeviceUid, V2IPStreamSource, AudioEndpointType, AudioEndpointMask, AudioFeatures, AudioEndpoint, AudioEndpoints, AudioChangeSource

class AudioCommandOpcode(Enum):
    UNKNOWN = 0xFFFF
    FEATURES = 0
    MUTE = 1
    TRIGGER = 2
    SELECT_INPUT = 3
    SELECT_OUTPUT = 4
    DESELECT_OUTPUT = 5

class AudioEntryType(Enum):
    PROCESSOR = 0
    ENDPOINT = 1
    ADDRESS = 2
    ROUTE_IN = 3
    ROUTE_OUT = 4
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
    def id_numeric(self) -> int|None:
        return self._frame.payload_u8(idx=self._idx)

    @cached_property
    def id(self) -> AudioEndpointType|None:
        pl = self.id_numeric
        if (pl is None) or (pl > AudioEndpointType.OUTPUT_RCA.value):
            return None
        return AudioEndpointType(pl)

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
    def supported_routes(self) -> AudioEndpointMask|None:
        if (self.entry_type != AudioEntryType.ROUTE_IN) and (self.entry_type != AudioEntryType.ROUTE_OUT):
            return None
        val = self._frame.payload_u32(idx=(self._idx + 8))
        if (val is None):
            return None
        return AudioEndpointMask(value=val)

    @cached_property
    def active_routes(self) -> AudioEndpointMask|None:
        if (self.entry_type != AudioEntryType.ROUTE_IN) and (self.entry_type != AudioEntryType.ROUTE_OUT):
            return None
        val = self._frame.payload_u32(idx=(self._idx + 12))
        if (val is None):
            return None
        return AudioEndpointMask(value=val)

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
    def __init__(self, container:AudioEndpoints, id:AudioEndpointType, features:AudioFeatures) -> None:
        AudioEndpoint.__init__(self, container=container)
        self._id = id
        self._features = features
        self._address:V2IPStreamSource|None = None
        self._parent_id:int|None = None
        self._in_routes_supported:AudioEndpointMask|None = None
        self._in_routes:AudioEndpointMask|None = None
        self._out_routes_supported:AudioEndpointMask|None = None
        self._out_routes:AudioEndpointMask|None = None

    @property
    def id(self) -> AudioEndpointType:
        return self._id

    @property
    def features(self) -> AudioFeatures:
        return self._features

    @property
    def is_v2ip(self) -> bool:
        return (self.id == AudioEndpointType.OUTPUT_V2IP) or (self.id == AudioEndpointType.INPUT_V2IP)

    @property
    def is_hdmi(self) -> bool:
        return (self.id == AudioEndpointType.OUTPUT_HDMI) or (self.id == AudioEndpointType.INPUT_HDMI)

    @property
    def is_spdif(self) -> bool:
        return (self.id == AudioEndpointType.OUTPUT_SPDIF) or (self.id == AudioEndpointType.INPUT_SPDIF)

    @property
    def is_rca(self) -> bool:
        return (self.id == AudioEndpointType.OUTPUT_RCA) or (self.id == AudioEndpointType.INPUT_RCA)

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
            if self.in_routes_supported.input_hdmi:
                ep = self.container.get(type=AudioEndpointType.INPUT_HDMI)
                if (ep is not None):
                    rv.append(ep)
            if self.in_routes_supported.input_rca:
                ep = self.container.get(type=AudioEndpointType.INPUT_RCA)
                if (ep is not None):
                    rv.append(ep)
            if self.in_routes_supported.input_spdif:
                ep = self.container.get(type=AudioEndpointType.INPUT_SPDIF)
                if (ep is not None):
                    rv.append(ep)
            if self.in_routes_supported.input_v2ip:
                ep = self.container.get(type=AudioEndpointType.INPUT_V2IP)
                if (ep is not None):
                    rv.append(ep)
        return rv

    @property
    def input(self) -> 'AudioEndpoint|None':
        if (self.in_routes is None):
            return None
        if self.in_routes.input_hdmi:
            return self.container.get(type=AudioEndpointType.INPUT_HDMI)
        if self.in_routes.input_rca:
            return self.container.get(type=AudioEndpointType.INPUT_HDMI)
        if self.in_routes.input_spdif:
            return self.container.get(type=AudioEndpointType.INPUT_HDMI)
        if self.in_routes.input_v2ip:
            return self.container.get(type=AudioEndpointType.INPUT_V2IP)
        return None

    @property
    def outputs_available(self) -> list['AudioEndpoint']:
        rv:list[AudioEndpoint] = []
        if (self.out_routes_supported is not None):
            if self.out_routes_supported.output_hdmi:
                ep = self.container.get(type=AudioEndpointType.OUTPUT_HDMI)
                if (ep is not None):
                    rv.append(ep)
            if self.out_routes_supported.output_rca:
                ep = self.container.get(type=AudioEndpointType.OUTPUT_RCA)
                if (ep is not None):
                    rv.append(ep)
            if self.out_routes_supported.output_spdif:
                ep = self.container.get(type=AudioEndpointType.OUTPUT_SPDIF)
                if (ep is not None):
                    rv.append(ep)
            if self.out_routes_supported.output_v2ip:
                ep = self.container.get(type=AudioEndpointType.OUTPUT_V2IP)
                if (ep is not None):
                    rv.append(ep)
        return rv

    @property
    def outputs(self) -> list['AudioEndpoint']:
        rv:list[AudioEndpoint] = []
        if (self.out_routes is not None):
            if self.out_routes.output_hdmi:
                ep = self.container.get(type=AudioEndpointType.OUTPUT_HDMI)
                if (ep is not None):
                    rv.append(ep)
            if self.out_routes.output_rca:
                ep = self.container.get(type=AudioEndpointType.OUTPUT_RCA)
                if (ep is not None):
                    rv.append(ep)
            if self.out_routes.output_spdif:
                ep = self.container.get(type=AudioEndpointType.OUTPUT_SPDIF)
                if (ep is not None):
                    rv.append(ep)
            if self.out_routes.output_v2ip:
                ep = self.container.get(type=AudioEndpointType.OUTPUT_V2IP)
                if (ep is not None):
                    rv.append(ep)
        return rv

    @property
    def in_routes(self) -> AudioEndpointMask|None:
        return self._in_routes

    @in_routes.setter
    def in_routes(self, routes:AudioEndpointMask) -> None:
        self._in_routes = routes

    @property
    def in_routes_supported(self) -> AudioEndpointMask|None:
        return self._in_routes_supported

    @in_routes_supported.setter
    def in_routes_supported(self, routes:AudioEndpointMask) -> None:
        self._in_routes_supported = routes

    @property
    def out_routes(self) -> AudioEndpointMask|None:
        return self._out_routes

    @out_routes.setter
    def out_routes(self, routes:AudioEndpointMask) -> None:
        self._out_routes = routes

    @property
    def out_routes_supported(self) -> AudioEndpointMask|None:
        return self._out_routes_supported

    @out_routes_supported.setter
    def out_routes_supported(self, routes:AudioEndpointMask) -> None:
        self._out_routes_supported = routes

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
            rv.append(AudioEntry(frame=self.data, idx=(36 + (x * 24))))
        return rv

    @cached_property
    def endpoints(self) -> AudioEndpoints:
        rv = AudioEndpoints()
        eps:dict[AudioEndpointType,AudioEndpointImpl] = {}

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
            if (id is None):
                continue
            if (entry.entry_type == AudioEntryType.ADDRESS):
                address = entry.stream_address
                if (address is not None):
                    eps[id].address = address
            elif (entry.entry_type == AudioEntryType.PARENT):
                parent = entry.parent_id
                if (parent is not None):
                    eps[id].parent_id = parent
                    parent_ep = rv.get(type=AudioEndpointType(parent))
                    if (parent_ep is not None):
                        parent_ep.add_child(eps[id])
                        eps[id].set_parent(parent_ep)
            elif (entry.entry_type == AudioEntryType.ROUTE_IN):
                routes_supported = entry.supported_routes
                routes = entry.active_routes
                if (routes_supported is not None) and (routes is not None):
                    eps[id].in_routes_supported = routes_supported
                    eps[id].in_routes = routes
            elif (entry.entry_type == AudioEntryType.ROUTE_OUT):
                routes_supported = entry.supported_routes
                routes = entry.active_routes
                if (routes_supported is not None) and (routes is not None):
                    eps[id].out_routes_supported = routes_supported
                    eps[id].out_routes = routes

        # TODO fix v2ipaud out_routes
        for endpoint in rv.as_tree:
            routes = 0
            for child in endpoint.children:
                if child in endpoint.outputs_available:
                    if child.input == endpoint:
                        routes |= (1 << child.id.value)
            endpoint.out_routes = AudioEndpointMask(value=routes) # pyright: ignore[reportAttributeAccessIssue]

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

class FrameV2IPAudio(FrameBase):
    def process(self) -> None:
        if (self.remote_device is None):
            return

        if (self.opcode == AudioCommandOpcode.FEATURES):
            cfg = AudioConfig(data=self)
            self.remote_device.on_mxr_update(data=cfg.endpoints)
        elif (self.opcode == AudioCommandOpcode.SELECT_INPUT):
            cmd = AudioChangeSourceImpl(data=self)
            self.remote_device.on_mxr_update(data=cmd)
        else:
            print(f"unknown audio opcode {self.opcode}")

    @staticmethod
    def construct_select_input(mxr:DeviceRegistry, sink:MxrDeviceUid, sink_ep:AudioEndpoint, source:MxrDeviceUid, source_ep:AudioEndpoint) -> FrameBase|None:
        payload = bytes([AudioCommandOpcode.SELECT_INPUT.value >> 8, AudioCommandOpcode.SELECT_INPUT.value & 0xF, 0, 0]) \
            + sink.byte_value \
            + source.byte_value \
            + sink.byte_value \
            + bytes([source_ep.id.value >> 8, source_ep.id.value & 0xF]) \
            + bytes([sink_ep.id.value >> 8, sink_ep.id.value & 0xF])
        return FrameBase.construct_base(mxr=mxr, opcode=0x43, payload=payload)

    @cached_property
    def opcode(self) -> AudioCommandOpcode:
        val = self.payload_u16(idx=0)
        if (val is None) or (val > AudioCommandOpcode.DESELECT_OUTPUT.value):
            return AudioCommandOpcode.UNKNOWN
        return AudioCommandOpcode(value=val)

    @cached_property
    def uid(self) -> MxrDeviceUid|None:
        return self.payload_uuid(idx=2)

    def __str__(self) -> str:
        return f"{str(self.remote_device)} audio command"
