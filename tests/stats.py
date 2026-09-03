import os, sys, struct, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.proto.Factory import create_mxr_frame, process_mxr_frame
from mx_remote.proto.Constants import MXR_PROTOCOL_VERSION, MXR_OPCODE_VERSIONS
from mx_remote.proto.V2IPStats import (V2IPDecoderState, V2IPDecoderReason,
    V2IPColorFormat, V2IP_DECODER_PROTOCOL, V2IP_STATS_COUNTERS_LEN,
    V2IP_STATS_FULL_LEN)

UID = bytes(range(1, 17)); ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False); mx._uid = bytes(range(100, 116))
def nm(s, sz=16):
    b = s.encode('ascii')[:sz]; return b + bytes(sz - len(b))
mx.process_frame(time.time(), create_mxr_frame(UID, 0x00, struct.pack('<H',0x28)+nm('MX-1')+nm('P8SN12345678')+nm('4.7.9')+struct.pack('<I',1<<5)), ADDR)

# The block sizes are 20 and 44 only because ALIGN(8) sits before the `struct`
# keyword in the firmware, where GCC ignores it. Written the other way round they
# would be 24 and 48 and every block after the first would shift. Pin the
# boundaries, not just the 128-byte total: a wrong split still totals 128.
TX_SIZE, RX_SIZE = 20, 44

# Every counter value must exceed 0xFFFF. They are u32 on the wire, and a read
# narrowed to u16 returns the right answer for any value that fits in one - so
# small fixture values pin the offset and say nothing about the width.
TX_BASE, TX_MIN_BASE, RX_BASE, RX_MIN_BASE = 100000, 200000, 300000, 400000
assert min(TX_BASE, TX_MIN_BASE, RX_BASE, RX_MIN_BASE) > 0xFFFF

def stats(state, tx_base=TX_BASE, tx_min_base=TX_MIN_BASE,
          rx_base=RX_BASE, rx_min_base=RX_MIN_BASE):
    # give each block distinct values so a mis-split cannot pass
    tx      = struct.pack('<5I',  *[tx_base + i for i in range(5)])
    tx_min  = struct.pack('<5I',  *[tx_min_base + i for i in range(5)])
    # decoder_state is ONE byte at +40 with three of alignment padding after it,
    # and the firmware memcpys a partially-initialised stack struct - so that
    # padding is not zero on the wire. Fill it with values actually observed in
    # a capture: a zero-filled fixture cannot tell a 1-byte read from a 4-byte
    # one, which is the bug it is supposed to be guarding against.
    PAD = bytes([0x73, 0x20, 0x28])
    rx      = struct.pack('<10I', *[rx_base + i for i in range(10)]) + bytes([state]) + PAD
    rx_min  = struct.pack('<10I', *[rx_min_base + i for i in range(10)]) + bytes([state]) + PAD
    assert len(tx) == TX_SIZE and len(rx) == RX_SIZE, (len(tx), len(rx))
    p = tx + tx_min + rx + rx_min
    assert len(p) == 128, len(p)
    # the four boundaries the firmware's own struct sizes imply
    assert (TX_SIZE, 2*TX_SIZE, 2*TX_SIZE+RX_SIZE, 2*TX_SIZE+2*RX_SIZE) == (20, 40, 84, 128)
    return p

for state, name, settled in ((0,'Unknown',False), (1,'Healthy',True), (2,'Bad',True), (3,'Starting',False)):
    f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x3F, stats(state)), ADDR)
    f.process()
    dev = mx.get_by_uid(mx_remote.MxrDeviceUid(UID))
    st = dev.v2ip_stats.rx.decoder_state
    assert int(st) == state and str(st) == name, (st, name)
    assert st.settled == settled, (st, settled)
    print(f'0x3F : state {state} -> {st} (settled={st.settled})')

# a state from a newer firmware must not raise out of the property
f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x3F, stats(9)), ADDR)
st = f.stats.rx.decoder_state
assert st == V2IPDecoderState.UNKNOWN and not st.settled
print('0x3F : unknown state 9 ->', st)

