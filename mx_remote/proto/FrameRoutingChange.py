##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import BayBase

class FrameRoutingChange(FrameBase):
    ''' Routing change information frame '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    @property
    def sink_bay(self) -> BayBase:
        # the sink bay that changed routing
        portnum = self.payload[0]
        dev = self.remote_device
        if dev is None:
            return
        return dev.get_by_portnum(portnum)

    @property
    def selected_bay(self) -> BayBase:
        # the (video) bay that was selected
        portnum = self.payload[1]
        dev = self.remote_device
        if dev is None:
            return
        return dev.get_by_portnum(portnum)

    @property
    def video_bay(self) -> BayBase:
        # the new video source bay
        portnum = self.payload[2]
        dev = self.remote_device
        if dev is None:
            return
        return dev.get_by_portnum(portnum)

    @property
    def audio_bay(self) -> BayBase:
        # the new audio source bay
        portnum = self.payload[4]
        dev = self.remote_device
        if dev is None:
            return
        return dev.get_by_portnum(portnum)

    @property
    def scrambled(self):
        # signal scrambled or not
        return (self.payload[3] == 1)

    def process(self):
        # update the local cache
        sink_bay = self.sink_bay
        if sink_bay is not None:
            sink_bay.video_source = self.video_bay
            sink_bay.audio_source = self.audio_bay

    def __str__(self) -> str:
        return f"routing change {self.sink_bay} to {self.video_bay}"