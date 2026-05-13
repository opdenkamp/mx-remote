##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Protocol frame for V2IP manual source switching by raw stream addresses (opcode 0x24).'''

from functools import cached_property
from .FrameBase import FrameBase
from .V2IPConfig import V2IPStreamSourceImpl, V2IPStreamSourcesImpl
from ..Interface import BayBase, DeviceBase, DeviceRegistry, DeviceV2IPSink, SelectedBays, V2IPAudioFormat
from ..Uid import MxrDeviceUid
import socket

_OPCODE = 0x24
_BASE_SIZE = 40
_WITH_OPTIONS_SIZE = 48

class FrameV2IPManualSourceSwitch(FrameBase):
    '''Manual V2IP source switch: target sink + raw video/audio/anc multicast addresses.

    Payload layout (little-endian, ALIGN(8) per field):
        0..16   sink uid
        16..24  video stream source (ip 4 + port 2 + pad 2)
        24..32  audio stream source
        32..40  anc stream source
        40..48  optional v2ip_audio_format (sample_rate u32 + channels u8 + reserved[3])
    '''

    @staticmethod
    def construct(mxr:DeviceRegistry, target:DeviceBase|MxrDeviceUid|bytes,
                  video_ip:str, video_port:int,
                  audio_ip:str, audio_port:int,
                  anc_ip:str, anc_port:int,
                  audio_fmt:V2IPAudioFormat|None=None) -> FrameBase|None:
        '''Build a manual switch frame for transmission.'''
        if isinstance(target, DeviceBase):
            uid_bytes = target.remote_id.byte_value
        elif isinstance(target, MxrDeviceUid):
            uid_bytes = target.byte_value
        else:
            uid_bytes = bytes(target)
        if len(uid_bytes) != 16:
            raise ValueError(f"invalid uid length: {len(uid_bytes)}")

        payload = bytearray(uid_bytes)
        for ip, port in ((video_ip, video_port), (audio_ip, audio_port), (anc_ip, anc_port)):
            payload += socket.inet_aton(ip)
            payload += bytes([port & 0xFF, (port >> 8) & 0xFF, 0, 0])
        if audio_fmt is not None:
            payload += audio_fmt.value
        return FrameBase.construct_base(mxr=mxr, opcode=_OPCODE, payload=bytes(payload))

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        return self.payload_uuid(0)

    @cached_property
    def target_device(self) -> DeviceBase|None:
        return self.mxr.get_by_uid(self.target_uid)

    def _stream(self, label:str, offset:int) -> V2IPStreamSourceImpl:
        if (self.payload is None) or (len(self.payload) < (offset + 6)):
            raise Exception("invalid FrameV2IPManualSourceSwitch size")
        return V2IPStreamSourceImpl(label, self.payload[offset:offset + 6])

    @cached_property
    def video(self) -> V2IPStreamSourceImpl:
        return self._stream("video", 16)

    @cached_property
    def audio(self) -> V2IPStreamSourceImpl:
        return self._stream("audio", 24)

    @cached_property
    def anc(self) -> V2IPStreamSourceImpl:
        return self._stream("anc", 32)

    @cached_property
    def audio_fmt(self) -> V2IPAudioFormat|None:
        '''Optional audio format override; None when the peer omitted the extension.'''
        if (self.payload is None) or (len(self.payload) < _WITH_OPTIONS_SIZE):
            return None
        return V2IPAudioFormat.from_bytes(self.payload[_BASE_SIZE:_WITH_OPTIONS_SIZE])

    @cached_property
    def video_bay(self) -> BayBase|None:
        return self.mxr.get_by_stream_ip(ip=self.video.ip, audio=False)

    @cached_property
    def audio_bay(self) -> BayBase|None:
        return self.mxr.get_by_stream_ip(ip=self.audio.ip, audio=True)

    @cached_property
    def sink(self) -> DeviceV2IPSink:
        '''Effective sink-side state announced by this manual switch (mirrors what /v2ip/sink reports).'''
        return DeviceV2IPSink(
            addresses=V2IPStreamSourcesImpl(video=self.video, audio=self.audio, anc=self.anc),
            audio_fmt=self.audio_fmt,
        )

    def process(self) -> None:
        '''Update the local cache with the new manual route.'''
        if (self.target_device is None):
            return
        sink_bay = self.target_device.first_output
        if (sink_bay is not None):
            sink_bay.on_mxr_update(SelectedBays(self.video_bay, self.audio_bay))
        # Refresh the target device's cached sink subscriptions so /port/details consumers
        # see the new route before the next periodic v2ip_device_config broadcast.
        self.target_device.on_mxr_update(self.sink)

    def __str__(self) -> str:
        fmt = f" fmt={self.audio_fmt}" if (self.audio_fmt is not None) else ""
        return f"V2IP manual source switch: {self.target_device} -> {self.video}/{self.audio}/{self.anc}{fmt}"
