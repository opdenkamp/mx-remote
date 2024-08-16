from .V2IPConfig import V2IPConfig
from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from typing import List
import logging

class FrameV2IPSources(FrameBase):
    ''' All configured v2ip sources for the device that sent this frame '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    @property
    def nb_sources(self) -> int:
        # number of sources defined in this frame
        return len(self) / 56

    @property
    def sources(self) -> List[V2IPConfig]:
        # list of all sources defined in this frame
        rv = []
        srcnum = 0
        while srcnum < self.nb_sources:
            cfg = V2IPConfig(self, srcnum, self.payload[(srcnum*56):((srcnum+1)*56)])
            rv.append(cfg)
            srcnum += 1
        return rv

    def process(self) -> None:
        # update the cached link status
        dev = self.remote_device
        return
        if dev is None:
            logging.debug("not processing v2ip config - hello not received")
            return
        for src in self.sources:
            src.process()
        #dev.on_v2ip_source_config_received()

    def __str__(self) -> str:
        return f"{str(self.remote_device)} v2ip sources"
