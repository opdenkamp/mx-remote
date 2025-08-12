##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import BayBase, SelectedBays

class FrameRoutingChange(FrameBase):
    ''' Routing change information frame '''
    @cached_property
    def sink_bay(self) -> BayBase|None:
        return self.payload_bay(device=self.remote_device, idx=0)

    @cached_property
    def selected_bay(self) -> BayBase|None:
        # the (video) bay that was selected
        return self.payload_bay(device=self.remote_device, idx=1)

    @cached_property
    def video_bay(self) -> BayBase|None:
        # the new video source bay
        return self.payload_bay(device=self.remote_device, idx=2)

    @cached_property
    def audio_bay(self) -> BayBase|None:
        # the new audio source bay
        return self.payload_bay(device=self.remote_device, idx=4)

    @cached_property
    def scrambled(self) -> bool|None:
        # signal scrambled or not
        return self.payload_bool(3)

    def process(self):
        # update the local cache
        if ((sink_bay := self.sink_bay) is not None):
            sink_bay.on_mxr_update(SelectedBays(self.video_bay, self.audio_bay))

    def __str__(self) -> str:
        return f"routing change {self.sink_bay} to {self.video_bay}"