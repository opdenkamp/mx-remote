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

# The 0x3F counters occupy the first 128 bytes: tx 0..20, tx_per_minute 20..40,
# rx 40..84, rx_per_minute 84..128, with the decoder state at +40 in each rx
# block.
#
# Those block sizes are 20 and 44 only because the firmware's ALIGN(8) attribute
# sits before the `struct` keyword, where GCC ignores it. Written the other way
# round they would be 24 and 48 and every block after the first would shift, so
# check the sizes and not just the field offsets if these stop lining up.

V2IP_STATS_COUNTERS_LEN = 128
'''Payload length of the four counter blocks, which is the whole payload from a
sender that predates the decoder detail block.'''

V2IP_DECODER_DETAIL_OFFSET = 128
'''Offset of the decoder detail block, which is where the counters end.'''

V2IP_DECODER_DETAIL_LEN = 24
'''Size of the decoder detail block, carried from MatrixOS 10.12.46.

20 bytes of fields rounded to 24 by ALIGN(8). The trailing four are the struct's
own padding: a device clears the payload buffer before writing any field, so a
non-zero value there is a newer sender or a bug, never noise. Along with the
reserved byte at +3 it is where the next expansion lands.'''

V2IP_STATS_FULL_LEN:int = V2IP_DECODER_DETAIL_OFFSET + V2IP_DECODER_DETAIL_LEN
'''Payload length of a report that carries the decoder detail block.'''

V2IP_DECODER_PROTOCOL = 0x29
'''Protocol version the decoder detail block appeared at.

Read with the payload length rather than instead of it: the length says a
payload is long enough to hold the block, and the stamp says those bytes are
that block rather than some later growth this client has no name for. A sender
below this stamps a report of the shape it always had, so its counters are read
and its tail, if any, is not.'''

