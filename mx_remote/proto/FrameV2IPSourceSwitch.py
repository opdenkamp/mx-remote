##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Protocol frame for V2IP source switching between encoder and decoder.'''

from functools import cached_property
from .FrameBase import FrameBase
from .Constants import BayFeaturesMask
from ..Interface import DeviceBase, BayBase, DeviceRegistry, SelectedBays
from ..Uid import MxrDeviceUid
import socket
import struct
import logging

_LOGGER = logging.getLogger(__name__)

class FrameV2IPSourceSwitch(FrameBase):
    '''V2IP source switch command for routing video and audio streams.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:BayBase, video:BayBase|str|None=None, audio:BayBase|str|None=None) -> FrameBase|None:
        '''Build a V2IP source switch frame for transmission.'''
        if video is not None:
            if isinstance(video, BayBase):
                if BayFeaturesMask.V2IP_SOURCE_LOCAL not in video.features and BayFeaturesMask.V2IP_SOURCE_REMOTE not in video.features:
                    raise Exception(f"{video} is not a v2ip source")
                if video.v2ip_source is None:
                    raise Exception(f"{video} v2ip addresses not known")

        if audio is not None:
            if isinstance(audio, BayBase):
                if BayFeaturesMask.V2IP_SOURCE_LOCAL not in audio.features and BayFeaturesMask.V2IP_SOURCE_REMOTE not in audio.features:
                    raise Exception(f"{audio} is not a v2ip source")
                if audio.v2ip_source is None:
                    raise Exception(f"{audio} v2ip addresses not known")

        payload = target.device.remote_id.byte_value
        if video is not None:
            video_ip = video.v2ip_source.video.ip if isinstance(video, BayBase) else video.split(':', 1)[0] # pyright: ignore[reportOptionalMemberAccess]
            ip = socket.inet_aton(video_ip)
            payload += bytes([int(ip[0]), int(ip[1]), int(ip[2]), int(ip[3])])
        else:
            payload += bytes([0, 0, 0, 0])
        if audio is not None:
            audio_ip = audio.v2ip_source.audio.ip if isinstance(audio, BayBase) else audio.split(':', 1)[0] # pyright: ignore[reportOptionalMemberAccess]
            ip = socket.inet_aton(audio_ip)
            payload += bytes([int(ip[0]), int(ip[1]), int(ip[2]), int(ip[3])])
        else:
            payload += bytes([0, 0, 0, 0])
        return FrameBase.construct_base(mxr=mxr, opcode=0x1F, payload=payload)

    @cached_property
    def target_device(self) -> DeviceBase|None:
        '''Target device for the source switch.'''
        return self.mxr.get_by_uid(self.target_uid)

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        '''UID of the target device.'''
        return self.payload_uuid(0)

    @cached_property
    def video(self) -> str:
        '''Video stream source IP address.'''
        if (self.payload is None) or (len(self.payload) < 24):
            raise Exception("invalid FrameV2IPSourceSwitch size")
        ip = int.from_bytes(self.payload[16:20], "big")
        return socket.inet_ntoa(struct.pack('!L', ip))

    @cached_property
    def video_bay(self) -> BayBase|None:
        '''Bay that is the video stream source.'''
        return self.mxr.get_by_stream_ip(ip=self.video, audio=False)

    @cached_property
    def audio(self) -> str:
        '''Audio stream source IP address.'''
        if (self.payload is None) or (len(self.payload) < 24):
            raise Exception("invalid FrameV2IPSourceSwitch size")
        ip = int.from_bytes(self.payload[20:24], "big")
        return socket.inet_ntoa(struct.pack('!L', ip))

    @cached_property
    def audio_bay(self) -> BayBase|None:
        '''Bay that is the audio stream source.'''
        return self.mxr.get_by_stream_ip(ip=self.audio, audio=True)

    def process(self) -> None:
        '''Update the local device cache with the new source routing.'''
        if (self.target_device is not None):
            sink_bay = self.target_device.first_output
            if (sink_bay is not None):
                sink_bay.on_mxr_update(SelectedBays(self.video_bay, self.audio_bay))

    def __str__(self) -> str:
        return f"V2IP source switch: {self.target_device} -> {self.video}={self.video_bay}/{self.audio}={self.audio_bay}"
