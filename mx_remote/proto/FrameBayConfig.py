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
    '''Bay configuration for the bays a remote device advertises.

    A device pages its bays across several of these frames: firmware sizes each
    page against mxr_max_payload_len() and shrinks it further on OOM, so the
    record count varies from frame to frame and no single frame holds the whole
    list. Each page is a valid stand-alone frame with the same per-record
    format - the receiver merges records into its cache and must never treat
    one frame as the complete set.'''
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

        for bayconfig in self.bays:
            _LOGGER.debug(f"process {bayconfig}")
            dev.on_mxr_update(bayconfig)

    def __str__(self) -> str:
        return f"{self.remote_device} bay config page: {len(self.bays)} bays"
