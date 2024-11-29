##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from ..Uid import MxrDeviceUid
from ..Interface import V2IPStreamSource, V2IPStreamSources

class V2IPConfig:
    ''' Single source configuration '''
    def __init__(self, frame, port:int, payload:bytes):
        if len(payload) < 40:
            raise Exception(f"invalid size: {len(payload)}")
        self.frame = frame
        self.port = port
        self.payload = payload
        self.video = V2IPStreamSource("video", self.payload[16:22])
        self.audio = V2IPStreamSource("audio", self.payload[24:30])
        self.anc = V2IPStreamSource("anc", self.payload[32:38])

    def process(self) -> None:
        # register or update this link in the local cache
        pass

    @property
    def uid(self) -> MxrDeviceUid:
        return MxrDeviceUid(self.payload[0:16])

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return f"V2IP port {self.port} source uid {self.uid} - {self.video} {self.audio} {self.anc}"

class V2IPStreamSourcesData(V2IPStreamSources):
    def __init__(self, video:V2IPStreamSource, audio:V2IPStreamSource, anc:V2IPStreamSource) -> None:
        self._video = video
        self._audio = audio
        self._anc = anc

    @property
    def video(self) -> V2IPStreamSource:
        return self._video

    @video.setter
    def video(self, stream:V2IPStreamSource) -> None:
        self._video = stream

    @property
    def audio(self) -> V2IPStreamSource:
        return self._audio

    @audio.setter
    def audio(self, stream:V2IPStreamSource) -> None:
        self._audio = stream

    @property
    def anc(self) -> V2IPStreamSource:
        return self._anc

    @anc.setter
    def anc(self, stream:V2IPStreamSource) -> None:
        self._anc = stream

    def __str__(self) -> str:
        return f"video:{self.video} audio:{self.audio} anc:{self.anc}"

    def __repr__(self) -> str:
        return str(self)