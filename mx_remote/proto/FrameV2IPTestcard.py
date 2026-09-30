######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for a OneIP sink's test pattern, tone and lip-sync flash.'''

from functools import cached_property
from typing import Any
import struct
from ..compat import override
from .FrameBase import FrameBase
from .Constants import OneIPTestcardFlag, OneIPTestPattern, OneIPToneMode
from ..Interface import DeviceRegistry, OneIPTestcard, OneIPTestSync, OneIPTestTone, _wire_enum
from ..Uid import MxrDeviceUid

# Payload, 56 bytes, whatever the frame type:
#     0..16   uid of the sink
#    16       frame type: TESTCARD_REQUEST, TESTCARD_SET or TESTCARD_STATE
#    17       flags: on a change the TESTCARD_PART_* it carries, on a report
#             the OneIPTestcardFlag bits
#    18       pattern
#    19       tone mode
#    20..24   u32 colour, 0xRRGGBB
#    24..32   tone: u16 frequency, i8 level, u8 channels, u32 rate
#    32..42   lip-sync: u16 period, u16 lead, u32 offset, u16 beep ms
#    42..44   reserved
#    44..56   u32 frames, u32 periods, u32 marks
#
# A sink answers every request and change with its report, sent on the group,
# so every device hears it and records it against the sink the frame names.
TESTCARD_SIZE = 56

TESTCARD_REQUEST = 0
'''Asks the sink for its report; nothing past the type is read.'''
TESTCARD_SET = 1
'''Changes the parts the flags byte names.'''
TESTCARD_STATE = 2
'''The sink's report.'''

TESTCARD_PART_PATTERN = (1 << 0)
TESTCARD_PART_TONE = (1 << 1)
TESTCARD_PART_SYNC = (1 << 2)

_LAYOUT = struct.Struct('<BBBBIHbBIHHIH2xIII')

class FrameV2IPTestcard(FrameBase):
    '''A request, a change, or a sink's report of its test card.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:Any, target_uid:MxrDeviceUid, kind:int, parts:int=0,
                  testcard:OneIPTestcard=OneIPTestcard()) -> FrameBase|None:
        '''Build a request or a change addressed to one sink.

        A sink reads only the parts named in parts from a change, and nothing
        past the type from a request; the counters are the sink's to report and
        go out zero.'''
        tone, sync = testcard.tone, testcard.sync
        payload = target_uid.byte_value + _LAYOUT.pack(
            kind, parts, int(testcard.pattern), int(tone.mode), testcard.colour,
            tone.freq, tone.level, tone.channels, tone.rate,
            sync.period, sync.lead, sync.offset, sync.beep_ms, 0, 0, 0)
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x4E, payload=payload)

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        '''The sink this frame is about.'''
        return self.payload_uuid(0)

    @cached_property
    def kind(self) -> int|None:
        '''The frame type, None for a frame shorter than the whole struct.'''
        if (self.payload is None) or (len(self.payload) < TESTCARD_SIZE):
            return None
        return self.payload[16]

    @cached_property
    def testcard(self) -> OneIPTestcard|None:
        '''The test card a sink reports, None for a request, a change, or a
        frame shorter than the whole struct.'''
        if (self.kind != TESTCARD_STATE) or (self.payload is None):
            return None
        (_, flags, pattern, mode, colour, freq, level, channels, rate,
         period, lead, offset, beep, frames, periods, marks) = _LAYOUT.unpack_from(self.payload, 16)
        return OneIPTestcard(
            flags=OneIPTestcardFlag(flags),
            pattern=_wire_enum(OneIPTestPattern, pattern),
            colour=(colour & 0xFFFFFF),
            tone=OneIPTestTone(mode=_wire_enum(OneIPToneMode, mode), freq=freq, level=level,
                              channels=channels, rate=rate),
            sync=OneIPTestSync(period=period, lead=lead, offset=offset, beep_ms=beep),
            frames=frames, periods=periods, marks=marks)

    @override
    def process(self) -> None:
        '''Record a sink's report against the sink it names.'''
        if ((testcard := self.testcard) is None) or ((uid := self.target_uid) is None):
            return
        if ((dev := self.mxr.get_by_uid(uid)) is not None):
            dev.on_mxr_update(testcard)

    def __str__(self) -> str:
        if (self.kind is None):
            return "OneIP test card <short>"
        if (self.testcard is not None):
            return f"OneIP test card of {self.target_uid}: {self.testcard}"
        return f"OneIP test card {('request', 'change')[self.kind] if self.kind < 2 else self.kind} for {self.target_uid}"
