from .BayConfig import BayConfig
from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from typing import List
import logging

class FrameBayConfig(FrameBase):
    ''' Bay configuration and information for all bays that are available on a remote device '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    @property
    def nb_bays(self) -> int:
        # total number of bay descriptors in this frame
        return len(self) / 61

    @property
    def bays(self) -> List[BayConfig]:
        # get a list of bay configurations defined in this frame
        rv = []
        baynum = 0
        while baynum < self.nb_bays:
            bay = BayConfig(self.payload[(baynum*61):((baynum+1)*61)])
            rv.append(bay)
            baynum += 1
        return rv

    def process(self) -> None:
        # register or update all bays in the local cache
        dev = self.remote_device
        if dev is None:
            logging.debug("not processing bay config - hello not received")
            return
        for bayconfig in self.bays:
            dev.on_mxr_bay_config(bayconfig)

    def __str__(self) -> str:
        return f"{self.remote_device} bay config: {len(self.bays)} bays"
