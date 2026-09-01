######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for infrared (IR) remote control key press events.'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import BayBase
import logging

_LOGGER = logging.getLogger(__name__)

# mxr_ir_data wire layout. The struct is NOT packed and carries no ALIGN(), so
# it is laid out with natural alignment and TMTicks is uint_fast32_t (4 bytes,
# 4-aligned) - which puts two bytes of padding after the u16 port:
#   0..2     mbay_port_id port
#   2..4     padding
#   4..8     TMTicks timestamp
#   8..12    TMTicks last_change
#   12..22   struct ir_raw_meta (4 x u16 + u8 status, padded to 10)
#   22..24   padding
# sizeof is 24, and the firmware appends the raw timings at exactly that offset
# (&payload[sizeof(mxr_ir_data)]), so the padding is load-bearing on both ends.
_META_OFFSET = 12
_TIMINGS_OFFSET = 24

# A receiver requires one timing beyond the struct, not just the struct, and it
# requires this protocol version. Both are the firmware's own gates. The length
# one reads like an off-by-one and is not: a capture with no timing is a burst
# nothing blasted, with nothing in it to replay, and it decodes perfectly.
_MIN_SIZE = _TIMINGS_OFFSET + 2
_ACCEPT_PROTOCOL = 0x19

class FrameRCIr(FrameBase):
    '''IR key press event received by a bay.'''
    @cached_property
    def acceptable(self) -> bool:
        '''Whether a receiver would act on this frame at all.

        Every field below reads None or empty when this is False, so a frame no
        device blasted cannot be mistaken for a capture with nothing in it.
        '''
        pl = self.payload
        if (pl is None) or (len(pl) < _MIN_SIZE):
            return False
        # The count is a declaration, not a measurement: nothing on the wire
        # ties it to the number of timings that arrived. A frame claiming more
        # than it carries is refused rather than handed to a caller that would
        # index the timings by it.
        nb = self.payload_u16(idx=_META_OFFSET + 4)
        return (nb is not None) and (nb <= ((len(pl) - _TIMINGS_OFFSET) // 2)) \
            and (self.protocol >= _ACCEPT_PROTOCOL)

    @cached_property
    def bay(self) -> BayBase|None:
        '''Bay that received the IR key press.'''
        if not self.acceptable:
            return None
        return self.payload_bay(device=self.remote_device, idx=0, u16=True)

    @cached_property
    def ir_timestamp(self) -> int|None:
        '''System clock value on the sender when the IR command was received.

        Not named `timestamp`: FrameBase assigns that instance attribute for our
        own receive time, and an instance attribute shadows a cached_property of
        the same name.
        '''
        return self.payload_u32(idx=4) if self.acceptable else None

    @cached_property
    def last_change(self) -> int|None:
        '''System clock value of the previous edge.'''
        return self.payload_u32(idx=8) if self.acceptable else None

    @cached_property
    def timer_resolution(self) -> int|None:
        '''Resolution of the TMTicks the timings are expressed in.'''
        return self.payload_u16(idx=_META_OFFSET) if self.acceptable else None

    @cached_property
    def frequency(self) -> int|None:
        '''Detected carrier frequency.'''
        return self.payload_u16(idx=_META_OFFSET + 2) if self.acceptable else None

    @cached_property
    def nb_timings(self) -> int|None:
        '''Number of raw timings that follow the struct.'''
        return self.payload_u16(idx=_META_OFFSET + 4) if self.acceptable else None

    @cached_property
    def replayable(self) -> bool:
        '''Whether a receiver would emit anything for this capture.

        A second threshold, above `acceptable`: one timing gets the frame read,
        more than one gets something blasted, because the first is dropped.
        '''
        return self.acceptable and ((nb := self.nb_timings) is not None) and (nb > 1)

    @cached_property
    def repeat_offset(self) -> int|None:
        '''Index into the timings where the repeat section starts.'''
        return self.payload_u16(idx=_META_OFFSET + 6) if self.acceptable else None

    @cached_property
    def status(self) -> int|None:
        '''IR receive status flags.'''
        return self.payload_u8(idx=_META_OFFSET + 8) if self.acceptable else None

    @cached_property
    def timings(self) -> bytes:
        '''Raw on/off timings appended after the struct.

        A receiver drops the first timing and blasts from the second, so this
        list is one longer than what is emitted. The first is discarded
        outright, not treated as a leading gap: the interval before the burst
        comes from the sender's timestamp instead.

        The targeted transmit request (0x48) carries its timings the same way,
        so a capture replays by passing this across byte for byte, with the
        declared count unchanged and the discarded first slot included. Its
        header is a different struct and must be rebuilt, and its timestamp has
        to be the sender's own clock at send time rather than the one captured
        here, because the receiver computes the gap before the burst from it.

        The values are the receiver's timer ticks, not microseconds, and the
        receiver applies its own tick length rather than the resolution
        reported beside them.
        '''
        if not self.acceptable:
            return bytes()
        if ((pl := self.payload_idx(_TIMINGS_OFFSET)) is None):
            return bytes()
        return pl

    def __str__(self) -> str:
        return f"IR key press bay {self.bay} at {self.ir_timestamp} freq {self.frequency} timings {self.nb_timings}"
