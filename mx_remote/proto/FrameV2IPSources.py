##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
from .V2IPConfig import V2IPConfig
from .FrameBase import FrameBase
from .V2IPConfig import V2IPStreamSourcesImpl
from ..Interface import V2IPStreamSourcesList

class FrameV2IPSources(FrameBase):
    ''' All configured v2ip sources for the device that sent this frame '''
    @property
    def nb_sources(self) -> int:
        # number of sources defined in this frame
        return int(len(self) / 40)

    @cached_property
    def sources(self) -> V2IPStreamSourcesList:
        # list of all sources defined in this frame
        rv = V2IPStreamSourcesList()
        srcnum = 0
        while srcnum < self.nb_sources:
            pl = self.payload_idx(start=(srcnum*40), end=((srcnum+1)*40))
            if (pl is None):
                break
            cfg = V2IPConfig(self, srcnum, pl)
            rv.append(V2IPStreamSourcesImpl(video=cfg.video, audio=cfg.audio, anc=cfg.anc))
            srcnum += 1
        return rv

    def process(self) -> None:
        if ((dev := self.remote_device) is not None):
            dev.on_mxr_update(self.sources)

    def __str__(self) -> str:
        if len(self.sources) > 0:
            return f"{str(self.remote_device)} {len(self.sources)} v2ip sources: {self.sources[0]}"
        return f"{str(self.remote_device)} 0 v2ip sources"
