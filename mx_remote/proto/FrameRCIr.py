##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import BayBase
import struct
import logging

_LOGGER = logging.getLogger(__name__)

class FrameRCIr(FrameBase):
    ''' IR key press '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    @property
    def bay(self) -> BayBase:
        # bay that received the key press
        dev = self.remote_device
        if dev is None:
            return None
        portnum = ((int(self.payload[1]) << 8) | int(self.payload[0]))
        return dev.get_by_portnum(portnum)

    @property
    def timestamp(self) -> int:
        return struct.unpack('<L', self.payload[2:6])[0]

    def process(self) -> None:
        bay = self.bay
        _LOGGER.debug(f"IR key bay {self.bay} timestamp {self.timestamp}")

    def __str__(self) -> str:
        return f"IR key press"
