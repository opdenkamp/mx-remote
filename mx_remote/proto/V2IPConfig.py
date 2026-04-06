##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Video-over-IP stream source configuration and parsing.'''

from typing import override
from ..Uid import MxrDeviceUid
from ..Interface import V2IPStreamSource, V2IPStreamSources
import socket
import struct

class V2IPStreamSourceImpl(V2IPStreamSource):
    '''Concrete implementation of a V2IP stream source with IP and port.'''

    def __init__(self, label:str, data:bytes) -> None:
        self._label = label
        self._ip = int.from_bytes(data[0:4], "big")
        self._port = int(data[5]) << 8 | int(data[4])

    @property
    @override
    def label(self) -> str:
        return self._label

    @property
    @override
    def ip(self) -> str:
        return socket.inet_ntoa(struct.pack('!L', self._ip))

    @property
    @override
    def port(self) -> int:
        return self._port

    def __str__(self) -> str:
        return f"{self.label}={self.ip}:{self.port}"

class V2IPConfig:
    '''V2IP source configuration for a single port with video, audio, and ancillary streams.'''
    def __init__(self, frame:'FrameBase', port:int, payload:bytes) -> None:
        if len(payload) < 40:
            raise Exception(f"invalid size: {len(payload)}")
        self.frame = frame
        self.port = port
        self.payload = payload
        self.video = V2IPStreamSourceImpl("video", self.payload[16:22])
        self.audio = V2IPStreamSourceImpl("audio", self.payload[24:30])
        self.anc = V2IPStreamSourceImpl("anc", self.payload[32:38])

    def process(self) -> None:
        '''Register or update this link in the local cache.'''
        pass

    @property
    def uid(self) -> MxrDeviceUid:
        '''Device UID of the V2IP source.'''
        return MxrDeviceUid(self.payload[0:16])

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return f"V2IP port {self.port} source uid {self.uid} - {self.video} {self.audio} {self.anc}"

class V2IPStreamSourcesImpl(V2IPStreamSources):
    '''Concrete collection of V2IP stream sources (video, audio, ancillary, ARC).'''

    def __init__(self, video:V2IPStreamSource, audio:V2IPStreamSource, anc:V2IPStreamSource, arc:V2IPStreamSource|None=None) -> None:
        self._video = video
        self._audio = audio
        self._anc = anc
        self._arc = arc

    @property
    @override
    def video(self) -> V2IPStreamSource:
        return self._video

    @video.setter
    def video(self, stream:V2IPStreamSource) -> None:
        self._video = stream

    @property
    @override
    def audio(self) -> V2IPStreamSource:
        return self._audio

    @audio.setter
    def audio(self, stream:V2IPStreamSource) -> None:
        self._audio = stream

    @property
    @override
    def anc(self) -> V2IPStreamSource:
        return self._anc

    @anc.setter
    def anc(self, stream:V2IPStreamSource) -> None:
        self._anc = stream

    @property
    @override
    def arc(self) -> V2IPStreamSource|None:
        return self._arc

    @arc.setter
    def arc(self, stream:V2IPStreamSource|None) -> None:
        self._arc = stream

    def __str__(self) -> str:
        return f"video:{self.video} audio:{self.audio} anc:{self.anc}"

    def __repr__(self) -> str:
        return str(self)