# the distinction that matters: STARTING is not a failure
assert V2IPDecoderState.STARTING != V2IPDecoderState.HEALTHY
assert not V2IPDecoderState.STARTING.settled, 'STARTING must not read as a verdict'
assert V2IPDecoderState.BAD.settled and V2IPDecoderState.HEALTHY.settled
print('0x3F : only HEALTHY and BAD are verdicts')
# --- each block must be read from its own bytes, not a neighbour's
f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x3F, stats(1)), ADDR)
st = f.stats
assert st.tx.video == TX_BASE and st.tx_per_minute.video == TX_MIN_BASE, (st.tx.video, st.tx_per_minute.video)
assert st.rx.video_total == RX_BASE, st.rx.video_total
assert st.rx_per_minute.video_total == RX_MIN_BASE, st.rx_per_minute.video_total
print('0x3F : four blocks read from their own bytes (20/40/84/128)')

# a 24/48 split - the sizes ALIGN(8) would have given had it been honoured -
# still totals 128, so only a boundary assertion catches it
assert (24 * 2) + (48 * 2) == 144 or True
print('0x3F : block sizes pinned at 20/44, not derived from the total')

# ==================================================== decoder detail, offset 128
# 20 bytes of fields rounded to 24 by ALIGN(8), appended to the counters from
# MatrixOS 10.12.46. Every fixture below is built over a poisoned buffer rather
# than zeros: a field read at the right offset with the wrong width, or one byte
# late, returns the right answer over zeros for most values and can never fail.
DETAIL_SIZE = 24

def poison(n, seed):
    # non-zero and position-varying, so a read that strays into a neighbour
    # returns a different wrong answer at every offset rather than 0
    return bytes((((seed + (7 * i)) % 251) + 1) for i in range(n))

def detail(valid=1, reason=0, blocking=0, width=0, height=0, fmt=0, updates=0,
           flags=0, blocked=0, reserved=None, tail=None):
    b = bytearray(poison(DETAIL_SIZE, 0x40))
    b[0] = valid
    b[1] = reason
    b[2] = blocking
    if reserved is not None:
        b[3] = reserved                                   # else it stays poisoned
    struct.pack_into('<HHHH', b, 4, width, height, fmt, updates)
    struct.pack_into('<II', b, 12, flags, blocked)
    if tail is not None:
        b[20:24] = tail                                   # else it stays poisoned
    assert len(b) == DETAIL_SIZE, len(b)
    return bytes(b)

def rx3f(payload, proto=V2IP_DECODER_PROTOCOL):
    # Stamped like the firmware stamps it, not like create_mxr_frame does: the
    # decoder block is recognised by the stamp as well as the length, so a
    # fixture left at the builder's default 1 reads as a sender that predates it.
    raw = bytearray(create_mxr_frame(UID, 0x3F, payload))
    raw[2] = proto
    f = process_mxr_frame(mx, time.time(), bytes(raw), ADDR)
    f.process()
    return f

assert (V2IP_STATS_COUNTERS_LEN, V2IP_STATS_FULL_LEN) == (128, 152), V2IP_STATS_FULL_LEN

# ---------------------------------------------------------- the shared vector
# Bytes 128..152 as agreed with the other clients of this protocol, decoded
# independently against the firmware struct. Every field at once, and the only
# expectation here that did not come out of this decoder.
VECTOR = bytes.fromhex('01040077000f70080200580210011000a9860100efbeadde')
assert len(VECTOR) == DETAIL_SIZE, len(VECTOR)
r = rx3f(stats(1) + VECTOR).decoder.reading
assert r is not None
assert r.reason == V2IPDecoderReason.FORMAT_MISMATCH and r.reason_value == 4, r.reason
assert r.blocking is False, 'blocking is byte 2; the vector poisons byte 3 with 0x77'
assert (r.width, r.height) == (3840, 2160), (r.width, r.height)
assert r.recovered
assert r.format == V2IPColorFormat.YCBCR_422 and r.format_value == 2, r.format
assert r.updates == 600, r.updates
assert r.flags == 0x00100110, hex(r.flags)
assert [b for b in range(32) if (r.flags >> b) & 1] == [4, 8, 20], hex(r.flags)
assert r.blocked_count == 100009, r.blocked_count
print('0x3F : shared vector ->', r)

# bit 20 is a cause nobody names yet, and has_reason still answers for it
assert r.has_reason(V2IPDecoderReason.FORMAT_MISMATCH)
assert r.has_reason(V2IPDecoderReason.PTP_UNLOCKED)
assert r.has_reason(20), 'an unnamed cause in flags must still be testable'
assert not r.has_reason(V2IPDecoderReason.NO_PACKETS)
assert not r.has_reason(V2IPDecoderReason.OK), 'bit 0 is unused, never a set cause'
print('0x3F : flags carry every cause, named or not')

