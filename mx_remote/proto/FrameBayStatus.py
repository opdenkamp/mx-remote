##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .Constants import BayStatusMask
from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import BayBase
import logging
import struct

_LOGGER = logging.getLogger(__name__)

class FrameBayStatus(FrameBase):
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    @property
    def bay(self)  -> BayBase:
        portnum = ((self.payload[1] << 8) | self.payload[0])
        dev = self.remote_device
        if dev is None:
            return None
        return dev.get_by_portnum(portnum)

    @property
    def signal_type(self) -> str:
        return self.payload[2:18].split(b'\0',1)[0].decode('ascii')

    @property
    def status(self) -> BayStatusMask:
        return BayStatusMask(struct.unpack('<L', self.payload[20:24])[0])

    @property
    def features(self) -> int:
        return struct.unpack('<L', self.payload[24:28])[0]

    def process(self) -> None:
        if self.bay is None:
            _LOGGER.warning("bay not registered yet")
        else:
            self.bay.features_mask = self.features
            self.bay.on_mxr_bay_status(self.status)
            if not self.status.signal_detected or not self.bay.device.is_v2ip:
                self.bay.signal_type = self.signal_type

    def __str__(self) -> str:
        return f"bay status {self.bay} signal '{self.signal_type}' status {self.status} features {self.features}"
