######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for V2IP stream detail information (video, audio, ancillary, ARC).'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import V2IPStreamSource, V2IPStreamSources
from .V2IPConfig import V2IPStreamSourceImpl, V2IPStreamSourcesImpl

class FrameV2IPStreamDetails(FrameBase):
    '''All configured V2IP stream sources for the device that sent this frame.'''
    @cached_property
    def video(self) -> V2IPStreamSource|None:
        '''Video stream source address.'''
        pl = self.payload_idx(start=0, end=6)
        if (pl is None):
            return None
        return V2IPStreamSourceImpl("video", pl)

    @cached_property
    def audio(self) -> V2IPStreamSource|None:
        '''Audio stream source address.'''
        pl = self.payload_idx(start=8, end=14)
        if (pl is None):
            return None
        return V2IPStreamSourceImpl("audio", pl)

    @cached_property
    def anc(self) -> V2IPStreamSource|None:
        '''Ancillary data stream source address.'''
        pl = self.payload_idx(start=16, end=22)
        if (pl is None):
            return None
        return V2IPStreamSourceImpl("anc", pl)

    @cached_property
    def arc(self) -> V2IPStreamSource|None:
        '''ARC (Audio Return Channel) stream source address.'''
        pl = self.payload_idx(start=24, end=30)
        if (pl is None):
            return None
        return V2IPStreamSourceImpl("arc", pl)

    @cached_property
    def sources(self) -> V2IPStreamSources|None:
        '''Combined stream sources, or None if required fields are missing.'''
        if ((video := self.video) is not None) and ((audio := self.audio) is not None) and ((anc := self.anc) is not None):
            return V2IPStreamSourcesImpl(video=video, audio=audio, anc=anc, arc=self.arc)

    def process(self) -> None:
        '''Update the local device cache with V2IP stream source details.'''
        if ((dev := self.remote_device) is not None):
            dev.on_mxr_update(self.sources)

    def __str__(self) -> str:
        return f"{str(self.remote_device)} v2ip stream details: {self.video} {self.audio} {self.anc} {self.arc}"