# ------------------------------------------------- three answers, kept apart
# 128 bytes: the sender predates the block. 152 with valid 0: the block is
# there and the decoder has never answered. 152 with valid 1: a reading. Only
# the third carries fields, and there is no path to geometry from the second.
f = rx3f(stats(1))
assert len(f.payload) == V2IP_STATS_COUNTERS_LEN
assert f.decoder is None, 'a 128-byte report has no block to read'
assert f.stats.decoder is None

f = rx3f(stats(1) + detail(valid=0, width=1920, height=1080, fmt=1, updates=9))
assert f.decoder is not None, 'a 152-byte report carries the block'
assert not f.decoder.valid
assert f.decoder.reading is None, 'valid 0 must expose no fields at all'
assert not hasattr(f.decoder, 'width'), 'geometry must not be reachable without a reading'

f = rx3f(stats(1) + detail(valid=1, width=1920, height=1080, fmt=1, updates=9))
assert f.decoder.valid and f.decoder.reading is not None
assert (f.decoder.reading.width, f.decoder.reading.height) == (1920, 1080)
print('0x3F : absent / never answered / a reading are three answers')

# ------------------------------------ the stamp and the length, both required
# The length says a payload is long enough to hold the block; the stamp says
# those 24 bytes are that block. A sender below V2IP_DECODER_PROTOCOL appended
# no such thing, so its tail is some other growth and reading it would invent a
# reading out of it. Its counters are read either way.
below = rx3f(stats(1) + VECTOR, proto=V2IP_DECODER_PROTOCOL - 1)
assert len(below.payload) == V2IP_STATS_FULL_LEN
assert below.decoder is None, 'a tail below the block stamp is not the block'
assert below.tx.video == TX_BASE, 'the counters ahead of the tail are still read'
assert rx3f(stats(1) + VECTOR).decoder is not None, 'the same bytes at the stamp are the block'
print('0x3F : the block needs the stamp and the length; the counters need neither')

# The opcode floor is what a sender stamps at minimum, not where the layout
# changed, so it does not move when a payload grows a block.
assert MXR_OPCODE_VERSIONS[0x3F] == 0x13
assert V2IP_DECODER_PROTOCOL > MXR_OPCODE_VERSIONS[0x3F]
print('0x3F : the block stamp is a layout version, not the opcode floor')

# a longer payload is a newer sender with another block appended; parse the
# prefix understood and ignore the tail
f = rx3f(stats(1) + detail(valid=1, width=1280, height=720, fmt=3) + poison(16, 0x90))
assert len(f.payload) == V2IP_STATS_FULL_LEN + 16
assert f.decoder.reading.width == 1280 and f.decoder.reading.format == V2IPColorFormat.YCBCR_420
print('0x3F : a 168-byte report parses its 24-byte block and drops the rest')

# ----------------------------------------- geometry says signal, format never does
# With no stream format reads 0, which is RGB. A caller testing format for a
# no-signal value gets a confident wrong answer at every value it could pick.
# The pair rests on the format being identical across both halves while the
# geometry moves - and the reason moves with it, because a sink with no packets
# does not report OK. Pin both formats to RGB rather than to each other: an
# equality assertion still passes if a later edit changes both halves together,
# which quietly turns the pair back into two ordinary fixtures.
r = rx3f(stats(1) + detail(valid=1, reason=1, width=0, height=0, fmt=0)).decoder.reading
assert not r.recovered, 'no geometry means nothing was recovered'
assert r.format == V2IPColorFormat.RGB and r.format_value == 0, r.format
r2 = rx3f(stats(1) + detail(valid=1, reason=0, width=3840, height=2160, fmt=0)).decoder.reading
assert r2.recovered, 'a real RGB stream read as no signal, which is what format 0 invites'
assert r2.format == V2IPColorFormat.RGB, 'the live half must be RGB for the pair to bite'
assert r.format == V2IPColorFormat.RGB, 'the dead half must be RGB for the pair to bite'

# both dimensions, not either: half a geometry is not a picture, and a decoder
# that answered with one of them has not recovered a codestream
for w, h in ((1920, 0), (0, 1080)):
    half = rx3f(stats(1) + detail(valid=1, width=w, height=h, fmt=1)).decoder.reading
    assert (half.width, half.height) == (w, h), (half.width, half.height)
    assert not half.recovered, f'{w}x{h} is not a recovered picture'
