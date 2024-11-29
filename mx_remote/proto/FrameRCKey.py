##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from .Constants import RCKey
from ..Interface import BayBase
class FrameRCKey(FrameBase):
    ''' remote control key press or action '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    @property
    def bay(self) -> BayBase:
        # bay that received the key press
        dev = self.remote_device
        if dev is None:
            return None
        portnum = ((int(self.payload[1]) << 8) | int(self.payload[0])) if (dev.protocol >= 6) else self.payload[0]
        return dev.get_by_portnum(portnum)

    @property
    def key(self) -> RCKey:
        # key that was received
        dev = self.remote_device
        if dev is None:
            return None
        return RCKey((int(self.payload[3]) << 8) | int(self.payload[2])) if (dev.protocol >= 6) else RCKey((int(self.payload[2]) << 8) | int(self.payload[1]))

    def process(self) -> None:
        bay = self.bay
        if bay is not None:
            bay.on_key_pressed(self.key)

    def __str__(self) -> str:
        return "{} key pressed: {}".format(str(self.bay), repr(self.key))
