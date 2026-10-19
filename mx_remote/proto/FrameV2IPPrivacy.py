######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for V2IP_PRIVACY (opcode 0x54): how a OneIP source unit
encrypts its streams, and the request that asks it.'''

from functools import cached_property
import ipaddress
import struct
from typing import Any
from ..compat import override
from .FrameBase import FrameBase
from ..Interface import DeviceRegistry, OneIPPrivacy, OneIPPrivacyStream
from ..Uid import MxrDeviceUid

# Every frame opens with a uid, the frame type at 16, the count of streams that
# follow at 17 and two reserved bytes.
#
# A report follows with its streams, video, audio and ancillary data first, each
# PRIVACY_STREAM_SIZE bytes: the IPv4 group at 0, u16 port at 4, the version at
# 6, a reserved byte, then whether it is encrypted at 8, the two header extension
# ids at 9 and 10, the 8-byte IV at 11, the 16-byte key generator at 19, the
# 8-byte key id at 35 and u32 key version at 43, unaligned, and a reserved byte.
PRIVACY_HEADER_SIZE = 20
PRIVACY_STREAM_SIZE = 48
PRIVACY_STREAMS = 3

PRIVACY_REPORT = 0
'''A source unit's report.'''
PRIVACY_REQUEST = 1
'''Report now.'''

def _stream(s:bytes) -> OneIPPrivacyStream:
    port, = struct.unpack_from('<H', s, 4)
    key_version, = struct.unpack_from('<I', s, 43)
    return OneIPPrivacyStream(group=str(ipaddress.IPv4Address(s[0:4])), port=port, version=s[6],
                              on=(s[8] != 0), full_id=s[9], short_id=s[10], iv=bytes(s[11:19]),
                              key_generator=bytes(s[19:35]), key_id=bytes(s[35:43]),
                              key_version=key_version)

class FrameV2IPPrivacy(FrameBase):
    '''A OneIP source unit's report of how it encrypts its streams, or a request
    for one.'''
    @staticmethod
    def construct_request(mxr:DeviceRegistry, target:Any, target_uid:MxrDeviceUid|None) -> FrameBase|None:
        '''A request naming the source unit asked, or the zero uid for every one.'''
        uid = target_uid.byte_value if (target_uid is not None) else bytes(16)
        payload = uid + bytes([PRIVACY_REQUEST, 0, 0, 0])
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x54, payload=payload)

    @cached_property
    def kind(self) -> int|None:
        '''The frame type, None for a frame shorter than its header.'''
        if (len(self.payload or b'') < PRIVACY_HEADER_SIZE):
            return None
        return self.payload_u8(16)

    @cached_property
    def privacy(self) -> OneIPPrivacy|None:
        '''What the unit reports, None for a request and for a report missing
        any of the three streams.'''
        p = self.payload or b''
        if (self.kind != PRIVACY_REPORT) or (p[17] < PRIVACY_STREAMS) \
                or (len(p) < PRIVACY_HEADER_SIZE + PRIVACY_STREAMS * PRIVACY_STREAM_SIZE):
            return None
        at = lambda i: _stream(p[PRIVACY_HEADER_SIZE + i * PRIVACY_STREAM_SIZE:])
        return OneIPPrivacy(video=at(0), audio=at(1), anc=at(2))

    @override
    def process(self) -> None:
        '''Record a report against the unit that sent it, whatever uid its
        header names, as units file it. A request is for a unit with an encoder
        to answer, which this client is not.'''
        if ((privacy := self.privacy) is not None) and ((dev := self.remote_device) is not None):
            dev.on_mxr_update(privacy)

    def __str__(self) -> str:
        if (self.privacy is not None):
            return f"OneIP privacy: {self.privacy}"
        return f"OneIP privacy request for {self.uid_to_user_string(self.payload_uuid(0))}"
