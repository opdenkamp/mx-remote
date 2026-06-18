######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for source routing change notifications.'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import BayBase, SelectedBays

class FrameRoutingChange(FrameBase):
    '''Routing change information frame.'''
    @cached_property
    def sink_bay(self) -> BayBase|None:
        '''Sink (output) bay that received a new routing.'''
        return self.payload_bay(device=self.remote_device, idx=0)

    @cached_property
    def selected_bay(self) -> BayBase|None:
        '''The (video) bay that was selected.'''
        return self.payload_bay(device=self.remote_device, idx=1)

    @cached_property
    def video_bay(self) -> BayBase|None:
        '''The new video source bay.'''
        return self.payload_bay(device=self.remote_device, idx=2)

    @cached_property
    def audio_bay(self) -> BayBase|None:
        '''The new audio source bay.'''
        return self.payload_bay(device=self.remote_device, idx=4)

    @cached_property
    def scrambled(self) -> bool|None:
        '''Whether the signal is scrambled.'''
        return self.payload_bool(3)

    def process(self) -> None:
        '''Update the local device cache with the new routing.'''
        if ((sink_bay := self.sink_bay) is not None):
            sink_bay.on_mxr_update(SelectedBays(self.video_bay, self.audio_bay))

    def __str__(self) -> str:
        return f"routing change {self.sink_bay} to {self.video_bay}"