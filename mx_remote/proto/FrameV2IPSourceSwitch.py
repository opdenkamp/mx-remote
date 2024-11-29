##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import DeviceBase, BayBase, DeviceRegistry
from ..Uid import MxrDeviceUid
import socket
import struct
import logging

_LOGGER = logging.getLogger(__name__)

class FrameV2IPSourceSwitch(FrameBase):
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    def construct(mxr:DeviceRegistry, target:BayBase, video:BayBase|str|None=None, audio:BayBase|str|None=None) -> FrameBase:
        if video is not None:
            if isinstance(audio, BayBase):
                if not video.is_v2ip_source:
                    raise Exception(f"{video} is not a v2ip source")
            if video.v2ip_source is None:
                raise Exception(f"{video} v2ip addresses not known")

        if audio is not None:
            if isinstance(audio, BayBase):
                if not audio.is_v2ip_source:
                    raise Exception(f"{audio} is not a v2ip source")
                if audio.v2ip_source is None:
                    raise Exception(f"{audio} v2ip addresses not known")

        payload = target.device.remote_id.byte_value
        if video is not None:
            ip = socket.inet_aton(video.v2ip_source.video.ip if isinstance(video, BayBase) else video)
            payload += bytes([int(ip[0]), int(ip[1]), int(ip[2]), int(ip[3])])
        else:
            payload += bytes([0, 0, 0, 0])
        if audio is not None:
            ip = socket.inet_aton(audio.v2ip_source.audio.ip if isinstance(audio, BayBase) else audio)
            payload += bytes([int(ip[0]), int(ip[1]), int(ip[2]), int(ip[3])])
        else:
            payload += bytes([0, 0, 0, 0])
        return FrameBase.construct_frame(mxr=mxr, opcode=0x1F, payload=payload)

    @property
    def target_device(self) -> DeviceBase:
        return self.mxr.get_by_uid(self.target_uid)

    @property
    def target_uid(self) -> MxrDeviceUid:
        return MxrDeviceUid(self.payload[0:16])

    @property
    def video(self) -> str:
        ip = int.from_bytes(self.payload[16:20], "big")
        return socket.inet_ntoa(struct.pack('!L', ip))

    @property
    def video_bay(self) -> BayBase:
        return self.mxr.get_by_stream_ip(ip=self.video, audio=False)

    @property
    def audio(self) -> str:
        ip = int.from_bytes(self.payload[20:24], "big")
        return socket.inet_ntoa(struct.pack('!L', ip))

    @property
    def audio_bay(self) -> BayBase:
        return self.mxr.get_by_stream_ip(ip=self.audio, audio=True)

    def process(self):
        # update the local cache
        sink_bay = self.target_device.first_output
        if sink_bay is not None:
            sink_bay.video_source = self.video_bay
            sink_bay.audio_source = self.audio_bay

    def __str__(self) -> str:
        return f"V2IP source switch: {self.target_device} -> {self.video}={self.video_bay}/{self.audio}={self.audio_bay}"