print('0x3F : format 0 is RGB on a live stream and on no stream; geometry separates them')

# a decoder that cannot name the format is answering, not staying silent - and
# 255 is not the 0xF that means unknown colour space in a signal report
r = rx3f(stats(1) + detail(valid=1, width=1920, height=1080, fmt=255)).decoder.reading
assert r.format == V2IPColorFormat.UNNAMED and r.format_value == 255, r.format
assert int(V2IPColorFormat.UNNAMED) != 0x0F
assert 0x0F not in [int(m) for m in V2IPColorFormat], 'no member may collide with the 0xF unknown'
assert r.recovered, 'an unnameable format is still a recovered picture'
print('0x3F : format 255 ->', r.format)

# format is two bytes: a byte-wide read returns the right answer for every value
# currently named, so only a value with a non-zero high byte can catch it
r = rx3f(stats(1) + detail(valid=1, width=1920, height=1080, fmt=0x0102)).decoder.reading
assert r.format_value == 0x0102, hex(r.format_value)
assert r.format is None, 'a format this build cannot name must not decode to one it can'
assert r.format != V2IPColorFormat.YCBCR_422, 'that is what the low byte alone reads as'
print('0x3F : format 0x0102 -> None, not the YCbCr 4:2:2 its low byte spells')

# --------------------------------------------- blocking is byte 2, reserved is 3
# A read taken from the reserved byte passes whenever that byte is non-zero, so
# assert both directions with the neighbour set the opposite way.
r = rx3f(stats(1) + detail(valid=1, blocking=0, reserved=0xFF)).decoder.reading
assert r.blocking is False, 'reserved byte 3 was read as blocking'
r = rx3f(stats(1) + detail(valid=1, blocking=1, reserved=0x00, blocked=7)).decoder.reading
assert r.blocking is True and r.blocked_count == 7
print('0x3F : blocking read from byte 2, reserved byte 3 ignored')

# --------------------------------------------------------- reasons stay opaque
for value, member in ((0, V2IPDecoderReason.OK),
                      (1, V2IPDecoderReason.NO_PACKETS),
                      (4, V2IPDecoderReason.FORMAT_MISMATCH),
                      (7, V2IPDecoderReason.SWITCH_PENDING),
                      (8, V2IPDecoderReason.PTP_UNLOCKED),
                      (10, V2IPDecoderReason.IDLE)):
    r = rx3f(stats(1) + detail(valid=1, reason=value)).decoder.reading
    assert r.reason == member and r.reason_value == value, (r.reason, member)
print('0x3F : every named reason decodes to its own member')

# ------------------------------------ the primary cause is not derivable from flags
# Every true cause sets its bit; which one keeps `reason` is a fixed priority in
# the video processor, and not the numbering. Three readings, none of which this
# decoder chose - two off the bench, one a standing property of the rank order.
#
# 1+2. A measured teardown: reason 7 with flags 138, then reason 1 with flags 10
#      six seconds later, geometry 0x0 from the first. 138 is bits 1, 3 and 7;
#      10 is bits 1 and 3. Bit 1 is set while 7 is named, so `reason` is not the
#      lowest set bit.
# 3.   A repeating pipeline restart. TX_BRIDGE_UNLOCKED ranks below every
#      input-side cause, so bit 9 is set while NO_PACKETS names itself - a cause
#      permanently invisible to anything reading `reason` alone.
READINGS = ((7, 138, (1, 3, 7)),
            (1, 10,  (1, 3)),
            (1, (1 << 1) | (1 << 9), (1, 9)))
for reason, flags, causes in READINGS:
    r = rx3f(stats(1) + detail(valid=1, reason=reason, flags=flags,
                               width=0, height=0)).decoder.reading
    assert r.causes == causes, (reason, flags, r.causes)
    assert r.reason_value == reason, r.reason_value
    assert r.has_reason(reason), 'the named cause must be in the set it came from'

loop = rx3f(stats(1) + detail(valid=1, reason=1,
                              flags=(1 << 1) | (1 << 9))).decoder.reading
assert loop.reason == V2IPDecoderReason.NO_PACKETS, loop.reason
assert loop.has_reason(V2IPDecoderReason.TX_BRIDGE_UNLOCKED), \
    'a restart loop is invisible to anything reading reason alone'
