##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
from .LinkConfig import LinkConfig
from .FrameBase import FrameBase
import logging

class FrameLinks(FrameBase):
    ''' All configured links for the device that sent this frame '''
    @cached_property
    def nb_links(self) -> int:
        # number of links defined in this frame
        return int(len(self) / 38)

    @cached_property
    def links(self) -> list[LinkConfig]:
        # list of all links defined in this frame
        rv = []
        linknum = 0
        if (self.payload is None):
            return []
        while linknum < self.nb_links:
            if (len(self.payload) >= ((linknum+1)*38)):
                link = LinkConfig(self, self.payload[(linknum*38):((linknum+1)*38)])
                rv.append(link)
                linknum += 1
        return rv

    def process(self) -> None:
        # update the cached link status
        dev = self.remote_device
        if dev is None:
            logging.debug("not processing link config - hello not received")
            return
        for link in self.links:
            link.process()
        dev.on_link_config_received()

    def __str__(self) -> str:
        return f"{self.remote_device} links config"
