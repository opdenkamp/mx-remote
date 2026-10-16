######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for source routing change notifications.'''

from functools import cached_property
from typing import Any
from .FrameBase import FrameBase
from ..Interface import BayBase, SelectedBays

_ROUTE_NONE = 0xFFFE
'''The video port a OneIP reports for an output that shows nothing.'''

class FrameRoutingChange(FrameBase):
    '''Routing change information frame.'''
    @cached_property
    def sink_bay(self) -> BayBase|None:
        '''Sink (output) bay that received a new routing.'''
        return self.payload_bay(device=self.remote_device, idx=0, u16=True)

    @cached_property
    def selected_bay(self) -> BayBase|None:
        '''The (video) bay that was selected.'''
        return self.payload_bay(device=self.remote_device, idx=2, u16=True)

    @cached_property
    def video_bay(self) -> BayBase|None:
        '''The new video source bay.'''
        return self.payload_bay(device=self.remote_device, idx=4, u16=True)

    @cached_property
    def audio_bay(self) -> BayBase|None:
        '''The new audio source bay.'''
        return self.payload_bay(device=self.remote_device, idx=7, u16=True)

    @cached_property
    def scrambled(self) -> bool|None:
        '''Whether the signal is scrambled.'''
        return self.payload_bool(6)

    def process(self) -> None:
        '''Update the local device cache with the new routing.'''
        if ((sink_bay := self.sink_bay) is not None) and ((dev := self.remote_device) is not None):
            # A OneIP unit's input port names a source before its mapping has
            # created the bay.
            resolve = getattr(dev, 'routed_source', None)
            def routed(at:int) -> Any:
                port = self.payload_u16(at)
                if (port is None):
                    return None
                return resolve(port) if (resolve is not None) else dev.get_by_portnum(port)
            sink_bay.on_mxr_update(SelectedBays(routed(4), routed(7),
                                                clear_video=(self.payload_u16(4) == _ROUTE_NONE)))

    def __str__(self) -> str:
        return f"routing change {self.sink_bay} to {self.video_bay}"