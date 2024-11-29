##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Uid import MxrDeviceUid

class TopologyEntry:
    def __init__(self, uid:MxrDeviceUid, mask:int):
        self.uid = uid
        self.mask = mask

    def __str__(self):
        return f"{self.uid} mask {self.mask}"

class FrameTopology(FrameBase):
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    @property
    def topology(self):
        topo = []
        if self.header.payload_len < 20:
            return []
        data = self.payload
        while len(data) >= 20:
            topo.append(TopologyEntry(MxrDeviceUid(data[0:16]), struct.unpack('<L', data[16:20])[0]))
            data = data[20:]
        return topo

    def __str__(self) -> str:
        return f"{self.remote_device} topology data: {self.topology}"
