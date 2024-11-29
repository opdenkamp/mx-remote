##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from ..const import __version__
from .Constants import MXR_PROTOCOL_VERSION, MXR_DEVICE_FEATURE_MANAGER
from .FrameBase import FrameBase, append_payload_str
from .FrameHeader import FrameHeader
from ..Interface import DeviceRegistry, DeviceFeatures
import struct
from typing import Any

class FrameHello(FrameBase):
    ''' Hello frame, sent by devices to advertise themselves on the network '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    def construct(mxr:DeviceRegistry) -> FrameBase:
        payload = [ (MXR_PROTOCOL_VERSION & 0xFF), ((MXR_PROTOCOL_VERSION >> 8) & 0xFF) ]
        payload = append_payload_str(payload=payload, value=mxr.name, sz=16)
        payload = append_payload_str(payload=payload, value="P9SN00000000", sz=16)
        payload = append_payload_str(payload=payload, value=__version__, sz=16)
        features = MXR_DEVICE_FEATURE_MANAGER
        payload += [ (features >> 0) & 0xFF, (features >> 8) & 0xFF, (features >> 16) & 0xFF, (features >> 24) & 0xFF ]
        return FrameBase.construct_frame(mxr=mxr, opcode=0, payload=payload)

    @property
    def supported_protocol(self) -> int:
        # supported protocol version, which may be higher than this frame's protocol version
        return (int(self.payload[1]) << 8) | int(self.payload[0])

    @property
    def device_name(self) -> str:
        # device name
        return self.payload[2:18].split(b'\0',1)[0].decode('ascii')

    @property
    def serial(self) -> str:
        # device serial
        return self.payload[18:34].split(b'\0',1)[0].decode('ascii')

    @property
    def version(self) -> str:
        # firmware version
        return self.payload[34:50].split(b'\0',1)[0].decode('ascii')

    @property
    def features(self) -> DeviceFeatures:
        # supported features bitmask
        return DeviceFeatures(struct.unpack('<L', self.payload[50:54])[0])

    def process(self) -> None:
        # register or update this device in the local cache
        self.mxr.on_mxr_hello(self)

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, FrameHello) and \
                (self.protocol == other.protocol) and \
                (self.device_name == other.device_name) and \
                (self.serial == other.serial) and \
                (self.version == other.version) and \
                (self.features == other.features)

    def __ne__(self, other: Any) -> bool:
        return not isinstance(other, FrameHello) or \
                (self.protocol != other.protocol) or \
                (self.device_name != other.device_name) or \
                (self.serial != other.serial) or \
                (self.version != other.version) or \
                (self.features != other.features)

    def __str__(self) -> str:
        return f"hello name:{self.device_name} serial:{self.serial} version:{self.version} features/status: {self.features} uid: {self.header.remote_id}"

