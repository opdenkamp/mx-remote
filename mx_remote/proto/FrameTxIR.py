######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for targeted IR blast (RC_IR_TX, opcode 0x48).

A peer asks a target device to retransmit captured IR on one of its local
bays. The struct is mxr_tx_ir_data:

    0..16   mxr_uid   uid          target device uid
    16      uint8_t   local_mode   target's local bay mode (mbay_mode)
    17      uint8_t   local_bay    target's local bay number
    18-     padding/align
    20..24  TMTicks   timestamp    sender clock at send time
    24..34  ir_raw_meta            timer_resolution u16, frequency u16,
                                   nb_timings u16, repeat_offset u16,
                                   status u8
    34-     tail padding to the struct's 4-byte alignment
    36..    ir_timings raw on/off data

The struct is not PACKED, so both holes are on the wire: the one at 18 before
the 4-aligned TMTicks, and the tail padding rounding sizeof up to 36. Timings
are appended at sizeof, so they start at 36 rather than at the end of the last
field.

Payload size varies with the number of timings. The fixed prefix is decoded
into fields; the timings are exposed as a raw blob.
'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Uid import MxrDeviceUid

# sizeof(mxr_tx_ir_data), not the offset just past its last field - the struct
# is 4-aligned because of TMTicks, so 34 rounds up to 36. Taking the timings
# from 34 prepends two padding bytes and shifts every u16 timing by one byte.
_TX_IR_HEADER_SIZE = 36


class FrameTxIR(FrameBase):
    '''Targeted IR transmit request.'''

    @cached_property
    def target_uid(self) -> MxrDeviceUid | None:
        return self.payload_uuid(0)

    @cached_property
    def local_mode(self) -> int | None:
        return self.payload_u8(16)

    @cached_property
    def local_bay(self) -> int | None:
        return self.payload_u8(17)

    @cached_property
    def timestamp_ticks(self) -> int | None:
        return self.payload_u32(20)

    @cached_property
    def timer_resolution(self) -> int | None:
        return self.payload_u16(24)

    @cached_property
    def carrier_frequency(self) -> int | None:
        return self.payload_u16(26)

    @cached_property
    def nb_timings(self) -> int | None:
        return self.payload_u16(28)

    @cached_property
    def repeat_offset(self) -> int | None:
        return self.payload_u16(30)

    @cached_property
    def meta_status(self) -> int | None:
        return self.payload_u8(32)

    @cached_property
    def timings_raw(self) -> bytes | None:
        return self.payload_idx(_TX_IR_HEADER_SIZE)

    def __str__(self) -> str:
        return (f"tx ir target={self.uid_to_user_string(self.target_uid)} "
                f"mode={self.local_mode} bay={self.local_bay} "
                f"freq={self.carrier_frequency}Hz nb={self.nb_timings}")
