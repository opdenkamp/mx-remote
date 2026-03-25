##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
from .BayConfig import BayConfig
from .FrameBase import FrameBase
import logging

_LOGGER = logging.getLogger(__name__)

class FrameBayConfigSecondary(FrameBase):
    ''' Bay configuration and information for all bays that are available on a remote device '''
    @cached_property
    def nb_bays(self) -> int:
        # total number of bay descriptors in this frame
        return int(len(self) / 61)

    @cached_property
    def bays(self) -> list[BayConfig]:
        # get a list of bay configurations defined in this frame
        rv:list[BayConfig] = []
        if self.payload is None:
            return rv
        baynum = 0
        while baynum < self.nb_bays:
            bay = BayConfig(self.payload[(baynum*61):((baynum+1)*61)])
            rv.append(bay)
            baynum += 1
        return rv

    def process(self) -> None:
        # register or update bay in the local cache
        if ((dev := self.remote_device) is None):
            _LOGGER.debug("hello not received")
            return

        for bay in self.bays:
            dev.on_mxr_update(bay)

    def __str__(self) -> str:
        return f"{self.remote_device} secondary bay config: {len(self.bays)} bays"
