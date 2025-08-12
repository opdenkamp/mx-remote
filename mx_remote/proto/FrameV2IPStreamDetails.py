##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import V2IPStreamSource, V2IPStreamSources
from .V2IPConfig import V2IPStreamSourceImpl, V2IPStreamSourcesImpl

class FrameV2IPStreamDetails(FrameBase):
    ''' All configured v2ip sources for the device that sent this frame '''
    @cached_property
    def video(self) -> V2IPStreamSource|None:
        pl = self.payload_idx(start=0, end=6)
        if (pl is None):
            return None
        return V2IPStreamSourceImpl("video", pl)

    @cached_property
    def audio(self) -> V2IPStreamSource|None:
        pl = self.payload_idx(start=8, end=14)
        if (pl is None):
            return None
        return V2IPStreamSourceImpl("audio", pl)

    @cached_property
    def anc(self) -> V2IPStreamSource|None:
        pl = self.payload_idx(start=16, end=22)
        if (pl is None):
            return None
        return V2IPStreamSourceImpl("anc", pl)

    @cached_property
    def arc(self) -> V2IPStreamSource|None:
        pl = self.payload_idx(start=24, end=30)
        if (pl is None):
            return None
        return V2IPStreamSourceImpl("arc", pl)

    @cached_property
    def sources(self) -> V2IPStreamSources|None:
        if ((video := self.video) is not None) and ((audio := self.audio) is not None) and ((anc := self.anc) is not None):
            return V2IPStreamSourcesImpl(video=video, audio=audio, anc=anc, arc=self.arc)

    def process(self) -> None:
        if ((dev := self.remote_device) is not None):
            dev.on_mxr_update(self.sources)

    def __str__(self) -> str:
        return f"{str(self.remote_device)} v2ip stream details: {self.video} {self.audio} {self.anc} {self.arc}"