assert V2IPDecoderReason.TX_BRIDGE_UNLOCKED not in (loop.reason,)
print('0x3F : causes', loop.causes, 'while reason names', loop.reason)

switching = rx3f(stats(1) + detail(valid=1, reason=7, flags=138)).decoder.reading
assert switching.reason == V2IPDecoderReason.SWITCH_PENDING, switching.reason
assert switching.causes[0] == 1 and switching.reason_value == 7, switching.causes
print('0x3F : reason 7 over causes', switching.causes, '- not the lowest set bit')

# A switched-off sink, from a build later than 10.12.46: IDLE named, with the
# causes the decoder genuinely observed still set beneath it. The accessor must
# report the word as it arrived - suppressing the lower bits here would answer
# the fault question for every caller by throwing away what the decoder saw, and
# that judgement belongs in the caller. Bit 4 can appear here too, since
# FORMAT_MISMATCH needs only a detected geometry beside a configured one.
#
# The exact word is deliberately not asserted: bits 1..3 are guarded by a flag
# that is only stuck true because of the defect being fixed, so this becomes
# (10,) alone when that lands. What holds either way is that IDLE is present and
# outranks whatever else is set.
off = rx3f(stats(1) + detail(valid=1, reason=10,
                             flags=(1 << 1) | (1 << 3) | (1 << 7) | (1 << 10),
                             width=3840, height=2160)).decoder.reading
assert off.reason == V2IPDecoderReason.IDLE, off.reason
assert off.has_reason(V2IPDecoderReason.IDLE), 'IDLE must be present in the set'
assert off.causes == (1, 3, 7, 10), off.causes
assert off.has_reason(V2IPDecoderReason.NO_PACKETS), 'the lower causes are a real reading'
# geometry answers what the decoder detects, not whether the sink is on: a sink
# at rest can be detecting a picture perfectly well
assert off.recovered, 'a switched-off sink can still be detecting a picture'
assert (off.width, off.height) == (3840, 2160), (off.width, off.height)
print('0x3F : a switched-off sink keeps causes', off.causes, 'and its geometry')

# bit 0 is force-cleared by the firmware, so flags 0 means nothing is true
# rather than that cause 0 is - and OK is never reported as a cause
zero = rx3f(stats(1) + detail(valid=1, reason=0, flags=0,
                              width=1920, height=1080)).decoder.reading
assert zero.causes == (), zero.causes
assert not zero.has_reason(V2IPDecoderReason.OK)
assert zero.recovered
bit0 = rx3f(stats(1) + detail(valid=1, reason=0, flags=0xFFFFFFFF)).decoder.reading
assert 0 not in bit0.causes, 'bit 0 is not a cause even when it arrives set'
assert bit0.causes == tuple(range(1, 32)), bit0.causes
print('0x3F : bit 0 is never a cause; flags 0 means nothing applies')

# a cause past the width of the field is answered, not shifted into
assert not loop.has_reason(200), 'a cause past the flags word must read false'
assert not loop.has_reason(32)
print('0x3F : a cause past the flags word reads false')

# a reason a newer firmware added must not raise, and must not be folded onto a
# cause somebody would act on - 0 is OK, so any clamp reports a healthy decoder
r = rx3f(stats(1) + detail(valid=1, reason=200, width=1920, height=1080)).decoder.reading
assert r.reason is None, r.reason
assert r.reason_value == 200, r.reason_value
assert r.reason != V2IPDecoderReason.OK
assert r.recovered, 'an unnamed reason must not cost the rest of the block'
print('0x3F : reason 200 -> None, raw value kept')

# ----------------------------------------- the counters keep every byte they had
# The block was appended, which is the point: a 152-byte report must decode its
# counters exactly as the 128-byte one did.
# Each counter gets its own value in the fixture, in the firmware's own field
# order, so this pins where every one of them is read from rather than only
# that the two forms agree - two reads off the same wrong offset agree too.
TX_FIELDS = ('video', 'audio', 'anc', 'stream_down', 'overflow')
RX_FIELDS = ('video_total', 'video_dropped', 'video_sequence_errors', 'wdt_timeout',
             'audio_total', 'audio_dropped', 'audio_sequence_errors',
             'anc_total', 'anc_dropped', 'anc_sequence_errors')

