######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Video-over-IP stream source configuration and parsing.'''

from typing import Any
from ..compat import override
from ..Uid import MxrDeviceUid
from ..Interface import V2IPStreamSource, V2IPStreamSources, V2IPAudioFormat
import socket
import struct

# Re-exported for back-compat: V2IPAudioFormat lives in Interface so abstract types can reference it.
__all__ = ["V2IPAudioFormat", "V2IPStreamSourceImpl", "V2IPConfig", "V2IPStreamSourcesImpl", "parse_v2ip_av_source"]

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

    def __eq__(self, other:Any) -> bool:
        """Compare by address. The container compares element-wise, so without
        this a re-broadcast source list never matches the cached one."""
        if not isinstance(other, V2IPStreamSourceImpl):
            return NotImplemented
        return (self._ip == other._ip) and (self._port == other._port) \
            and (self._label == other._label)

    def __ne__(self, other:Any) -> bool:
        result = self.__eq__(other)
        return result if (result is NotImplemented) else (not result)

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

    def __init__(self, video:V2IPStreamSource, audio:V2IPStreamSource, anc:V2IPStreamSource, arc:V2IPStreamSource|None=None, uid:MxrDeviceUid|None=None) -> None:
        self._video = video
        self._audio = audio
        self._anc = anc
        self._arc = arc
        self._uid = uid

    @property
    @override
    def uid(self) -> MxrDeviceUid|None:
        return self._uid

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

    def __eq__(self, other:Any) -> bool:
        """Compare by the addresses carried, so an unchanged re-broadcast of a
        device's sources does not read as a change."""
        if not isinstance(other, V2IPStreamSourcesImpl):
            return NotImplemented
        return (self._video == other._video) and (self._audio == other._audio) \
            and (self._anc == other._anc) and (self._arc == other._arc) \
            and (self._uid == other._uid)

    def __ne__(self, other:Any) -> bool:
        result = self.__eq__(other)
        return result if (result is NotImplemented) else (not result)

    def __str__(self) -> str:
        return f"video:{self.video} audio:{self.audio} anc:{self.anc}"

    def __repr__(self) -> str:
        return str(self)

# A v2ip_stream_source is 8 bytes: a 4-byte ip and a 4-byte port, since port is
# uint_fast16_t. Only its low two bytes are ever used. So a v2ip_av_source of
# three of them is 24 bytes.
V2IP_AV_SOURCE_WIRE_SIZE = 24


def parse_v2ip_av_source(data:bytes, offset:int=0) -> V2IPStreamSourcesImpl:
    '''Parse a v2ip_av_source struct (24 bytes) into a V2IPStreamSourcesImpl with video/audio/anc.'''
    if len(data) < (offset + V2IP_AV_SOURCE_WIRE_SIZE):
        raise ValueError(f"invalid v2ip_av_source size: {len(data) - offset}")
    return V2IPStreamSourcesImpl(
        video=V2IPStreamSourceImpl("video", data[offset + 0:offset + 6]),
        audio=V2IPStreamSourceImpl("audio", data[offset + 8:offset + 14]),
        anc=V2IPStreamSourceImpl("anc", data[offset + 16:offset + 22]),
    )
