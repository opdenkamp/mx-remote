from .LinkConfig import LinkConfig
from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from typing import List
import logging

class FrameLinks(FrameBase):
    ''' All configured links for the device that sent this frame '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    @property
    def nb_links(self) -> int:
        # number of links defined in this frame
        return len(self) / 38

    @property
    def links(self) -> List[LinkConfig]:
        # list of all links defined in this frame
        rv = []
        linknum = 0
        while linknum < self.nb_links:
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
        return "{} links config".format(str(self.remote_dev))