class V2IPDecoderState(IntEnum):
    '''Health state of the V2IP decoder.

    Only HEALTHY and BAD are verdicts; UNKNOWN and STARTING mean the decoder has
    not said yet. Use `settled` rather than `state != HEALTHY`, which reads a
    receiver that is merely starting as one that failed to decode.

    HEALTHY is the firmware's V2IP_STATE_GOOD - the name differs, the value does
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
        # ONE byte at 40, with three of padding after it: it is a plain enum and
        # Cortex-M builds with -fshort-enums.
        #
        # This sender does zero that padding: it writes through pointers into
        # an already-zeroed buffer rather than copying a stack struct, so unlike
        # 0x45 there is no stack content here.
        # Keep the read one byte anyway: that is a property of one sender's
        # implementation, not of the protocol, and the 0x45 sender demonstrates
        # what the other approach puts on the wire. A width that is only correct
        # because of how a particular transmitter happens to build its payload
        # is not correct, it is unfalsified.
        #
        # A state this build does not know is UNKNOWN rather than a ValueError
        # out of whatever happened to touch the property first.
        st = decode_enum(V2IPDecoderState, int(self._data[40]))
        return st if (st is not None) else V2IPDecoderState.UNKNOWN

    def __str__(self) -> str:
        viseq = f" (seq: {self.video_sequence_errors})" if self.video_sequence_errors > 0 else ''
        auseq = f" (seq: {self.audio_sequence_errors})" if self.audio_sequence_errors > 0 else ''
        anseq = f" (seq: {self.anc_sequence_errors})" if self.anc_sequence_errors > 0 else ''
        wdt = f" WDT Timeout:{self.wdt_timeout}" if self.wdt_timeout > 0 else ''
        return f"State: {self.decoder_state}, Video: {self.video_total}{viseq}, Audio: {self.audio_total}{auseq}, Anc: {self.anc_total}{anseq}{wdt}"

class V2IPDecoderReason(IntEnum):
    '''Why the decoder is reporting what it is reporting.

    Only the primary cause; every cause that applies is in
    V2IPDecoderReading.flags.

    Use this for display and V2IPDecoderReading.causes for logic. Every true
    cause sets its bit in `flags`; which one keeps `reason` is a fixed priority
    in the video processor, and deliberately not the numbering here - the
    firmware's own header says these values are identifiers carrying no
    precedence. TX_BRIDGE_UNLOCKED ranks below every input-side cause, so during
    a repeating pipeline restart an input cause names itself and bit 9 shows in
    `flags` alone: a check keyed on `reason` misses that restart loop always,
    not briefly.

    There is deliberately no UNKNOWN member: 0 is OK, a verdict somebody would
    act on, so folding an unrecognised value onto any member here gives a
    confidently wrong answer.
    decode_enum yields None instead, and V2IPDecoderReading.reason_value keeps
    the raw byte. Firmware adds reasons without a protocol bump, so a None here
    is expected traffic rather than a decode failure.
    '''
    OK = 0
    NO_PACKETS = 1
    PACKETS_DEGRADED = 2
    NO_FORMAT = 3
    FORMAT_MISMATCH = 4
    FORMAT_REJECTED = 5
    DECODER_BLOCKED = 6
    SWITCH_PENDING = 7
    PTP_UNLOCKED = 8
    '''A real fault, scoped to the audio; the picture is unaffected.'''
    TX_BRIDGE_UNLOCKED = 9
    '''The pipeline rebuilding after the HDMI bridge stayed unlocked.

    Never a transient: the bridge must read unlocked for a sustained 5000ms
    before this exists, so the picture has been down five seconds by the time it
    arrives. The debounce restarts each time it elapses, so this sustained
    across reports is a restart loop rather than one event.

    Evaluated only while no format change is in progress, so across a switch it
    holds its previous value and clears on the first poll after the change
    settles. `updates` cannot see that - a value carried forward is a stored
    reading like any other.'''
    IDLE = 10
    '''A sink its owner has switched off, named as such rather than left to look
    broken.

    Sent only by builds later than 10.12.46, which is where this block first
    appeared. Below that a disabled sink reports NO_PACKETS indefinitely, so an
    absent IDLE is not evidence a sink is enabled - it is as likely to be an
    older sender. Nothing in this block answers enablement in either direction:
    read that from MXR_OP_V2IP_DEVICE_CFG or the HTTP status.

    Where it is sent, it outranks the causes below it without excluding them.
    A disabled sink keeps every bit the decoder genuinely observed, so a check
    that masks `flags` for faults calls it broken - the exact bug naming it was
    meant to remove, moved into the caller. Test for this cause first and stop;
    the bits beneath it are a real reading, not noise to discard.

    Do not read it as implying an absence, either: FORMAT_MISMATCH needs only a
    detected geometry beside a configured one, which a switched-off sink can
    still have.'''

    def __str__(self) -> str:
        return {
            V2IPDecoderReason.OK.value:                 'Ok',
            V2IPDecoderReason.NO_PACKETS.value:         'No Packets',
            V2IPDecoderReason.PACKETS_DEGRADED.value:   'Packets Degraded',
            V2IPDecoderReason.NO_FORMAT.value:          'No Format Recovered',
            V2IPDecoderReason.FORMAT_MISMATCH.value:    'Format Mismatch',
            V2IPDecoderReason.FORMAT_REJECTED.value:    'Format Rejected',
            V2IPDecoderReason.DECODER_BLOCKED.value:    'Decoder Blocked',
            V2IPDecoderReason.SWITCH_PENDING.value:     'Switch Pending',
            V2IPDecoderReason.PTP_UNLOCKED.value:       'PTP Unlocked',
            V2IPDecoderReason.TX_BRIDGE_UNLOCKED.value: 'TX Bridge Unlocked',
            V2IPDecoderReason.IDLE.value:               'Idle',
        }[self.value]

    def __repr__(self) -> str:
        return str(self)

class V2IPColorFormat(IntEnum):
    '''Colour space the decoder recovered from the codestream.

    UNNAMED is the decoder answering that it cannot name the format. That is a
    different answer from a format this build has no member for, which decodes
    to None with the raw number in V2IPDecoderReading.format_value - so UNNAMED
    is not spelled UNKNOWN, which is the name decode_enum would fold every
    unrecognised value onto.

    This is not the signal-status colour space enum, which spells its unknown
    0xF. Casting UNNAMED into that one lands outside its range; casting the
    other way lands on YCbCr 4:2:0.
    '''
    RGB = 0
    YCBCR_444 = 1
    YCBCR_422 = 2
    YCBCR_420 = 3
    UNNAMED = 255

    def __str__(self) -> str:
        return {
            V2IPColorFormat.RGB.value:       'RGB',
            V2IPColorFormat.YCBCR_444.value: 'YCbCr 4:4:4',
            V2IPColorFormat.YCBCR_422.value: 'YCbCr 4:2:2',
            V2IPColorFormat.YCBCR_420.value: 'YCbCr 4:2:0',
            V2IPColorFormat.UNNAMED.value:   'Unnamed',
        }[self.value]

    def __repr__(self) -> str:
        return str(self)

class V2IPDecoderReading:
    '''What a sink's decoder recovered from the codestream it is being given.

    Geometry and colour format read off the codestream itself, so this
    separates "the decoder understood the stream" from "something came out the
    other end and the scaler made it presentable".

    Only reachable through V2IPDecoderDetail.reading, which is None until the
    decoder has answered at all - so there is no way to read geometry off a
    block that carries none.

    Colour depth is absent and stays absent: the video processor answers depth
    from a driver constant rather than from the codestream, so it was withheld
    rather than shipped as a constant that looks like a measurement. Assert
    depth at the encoder's input bay instead.
    '''

    def __init__(self, data:bytes) -> None:
        if (data is None) or (len(data) < V2IP_DECODER_DETAIL_LEN):
            raise Exception(f'invalid decoder detail size: {0 if (data is None) else len(data)}')
        self._data = data

    @property
    def reason_value(self) -> int:
        '''Primary cause as it arrived, named or not.

        Firmware adds causes without a protocol bump, so keep an unrecognised
        one opaque and pass it through: it is not a decode failure, and it is
        not any of the causes `reason` can name.'''
        return int(self._data[1])

    @property
    def reason(self) -> V2IPDecoderReason|None:
        '''Primary cause, or None for a cause this build has no name for.'''
        return decode_enum(V2IPDecoderReason, self.reason_value)

    @property
    def blocking(self) -> bool:
        '''True while the converter watchdog is holding the stream back.

        Byte 2. Byte 3 beside it is reserved and must be ignored - a read
        widened to two bytes, or taken one byte late, picks it up and reports a
        block that is not happening.'''
        return (int(self._data[2]) != 0)

    @property
    def width(self) -> int:
        '''Width recovered from the codestream, 0 if none. Pre-scaler, unrounded.'''
        return int.from_bytes(self._data[4:6], "little")

    @property
    def height(self) -> int:
        '''Height recovered from the codestream, 0 if none. Pre-scaler, unrounded.'''
        return int.from_bytes(self._data[6:8], "little")

    @property
    def recovered(self) -> bool:
        '''True when the decoder recovered a picture from the codestream.

        Geometry is what answers this. `format` never does, at any value: with
        no stream it reads 0, which is RGB, and is indistinguishable from a real
        reading of an RGB source.

        This answers what the decoder currently detects, never whether the sink
        is switched on: a sink at rest can be detecting a picture perfectly
        well, so False here is "nothing is arriving", not "nobody asked for
        anything". Enablement is not in this block at all.'''
        return (self.width > 0) and (self.height > 0)

    @property
    def format_value(self) -> int:
        '''Colour space as it arrived, named or not.'''
        return int.from_bytes(self._data[8:10], "little")

    @property
    def format(self) -> V2IPColorFormat|None:
        '''Colour space, or None for a value this build has no name for.

        UNNAMED (255) is the decoder's own "cannot name it" and is a reading,
        not an absence. Never read any value of this as no-signal - see
        `recovered`.'''
        return decode_enum(V2IPColorFormat, self.format_value)

    @property
    def updates(self) -> int:
        '''Count of readings stored, for telling a fresh reading from a repeat.

        The values are read off the video processor every 2s and reported every
        1s, latched between reads, so roughly every other report repeats a
        reading already seen and a frame arriving says nothing about freshness.
        This moves only when a reading is actually stored, so a stalled
        processor leaves it still rather than implying a refresh.

        Monotonic, never reset, wraps at 65535 (~36h at 2s).

        After changing what a sink is pointed at, wait for this to advance by
        **two** before trusting the geometry. It ticks when the reply lands,
        not when the query is sent, so a single tick can carry an answer read
        fractionally before the switch. Two is a real bound: the firmware drops
        any queued duplicate before each new query, so at most one is
        outstanding and tick N+2's query was necessarily issued after tick
        N+1's reply landed.

        This counts readings stored, not measurements taken, and they are not
        the same: a field the processor could not re-evaluate is carried
        forward into the new reading and ticks this like any other. A tick
        vouches for the reading, not for every field in it - TX_BRIDGE_UNLOCKED
        holds its previous value across a format change.'''
        return int.from_bytes(self._data[10:12], "little")

    @property
    def flags(self) -> int:
        '''Every cause that applies, bit N set for reason N. Bit 0 is unused.

        `reason` is the primary one. A set bit this build cannot name is a
        cause a newer firmware reports, not a decode error.'''
        return int.from_bytes(self._data[12:16], "little")

    @property
    def causes(self) -> tuple[int, ...]:
        '''Every cause that applies, as raw reason values, lowest first.

        `reason` is one member of this set - whichever the firmware named - so
        judge a sink on the set and report the named one. A teardown was
        measured reporting reason 7, a transition, while causes 1 and 3 applied
        alongside it.'''
        return tuple(bit for bit in range(1, 32) if ((self.flags >> bit) & 1))

    def has_reason(self, reason:V2IPDecoderReason|int) -> bool:
        '''True when reason is among the causes that apply.

        Takes a raw value as well as a member, so a cause this build cannot yet
        name can still be tested for. OK reads False: bit 0 is unused, and a
        cause that applies is what a set bit means.'''
        return ((self.flags >> int(reason)) & 1) != 0

    @property
    def blocked_count(self) -> int:
        '''Times the converter watchdog has triggered.'''
        return int.from_bytes(self._data[16:20], "little")

    def __str__(self) -> str:
        geometry = f"{self.width}x{self.height}" if self.recovered else 'no picture'
        fmt = str(self.format) if (self.format is not None) else f"format #{self.format_value}"
        reason = str(self.reason) if (self.reason is not None) else f"reason #{self.reason_value}"
        rv = f"{geometry}, {fmt}, {reason}"
        if self.blocking:
            rv += f", Blocking (x{self.blocked_count})"
        return f"{rv}, Updates: {self.updates}"

    def __repr__(self) -> str:
        return str(self)

