##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .V2IPConfig import V2IPConfig
from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import V2IPStreamSource

class FrameV2IPStreamDetails(FrameBase):
    ''' All configured v2ip sources for the device that sent this frame '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)
        self.video = V2IPStreamSource("video", self.payload[0:6])
        self.audio = V2IPStreamSource("audio", self.payload[8:14])
        self.anc = V2IPStreamSource("anc", self.payload[16:22])
        self.arc = V2IPStreamSource("arc", self.payload[24:30])

    @property
    def sources(self) -> list[V2IPConfig]:
        # list of all sources defined in this frame
        rv = []
        srcnum = 0
        while srcnum < self.nb_sources:
            cfg = V2IPConfig(self, srcnum, self.payload[(srcnum*56):((srcnum+1)*56)])
            rv.append(cfg)
            srcnum += 1
        return rv

    def process(self) -> None:
        dev = self.remote_device
        first_in = dev.first_input
        if first_in is not None:
            first_in.v2ip.video = self.video
            first_in.v2ip.audio = self.audio
            first_in.v2ip.anc = self.anc
        first_out = dev.first_output
        if first_out is not None:
            first_out.v2ip.arc = self.arc
        #dev.on_v2ip_source_config_received()

    def __str__(self) -> str:
        return f"{str(self.remote_device)} v2ip stream details: {self.video} {self.audio} {self.anc} {self.arc}"