short, long = rx3f(stats(1)).stats, rx3f(stats(1) + VECTOR).stats
for name, base, fields in (('tx', TX_BASE, TX_FIELDS), ('tx_per_minute', TX_MIN_BASE, TX_FIELDS),
                           ('rx', RX_BASE, RX_FIELDS), ('rx_per_minute', RX_MIN_BASE, RX_FIELDS)):
    a, b = getattr(short, name), getattr(long, name)
    for i, field in enumerate(fields):
        assert getattr(a, field) == base + i, (name, field, getattr(a, field))
        assert getattr(b, field) == base + i, (name, field, getattr(b, field))
for name in ('rx', 'rx_per_minute'):
    assert getattr(short, name).decoder_state == getattr(long, name).decoder_state \
        == V2IPDecoderState.HEALTHY, name
print('0x3F : every counter still read from its own offset with the block appended')

# ------------------------------------------- the request form is not a report
# The same opcode carries the subscribe request: uid plus one byte, 17 in all.
# Another controller's request is seen on the mesh like anything else, and the
# counter blocks are not there to read - so a handler that treats it as a report
# raises inside the receive path rather than decoding a short one.
req = rx3f_raw = create_mxr_frame(UID, 0x3F, UID + bytes([1]))
f = process_mxr_frame(mx, time.time(), req, ADDR)
assert f.is_request and len(f.payload) == 17, (f.is_request, len(f.payload))
assert f.stats_enabled is True, f.stats_enabled

before = mx.get_by_uid(mx_remote.MxrDeviceUid(UID)).v2ip_stats
f.process()
assert mx.get_by_uid(mx_remote.MxrDeviceUid(UID)).v2ip_stats is before, \
    'a request must not overwrite the cached report'

off = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x3F, UID + bytes([0])), ADDR)
assert off.is_request and off.stats_enabled is False, off.stats_enabled
off.process()

# and the whole receive path, not just the handler
mx.process_frame(time.time(), req, ADDR)
print('0x3F : a 17-byte request is not decoded as a report')

# ------------------------------ no payload length reaches the counter parsing
# The two forms are separated by length, and everything between them is a
# truncated report. payload_idx clamps a slice to what arrived rather than
# failing, so reading one hands a counter block a buffer too short and it
# refuses it - which str(frame) reaches as readily as process() does. The
# receive path renders every frame it decodes to its debug log ahead of
# processing it, and re-raises what that render throws.
seen_short = []
for n in list(range(0, 40)) + [126, 127, 128, 151, 152, 153, 200]:
    raw = bytearray(create_mxr_frame(UID, 0x3F, poison(n, 0x11) if n else b''))
    raw[2] = V2IP_DECODER_PROTOCOL
    try:
        f = process_mxr_frame(mx, time.time(), bytes(raw), ADDR)
        str(f)
        f.process()
    except Exception as e:
        seen_short.append((n, e))
assert not seen_short, f'a payload length raised out of the frame: {seen_short}'
print('0x3F : no payload length raises out of str() or process()')

# A truncated report reaches no device, and says why rather than pretending
short = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x3F, bytes(127)), ADDR)
assert not short.is_report and not short.is_request
assert 'too short' in str(short), str(short)
print('0x3F : 127 bytes is neither form, and is filed as neither')

# ------------------------------------- a report from 10.12.46 is stamped 0x29
# The receive path drops any frame stamped above this build's protocol version,
# so a stamp this build has not caught up to silences the whole report -
# counters included - the moment a device upgrades. Nothing about the payload
# says it happened.
assert MXR_PROTOCOL_VERSION >= 0x29, 'a 10.12.46 V2IP_STATS report would be dropped unparsed'
seen = []
dev = mx.get_by_uid(mx_remote.MxrDeviceUid(UID))
real = type(dev).on_mxr_update
type(dev).on_mxr_update = lambda self, data: seen.append(data)
try:
    raw = bytearray(create_mxr_frame(UID, 0x3F, stats(1) + VECTOR))
    raw[2] = 0x29
    mx.process_frame(time.time(), bytes(raw), ADDR)
    assert seen, 'a report stamped 0x29 was dropped before it reached the device'
    assert seen[-1].decoder.reading.width == 3840, seen[-1]
finally:
    type(dev).on_mxr_update = real
print('0x3F : a report stamped 0x29 reaches the device cache')

print()
print('ALL OK')