class V2IPDecoderDetail:
    '''The decoder detail block a 0x3F report carries from MatrixOS 10.12.46.

    Three answers this report can give, kept apart because they mean different
    things: no block at all (the sender predates it, and V2IPDeviceStats.decoder
    is None), a block whose decoder has never answered (`reading` is None), and a
    reading.
    '''

    def __init__(self, data:bytes) -> None:
        if (data is None) or (len(data) < V2IP_DECODER_DETAIL_LEN):
            raise Exception(f'invalid decoder detail size: {0 if (data is None) else len(data)}')
        self._data = data
        self._reading = V2IPDecoderReading(self._data) if (self._data[0] != 0) else None

    @property
    def valid(self) -> bool:
        '''True when the decoder has answered and `reading` carries a reading.'''
        return (self._reading is not None)

    @property
    def reading(self) -> V2IPDecoderReading|None:
        '''The reading, or None while the decoder has never answered.

        Every field is meaningless until the block's valid byte is set, which is
        why they live here rather than beside `valid`.'''
        return self._reading

    def __str__(self) -> str:
        return str(self._reading) if (self._reading is not None) else 'decoder has not reported'

    def __repr__(self) -> str:
        return str(self)

class V2IPDeviceStats:
    '''Combined TX and RX statistics for a V2IP device.'''

    tx:V2IPTxStats|None = None
    tx_per_minute:V2IPTxStats|None = None
    rx:V2IPRxStats|None = None
    rx_per_minute:V2IPRxStats|None = None
    decoder:V2IPDecoderDetail|None = None
    '''What the sink's decoder recovered, None from a sender that predates it.'''

    def __str__(self) -> str:
        dec = f" decoder={self.decoder}" if (self.decoder is not None) else ''
        return f"v2ip stats: tx={self.tx_per_minute} rx={self.rx_per_minute}{dec}"

    def __repr__(self) -> str:
        return str(self)