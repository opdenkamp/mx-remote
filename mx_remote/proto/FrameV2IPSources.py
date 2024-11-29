##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .V2IPConfig import V2IPConfig
from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from .V2IPConfig import V2IPStreamSourcesData

class FrameV2IPSources(FrameBase):
    ''' All configured v2ip sources for the device that sent this frame '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    @property
    def nb_sources(self) -> int:
        # number of sources defined in this frame
        return len(self) / 40

    @property
    def sources(self) -> list[V2IPStreamSourcesData]:
        # list of all sources defined in this frame
        rv = []
        srcnum = 0
        while srcnum < self.nb_sources:
            cfg = V2IPConfig(self, srcnum, self.payload[(srcnum*40):((srcnum+1)*40)])
            rv.append(V2IPStreamSourcesData(video=cfg.video, audio=cfg.audio, anc=cfg.anc))
            srcnum += 1
        return rv

    def process(self) -> None:
        dev = self.remote_device
        if dev is None:
            return
        self.remote_device.v2ip_sources = self.sources

    def __str__(self) -> str:
        if len(self.sources) > 0:
            return f"{str(self.remote_device)} {len(self.sources)} v2ip sources: {self.sources[0]}"
        return f"{str(self.remote_device)} 0 v2ip sources"
