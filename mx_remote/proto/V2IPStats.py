######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Video-over-IP transmitter and receiver statistics parsing.'''

from enum import IntEnum
from .Constants import decode_enum

class V2IPTxStats:
    '''Transmitter stream statistics (packet counts and errors).'''

    def __init__(self, data:bytes|None) -> None:
        if (data is None) or (len(data) < 20):
            raise Exception('invalid stats data')
        self._data = data

    @property
    def video(self) -> int:
        '''Video packet count.'''
        return int.from_bytes(self._data[0:4], "little")

    @property
    def audio(self) -> int:
        '''Audio packet count.'''
        return int.from_bytes(self._data[4:8], "little")

    @property
    def anc(self) -> int:
        '''Ancillary data packet count.'''
        return int.from_bytes(self._data[8:12], "little")

    @property
    def stream_down(self) -> int:
        '''Stream-down event count.'''
        return int.from_bytes(self._data[12:16], "little")

    @property
    def overflow(self) -> int:
        '''Buffer overflow count.'''
        return int.from_bytes(self._data[16:20], "little")

    def __str__(self) -> str:
        rv = f"Video: {self.video}, Audio: {self.audio}, Anc: {self.anc}"
        if self.stream_down > 0:
            rv += f", Stream Down:{self.stream_down}"
        if self.overflow > 0:
            rv += f", Overflow:{self.overflow}"
        return rv

    def __repr__(self) -> str:
        return str(self)

# The two stats structs are 20 and 44 bytes, which is what makes the 0x3F payload
# 128: tx 0..20, tx_per_minute 20..40, rx 40..84, rx_per_minute 84..128, with the
# decoder state at +40 inside each rx block (absolute 80 and 124).
#
# Those sizes hold by accident. Both are declared with the ALIGN(8) attribute
# placed before the `struct` keyword, where GCC ignores it - written the other
# way round they would be 24 and 48 and every block after the first would shift.
# So this layout is stable because of a misplaced attribute rather than by
# intent, and a tidy-up of that declaration would change the wire format without
# anything in the firmware looking different. Check the sizes, not just the field
# offsets, if these ever stop lining up.

class V2IPDecoderState(IntEnum):
    '''Health state of the V2IP decoder.

    Mirrors enum v2ip_decoder_state (Devices/BSP/V2IP/v2ip_sink_stats.h). Only
    HEALTHY and BAD are verdicts: UNKNOWN and STARTING both mean the decoder has
    not said yet. Testing `state != HEALTHY` therefore reads a receiver that is
    merely coming up as one that failed to decode, which is the opposite of what
    it means - use `settled` to tell a verdict from a non-answer.

    HEALTHY is the firmware's V2IP_STATE_GOOD; the name differs, the value does
    not.
    '''
    UNKNOWN = 0
    HEALTHY = 1
    BAD = 2
    STARTING = 3

    @property
    def settled(self) -> bool:
        '''True when this state is a verdict rather than "has not said yet".'''
        return (self.value in (V2IPDecoderState.HEALTHY.value, V2IPDecoderState.BAD.value))

    def __str__(self) -> str:
        if self.value == V2IPDecoderState.HEALTHY.value:
            return 'Healthy'
        if self.value == V2IPDecoderState.BAD.value:
            return 'Bad'
        if self.value == V2IPDecoderState.STARTING.value:
            return 'Starting'
        return 'Unknown'

class V2IPRxStats:
    '''Receiver stream statistics (packet counts, drops, and sequence errors).'''

    def __init__(self, data:bytes) -> None:
        if len(data) < 44:
            raise Exception(f'invalid stats size: {len(data)}')
        self._data = data

    @property
    def video_total(self) -> int:
        '''Total video packets received.'''
        return int.from_bytes(self._data[0:4], "little")

    @property
    def video_dropped(self) -> int:
        '''Dropped video packets.'''
        return int.from_bytes(self._data[4:8], "little")

    @property
    def video_sequence_errors(self) -> int:
        '''Video packet sequence errors.'''
        return int.from_bytes(self._data[8:12], "little")

    @property
    def wdt_timeout(self) -> int:
        '''Watchdog timeout count.'''
        return int.from_bytes(self._data[12:16], "little")

    @property
    def audio_total(self) -> int:
        '''Total audio packets received.'''
        return int.from_bytes(self._data[16:20], "little")

    @property
    def audio_dropped(self) -> int:
        '''Dropped audio packets.'''
        return int.from_bytes(self._data[20:24], "little")

    @property
    def audio_sequence_errors(self) -> int:
        '''Audio packet sequence errors.'''
        return int.from_bytes(self._data[24:28], "little")

    @property
    def anc_total(self) -> int:
        '''Total ancillary data packets received.'''
        return int.from_bytes(self._data[28:32], "little")

    @property
    def anc_dropped(self) -> int:
        '''Dropped ancillary data packets.'''
        return int.from_bytes(self._data[32:36], "little")

    @property
    def anc_sequence_errors(self) -> int:
        '''Ancillary data packet sequence errors.'''
        return int.from_bytes(self._data[36:40], "little")

    @property
    def decoder_state(self) -> V2IPDecoderState:
        '''Current decoder health state.'''
        # a state this build does not know is UNKNOWN, not a ValueError out of
        # whatever happened to touch the property first
        return decode_enum(V2IPDecoderState, int(self._data[40])) or V2IPDecoderState.UNKNOWN

    def __str__(self) -> str:
        viseq = f" (seq: {self.video_sequence_errors})" if self.video_sequence_errors > 0 else ''
        auseq = f" (seq: {self.audio_sequence_errors})" if self.audio_sequence_errors > 0 else ''
        anseq = f" (seq: {self.anc_sequence_errors})" if self.anc_sequence_errors > 0 else ''
        wdt = f" WDT Timeout:{self.wdt_timeout}" if self.wdt_timeout > 0 else ''
        return f"State: {self.decoder_state}, Video: {self.video_total}{viseq}, Audio: {self.audio_total}{auseq}, Anc: {self.anc_total}{anseq}{wdt}"

class V2IPDeviceStats:
    '''Combined TX and RX statistics for a V2IP device.'''

    tx:V2IPTxStats|None = None
    tx_per_minute:V2IPTxStats|None = None
    rx:V2IPRxStats|None = None
    rx_per_minute:V2IPRxStats|None = None

    def __str__(self) -> str:
        return f"v2ip stats: tx={self.tx_per_minute} rx={self.rx_per_minute}"

    def __repr__(self) -> str:
        return str(self)