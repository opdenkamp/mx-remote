##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .BayConfig import BayConfig
from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
import logging

_LOGGER = logging.getLogger(__name__)

class FrameBayConfig(FrameBase):
    ''' Bay configuration and information for all bays that are available on a remote device '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    @property
    def nb_bays(self) -> int:
        # total number of bay descriptors in this frame
        return len(self) / 61

    @property
    def bays(self) -> list[BayConfig]:
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
            _LOGGER.debug("not processing bay config - hello not received")
            return
        for bayconfig in self.bays:
            _LOGGER.debug(f"process {bayconfig}")
            dev.on_mxr_bay_config(bayconfig)

    def __str__(self) -> str:
        return f"{self.remote_device} bay config: {len(self.bays)} bays"
