##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import BayBase

class FrameSignalStatus(FrameBase):
    ''' signal status changed '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    @property
    def bay(self)  -> BayBase:
        portnum = self.payload[0]
        dev = self.remote_device
        if dev is None:
            return None
        return dev.get_by_portnum(portnum)

    @property
    def signal(self) -> bool:
        # signal detected
        return (self.payload[1] == 1)

    @property
    def signal_type(self) -> str:
        # signal type description
        if len(self) <= 2:
            return None
        return self.payload[2:].split(b'\0',1)[0].decode('ascii')

    def process(self) -> None:
        # update the local cache
        bay = self.bay
        if bay is None:
            return
        bay.signal_detected = self.signal
        bay.signal_type = self.signal_type

    def __str__(self) -> str:
        return f"signal status {str(self.bay)} - detected={self.signal} type={self.signal_type}"
