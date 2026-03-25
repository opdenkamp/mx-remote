##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import BayBase, ConnectStatus

class FrameConnectStatus(FrameBase):
    ''' Device was connected or disconnected. For sources, this means that an input signal was detected '''
    @cached_property
    def bay(self) -> BayBase|None:
        return self.payload_bay(device=self.remote_device, idx=0)

    @cached_property
    def connected(self) -> ConnectStatus:
        # new connected / signal detect status
        pl = self.payload_bool(1)
        if (pl is not None):
            return ConnectStatus.CONNECTED if pl else ConnectStatus.DISCONNECTED
        return ConnectStatus.UNKNOWN

    def process(self) -> None:
        # update the cached connected status for this bay
        bay = self.bay
        if (bay is not None):
            bay.on_mxr_update(self.connected)

    def __str__(self) -> str:
        return f"connect status {self.bay}: {self.connected}"
