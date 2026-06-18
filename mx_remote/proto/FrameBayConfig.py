######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for bay configuration data.'''

from functools import cached_property
from .BayConfig import BayConfig
from .FrameBase import FrameBase
import logging

_LOGGER = logging.getLogger(__name__)

class FrameBayConfig(FrameBase):
    '''Bay configuration and information for all bays available on a remote device.'''
    @cached_property
    def nb_bays(self) -> int:
        '''Total number of bay descriptors in this frame.'''
        return int(len(self) / 61)

    @cached_property
    def bays(self) -> list[BayConfig]:
        '''List of bay configurations defined in this frame.'''
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
        '''Register or update all bays in the local device cache.'''
        if ((dev := self.remote_device) is None):
            _LOGGER.debug("hello not received")
            return

        for bayconfig in self.bays:
            _LOGGER.debug(f"process {bayconfig}")
            dev.on_mxr_update(bayconfig)

    def __str__(self) -> str:
        return f"{self.remote_device} bay config: {len(self.bays)} bays"
