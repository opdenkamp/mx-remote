######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for secondary bay configuration data.'''

from functools import cached_property
from .BayConfig import BayConfig
from .FrameBase import FrameBase
import logging

_LOGGER = logging.getLogger(__name__)

class FrameBayConfigSecondary(FrameBase):
    '''Secondary bay configuration for the bays a remote device advertises.

    Paged the same way as FrameBayConfig: the record count varies per frame and
    the receiver merges records into its cache rather than replacing it.'''
    @cached_property
    def nb_bays(self) -> int:
        '''Number of bay descriptors in this page. Not the device's bay count.'''
        return int(len(self) / 61)

    @cached_property
    def bays(self) -> list[BayConfig]:
        '''Bay configurations carried by this page.'''
        rv:list[BayConfig] = []
        if self.payload is None:
            return rv
        # nb_bays comes from the header's declared length; a truncated datagram
        # can claim more records than actually arrived, so bound on both
        nb_bays = min(self.nb_bays, int(len(self.payload) / 61))
        for baynum in range(nb_bays):
            rv.append(BayConfig(self.payload[(baynum*61):((baynum+1)*61)]))
        return rv

    def process(self) -> None:
        '''Merge this page's bays into the local device cache.'''
        if ((dev := self.remote_device) is None):
            _LOGGER.debug("hello not received")
            return

        for bay in self.bays:
            dev.on_mxr_update(bay)

    def __str__(self) -> str:
        return f"{self.remote_device} secondary bay config page: {len(self.bays)} bays"
