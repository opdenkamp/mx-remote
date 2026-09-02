######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame containing all configured links for a device.'''

from functools import cached_property
from .LinkConfig import LinkConfig
from .FrameBase import FrameBase
import logging

class FrameLinks(FrameBase):
    '''Configured links for the device that sent this frame.

    Paged the same way as the bay config: a device with many bays splits its
    links across several frames sized against its own maximum payload, so the
    record count varies per frame and the receiver merges records into its
    cache rather than replacing it.'''
    @cached_property
    def nb_links(self) -> int:
        '''Number of link descriptors in this page. Not the device's link count.'''
        return int(len(self) / 38)

    @cached_property
    def links(self) -> list[LinkConfig]:
        '''Link configurations carried by this page.'''
        rv:list[LinkConfig] = []
        if (self.payload is None):
            return rv
        # nb_links comes from the header's declared length; a truncated datagram
        # can claim more records than actually arrived, so bound on both
        nb_links = min(self.nb_links, int(len(self.payload) / 38))
        for linknum in range(nb_links):
            rv.append(LinkConfig(self, self.payload[(linknum*38):((linknum+1)*38)]))
        return rv

    def process(self) -> None:
        '''Merge this page's links into the local device cache.'''
        dev = self.remote_device
        if dev is None:
            logging.debug("not processing link config - hello not received")
            return
        for link in self.links:
            link.process()
        dev.on_link_config_received()

    def __str__(self) -> str:
        return f"{self.remote_device} links config page: {len(self.links)} links"
