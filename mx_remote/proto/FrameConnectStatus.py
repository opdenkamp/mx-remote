##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import BayBase

class FrameConnectStatus(FrameBase):
    ''' Device was connected or disconnected. For sources, this means that an input signal was detected '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    @property
    def bay(self) -> BayBase:
        # bay that changed
        portnum = self.payload[0]
        dev = self.remote_device
        if dev is None:
            return None
        return dev.get_by_portnum(portnum)

    @property
    def connected(self) -> bool:
        # new connected / signal detect status
        return (self.payload[1] == 1)

    def process(self) -> None:
        # update the cached connected status for this bay
        bay = self.bay
        if bay is not None:
            bay.connected = self.connected

    def __str__(self) -> str:
        return "connect status {}: {}".format(str(self.bay), str(self.connected))
