######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for V2IP_SINK_SDP (opcode 0x52): what a OneIP output plays
from a session description, and the commands that hand it one.'''

from functools import cached_property
import ipaddress
import struct
from typing import Any
from ..compat import override
from .Constants import (OneIPSdpClockMode, OneIPSdpClockState, OneIPSdpEncoding, OneIPSdpFlag,
                        OneIPSdpMediaClock, OneIPSdpRefClock)
from .FrameBase import FrameBase
from ..Interface import DeviceRegistry, OneIPSinkSdp, _wire_enum
from ..Uid import MxrDeviceUid

# Every frame opens with the output's uid, the frame type at 16, a value at 17
# and two reserved bytes.
#
# A status report follows with 80 bytes: flags, screen, encoding, channels,
# payload type, media clock, reference clock, clock mode and clock state, one
# byte each, a reserved byte, then u16 port at 10, u32 rate at 12, u32 media
# clock offset at 16, the IPv4 group at 20, a 48-byte session name at 24 and an
# 8-byte channel layout at 72. It grows at the back, so it is read as far as it
# goes and the fields it does not reach read as zero.
#
# A page follows the header with the description's length, the page's offset
# into it and the page's length, all u16, two reserved bytes, and at most
# SDP_PAGE_LEN bytes of the description.
SDP_HEADER_SIZE = 20
_STATUS_SIZE = 80

SDP_STATUS = 0
'''The output's report.'''
SDP_PAGE = 1
'''A page of a description to play.'''
SDP_STOP = 2
'''Stop the described stream.'''
SDP_SCREEN = 3
'''What the output shows while it plays audio alone, in the value byte.'''
SDP_REQUEST = 4
'''Report now.'''

SDP_PAGE_LEN = 1024
'''The most bytes of a session description one page carries.'''

def _cstr(data:bytes) -> str:
    return data.split(b'\0', 1)[0].decode('ascii', errors='replace')

class FrameV2IPSinkSdp(FrameBase):
    '''A OneIP output's report of what it plays from a session description, or a
    command handing it one.'''
    @staticmethod
    def construct_command(mxr:DeviceRegistry, target:Any, target_uid:MxrDeviceUid, kind:int,
                          value:int=0) -> FrameBase|None:
        '''A command without a description: stop, screen or request.'''
        payload = target_uid.byte_value + bytes([kind, value & 0xFF, 0, 0])
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x52, payload=payload)

    @staticmethod
    def construct_pages(mxr:DeviceRegistry, target:Any, target_uid:MxrDeviceUid, sdp:bytes) -> list[FrameBase]|None:
        '''The pages that hand an output a description, in order. The output
        starts a description at offset 0 and plays it once the last byte has
        arrived. None when the target cannot receive the opcode.'''
        pages = []
        for offset in range(0, len(sdp), SDP_PAGE_LEN):
            chunk = sdp[offset:offset + SDP_PAGE_LEN]
            payload = (target_uid.byte_value + bytes([SDP_PAGE, 0, 0, 0])
                       + struct.pack('<HHH2x', len(sdp), offset, len(chunk)) + chunk)
            if ((frame := FrameBase.construct_base(target=target, mxr=mxr, opcode=0x52, payload=payload)) is None):
                return None
            pages.append(frame)
        return pages

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        '''The output this frame is about.'''
        return self.payload_uuid(0)

    @cached_property
    def kind(self) -> int|None:
        '''The frame type, None for a frame shorter than its header.'''
        if (len(self.payload or b'') < SDP_HEADER_SIZE):
            return None
        return self.payload_u8(16)

    @cached_property
    def status(self) -> OneIPSinkSdp|None:
        '''What the output reports it plays, None for a command.'''
        if (self.kind != SDP_STATUS) or (self.payload is None):
            return None
        s = self.payload[SDP_HEADER_SIZE:].ljust(_STATUS_SIZE, b'\0')
        flags, screen, encoding, channels, payload_type, media_clock, ref_clock, clock_mode, clock_state, \
            port, rate, offset = struct.unpack_from('<BBBBBBBBBxHII', s)
        return OneIPSinkSdp(
            flags=OneIPSdpFlag(flags), screen=screen,
            encoding=_wire_enum(OneIPSdpEncoding, encoding), channels=channels, payload_type=payload_type,
            media_clock=_wire_enum(OneIPSdpMediaClock, media_clock),
            ref_clock=_wire_enum(OneIPSdpRefClock, ref_clock),
            clock_mode=_wire_enum(OneIPSdpClockMode, clock_mode),
            clock_state=_wire_enum(OneIPSdpClockState, clock_state),
            port=port, rate_hz=rate, media_clock_offset=offset,
            group=str(ipaddress.IPv4Address(s[20:24])),
            # The output terminates both strings in their last byte, so a name
            # that fills its field stops one byte short of it.
            name=_cstr(s[24:71]), layout=_cstr(s[72:79]))

    @override
    def process(self) -> None:
        '''Record an output's report against the output that sent it. The other
        types are commands for an output, which only that output acts on.'''
        if ((status := self.status) is not None) and ((dev := self.remote_device) is not None):
            dev.on_mxr_update(status)

    def __str__(self) -> str:
        if (self.status is not None):
            return f"OneIP sink SDP: {self.status}"
        return f"OneIP sink SDP command {self.kind} for {self.uid_to_user_string(self.target_uid)}"
