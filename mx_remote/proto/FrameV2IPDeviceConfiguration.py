##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Uid import MxrDeviceUid
from .V2IPConfig import V2IPStreamSourcesData
import socket
import struct

class V2IPStreamSource:
    def __init__(self, label, data):
        self._label = label
        self._ip = int.from_bytes(data[0:4], "big")
        self._port = int(data[5]) << 8 | int(data[4])

    @property
    def label(self):
        return self._label

    @property
    def ip(self):
        return socket.inet_ntoa(struct.pack('!L', self._ip))

    @property
    def port(self):
        return self._port

    def __str__(self):
        return f"{self.label}={self.ip}:{self.port}"

class V2IPDeviceOptions:
    def __init__(self, data:bytes) -> None:
        self._tx_rate = int.from_bytes(data[0:1], "little")

    @property
    def tx_rate(self) -> int:
        return self._tx_rate

    def __str__(self) -> str:
        return f"tx rate: {self.tx_rate * 10}Mb/s"

class V2IPScalingSettings:
    def __init__(self, data):
        self.mode = data[0:2]
        self.refresh = (int(data[3]) << 8) | int(data[2])
        self.flags = data[4]

class FrameV2IPDeviceConfiguration(FrameBase):
    def __init__(self, header:FrameHeader):
        super().__init__(header)
        if len(self.payload) < 61:
            raise Exception(f"invalid device config len {len(self.payload)}")
        self.video = V2IPStreamSource("video", self.payload[16:22])
        self.audio = V2IPStreamSource("audio", self.payload[24:30])
        self.anc = V2IPStreamSource("anc", self.payload[32:38])
        self.options = V2IPDeviceOptions(self.payload[40:44])
        self.arc = V2IPStreamSource("arc", self.payload[48:54])
        self.scaling = V2IPScalingSettings(self.payload[56:61])

    @property
    def target_uid(self) -> str:
        return MxrDeviceUid(self.payload[0:16])

    @property
    def target_self(self) -> bool:
        return self.remote_id == self.target_uid

    def process(self) -> None:
        dev = self.remote_device
        if dev is None:
            return
        dev.v2ip_details = self.options
        if dev.v2ip_sources is None:
            dev.v2ip_sources = [V2IPStreamSourcesData(video=self.video, audio=self.audio, anc=self.anc)]
        else:
            dev.v2ip_sources[0].video = self.video
            dev.v2ip_sources[0].audio = self.audio
            dev.v2ip_sources[0].anc = self.anc

    def __str__(self) -> str:
        return f"V2IP device configuration self={self.target_self} {self.video} {self.audio} {self.anc} {self.arc} options={self.options}"