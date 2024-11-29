##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader

class FrameVolumeUp(FrameBase):
    ''' volume up pressed frame '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    @property
    def bay(self):
        portnum = self.payload[0]
        dev = self.remote_device
        if dev is None:
            return
        return dev.get_by_portnum(portnum)

    def process(self):
        pass

    def __str__(self):
        return f"volume up bay: {self.bay} (port {self.payload[0]})"
