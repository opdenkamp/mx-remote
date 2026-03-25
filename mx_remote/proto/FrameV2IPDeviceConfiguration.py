##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Uid import MxrDeviceUid
from ..Interface import DeviceV2IPDetails, DeviceV2IPScalingSettings, V2IPStreamSource
from .V2IPConfig import V2IPStreamSourceImpl

class V2IPDeviceOptions:
    def __init__(self, data:bytes) -> None:
        self._tx_rate = int.from_bytes(data[0:1], "little")

    @property
    def tx_rate(self) -> int:
        return self._tx_rate

    def __str__(self) -> str:
        return f"tx rate: {self.tx_rate * 10}Mb/s"

class V2IPScalingSettingsImpl(DeviceV2IPScalingSettings):
    def __init__(self, data):
        self._mode = data[0:2]
        self._refresh = (int(data[3]) << 8) | int(data[2])
        self._flags = data[4]

    @property
    def mode(self) -> int:
        return self._mode

    @property
    def refresh(self) -> int:
        return self._refresh

    @property
    def flags(self) -> int:
        return self._flags

class FrameV2IPDeviceConfiguration(FrameBase):
    def __init__(self, header:FrameHeader, timestamp:float):
        super().__init__(header=header, timestamp=timestamp)
        if (self.payload is None) or (len(self.payload) < 61):
            raise Exception("invalid v2ip configuration")
        self.video = V2IPStreamSourceImpl("video", self.payload[16:22])
        self.audio = V2IPStreamSourceImpl("audio", self.payload[24:30])
        self.anc = V2IPStreamSourceImpl("anc", self.payload[32:38])
        self.options = V2IPDeviceOptions(self.payload[40:44])
        self.arc = V2IPStreamSourceImpl("arc", self.payload[48:54])
        self.scaling = V2IPScalingSettingsImpl(self.payload[56:61])

    @property
    def target_uid(self) -> MxrDeviceUid|None:
        return self.payload_uuid(idx=0)

    @property
    def target_self(self) -> bool:
        return (self.remote_id == self.target_uid)

    @cached_property
    def details(self) -> DeviceV2IPDetails:
        return DeviceV2IPDetails(video=self.video, audio=self.audio, anc=self.anc, arc=self.arc, tx_rate=self.options.tx_rate, scaling=self.scaling)

    def process(self) -> None:
        if ((dev := self.remote_device) is None):
            return
        dev.on_mxr_update(self.details)

    def __str__(self) -> str:
        return f"V2IP device configuration self={self.target_self} {self.video} {self.audio} {self.anc} {self.arc} options={self.options}"