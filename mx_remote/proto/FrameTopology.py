##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from ..Uid import MxrDeviceUid
import struct

class TopologyEntry:
    def __init__(self, uid:MxrDeviceUid, mask:int):
        self.uid = uid
        self.mask = mask

    def __str__(self) -> str:
        return f"{self.uid} mask {self.mask}"

    def __repr__(self) -> str:
        return str(self)

class FrameTopology(FrameBase):
    @property
    def topology(self) -> list[TopologyEntry]:
        topo = []
        data = self.payload
        if (data is None):
            return []
        while len(data) >= 20:
            topo.append(TopologyEntry(MxrDeviceUid(data[0:16]), struct.unpack('<L', data[16:20])[0]))
            data = data[20:]
        return topo

    def process(self) -> None:
        if ((dev := self.remote_device) is not None):
            dev.on_mxr_update(self)

    def __str__(self) -> str:
        return f"{self.remote_device} topology data: {self.topology}"
