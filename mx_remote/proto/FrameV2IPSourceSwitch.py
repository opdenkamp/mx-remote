##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import DeviceBase, BayBase, DeviceRegistry, SelectedBays
from ..Uid import MxrDeviceUid
import socket
import struct
import logging

_LOGGER = logging.getLogger(__name__)

class FrameV2IPSourceSwitch(FrameBase):
    @staticmethod
    def construct(mxr:DeviceRegistry, target:BayBase, video:BayBase|str|None=None, audio:BayBase|str|None=None) -> FrameBase|None:
        if video is not None:
            if isinstance(video, BayBase):
                if not video.features.v2ip_source_local and not video.features.v2ip_source_remote:
                    raise Exception(f"{video} is not a v2ip source")
                if video.v2ip_source is None:
                    raise Exception(f"{video} v2ip addresses not known")

        if audio is not None:
            if isinstance(audio, BayBase):
                if not audio.features.v2ip_source_local and not audio.features.v2ip_source_remote:
                    raise Exception(f"{audio} is not a v2ip source")
                if audio.v2ip_source is None:
                    raise Exception(f"{audio} v2ip addresses not known")

        payload = target.device.remote_id.byte_value
        if video is not None:
            ip = socket.inet_aton(video.v2ip_source.video.ip if isinstance(video, BayBase) else video) # pyright: ignore[reportOptionalMemberAccess]
            payload += bytes([int(ip[0]), int(ip[1]), int(ip[2]), int(ip[3])])
        else:
            payload += bytes([0, 0, 0, 0])
        if audio is not None:
            ip = socket.inet_aton(audio.v2ip_source.audio.ip if isinstance(audio, BayBase) else audio) # pyright: ignore[reportOptionalMemberAccess]
            payload += bytes([int(ip[0]), int(ip[1]), int(ip[2]), int(ip[3])])
        else:
            payload += bytes([0, 0, 0, 0])
        return FrameBase.construct_base(mxr=mxr, opcode=0x1F, payload=payload)

    @cached_property
    def target_device(self) -> DeviceBase|None:
        return self.mxr.get_by_uid(self.target_uid)

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        return self.payload_uuid(0)

    @cached_property
    def video(self) -> str:
        if (self.payload is None) or (len(self.payload) < 24):
            raise Exception("invalid FrameV2IPSourceSwitch size")
        ip = int.from_bytes(self.payload[16:20], "big")
        return socket.inet_ntoa(struct.pack('!L', ip))

    @cached_property
    def video_bay(self) -> BayBase|None:
        return self.mxr.get_by_stream_ip(ip=self.video, audio=False)

    @cached_property
    def audio(self) -> str:
        if (self.payload is None) or (len(self.payload) < 24):
            raise Exception("invalid FrameV2IPSourceSwitch size")
        ip = int.from_bytes(self.payload[20:24], "big")
        return socket.inet_ntoa(struct.pack('!L', ip))

    @cached_property
    def audio_bay(self) -> BayBase|None:
        return self.mxr.get_by_stream_ip(ip=self.audio, audio=True)

    def process(self):
        # update the local cache
        if (self.target_device is not None):
            sink_bay = self.target_device.first_output
            if (sink_bay is not None):
                sink_bay.on_mxr_update(SelectedBays(self.video_bay, self.audio_bay))

    def __str__(self) -> str:
        return f"V2IP source switch: {self.target_device} -> {self.video}={self.video_bay}/{self.audio}={self.audio_bay}"
