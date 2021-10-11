from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
import struct
from typing import Any

class FrameHello(FrameBase):
    ''' Hello frame, sent by devices to advertise themselves on the network '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

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
    def features(self) -> int:
        # supported features bitmask
        return struct.unpack('<L', self.payload[50:54])[0]

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
        return "hello name:{} serial:{} version:{}".format(self.device_name, self.serial, self.version)

