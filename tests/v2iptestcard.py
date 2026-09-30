######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''A V2IP sink's test pattern, tone and lip-sync flash (0x4E).

The frame is composed from the module's declaration rather than captured: no
unit on hand runs the module. Every value is distinct and wider than a byte
where its field is, the colour's unused top byte and the reserved bytes are
poisoned, so a read at a neighbour's offset or at the wrong width shows.

Commands are asserted in both directions: every refusal sits next to a write
that goes out, to a sink whose processor reports the feature.
'''

import asyncio, os, struct, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import (DeviceFeature, MxrDeviceUid, V2IPTestcard, V2IPTestSync, V2IPTestTone,
                       V2IPTestPattern as P, V2IPToneMode as T, V2IPTestcardFlag as F)
from mx_remote.proto.Constants import V2IPFpgaFeature
from mx_remote.proto.Factory import create_mxr_frame, process_mxr_frame

ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False)
mx._uid = bytes(range(0x20, 0x30))

def uid(n):
    return bytes([n]) * 16

def name(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def rx(sender, opcode, payload=b'', protocol=0x2B):
    frame = bytearray(create_mxr_frame(sender, opcode, payload))
    frame[2] = protocol
    mx.process_frame(0.0, bytes(frame), ADDR)

def sink(n, fpga, protocol=0x2B):
    '''A sink on protocol whose video processor reports fpga, 0 for nothing yet.'''
    rx(uid(n), 0x00, struct.pack('<H', protocol) + name('ONEIP') + name('P8SN12345678')
                   + name('5.0.0') + struct.pack('<I', int(DeviceFeature.V2IP_SINK)), protocol=protocol)
    cfg = (uid(n) + bytes(24) + bytes([0xFF, 0, 0, 0]) + bytes(4) + bytes(72)   # processor word at 120
           + struct.pack('<Q', int(fpga)))
    rx(uid(n), 0x3C, cfg, protocol=0x11)
    return mx.get_by_uid(MxrDeviceUid(uid(n)))

def testcard_frame(target, kind):
    p = bytearray([0xA5] * 56)
    p[:16] = target
    p[16] = kind
    p[17] = 0b0010_1011
    p[18] = 2
    p[19] = 3
    p[20:24] = struct.pack('<I', 0xAB123456)
    p[24:26] = struct.pack('<H', 0x0457)
    p[26] = (-23) & 0xFF
    p[27] = 6
    p[28:32] = struct.pack('<I', 96000)
    p[32:34] = struct.pack('<H', 0x0312)
    p[34:36] = struct.pack('<H', 0x0211)
    p[36:40] = struct.pack('<I', 0x00ABCDEF)
    p[40:42] = struct.pack('<H', 0x0765)
    p[44:48] = struct.pack('<I', 0x11223344)
    p[48:52] = struct.pack('<I', 0x55667788)
    p[52:56] = struct.pack('<I', 0x99AABBCC)
    return bytes(p)

# ------------------------------------------------------------------- reading

# Answered to the device that asked, but heard by everyone, and recorded against
# the sink the frame names.
s = sink(0x10, V2IPFpgaFeature.SINK_TEST_PATTERN)
rx(uid(0x10), 0x4E, testcard_frame(uid(0x10), 2))
tc = s.v2ip_testcard
assert tc == V2IPTestcard(
    flags=F(0b0010_1011), pattern=P.FLAT, colour=0x123456,
    tone=V2IPTestTone(mode=T.LINEUP, freq=0x0457, level=-23, channels=6, rate=96000),
    sync=V2IPTestSync(period=0x0312, lead=0x0211, offset=0x00ABCDEF, beep_ms=0x0765),
    frames=0x11223344, periods=0x55667788, marks=0x99AABBCC), tc
assert tc.supported and (F.SYNC_PENDING in tc.flags)
print('decode      :', tc)

# A request or a change addressed to a sink is not its report, and a frame
# shorter than the whole struct is nothing.
s = sink(0x11, V2IPFpgaFeature.SINK_TEST_PATTERN)
rx(uid(0x10), 0x4E, testcard_frame(uid(0x11), 0))
rx(uid(0x10), 0x4E, testcard_frame(uid(0x11), 1))
rx(uid(0x11), 0x4E, testcard_frame(uid(0x11), 2)[:55])
assert s.v2ip_testcard is None, s.v2ip_testcard
# process_frame() swallows what a handler raises, so decode the short one here.
short = process_mxr_frame(mx, 0.0, create_mxr_frame(uid(0x11), 0x4E, testcard_frame(uid(0x11), 2)[:55]), ADDR)
assert short.testcard is None, 'a report cut short'
rx(uid(0x11), 0x4E, testcard_frame(uid(0x11), 2))
assert s.v2ip_testcard is not None, 'a whole report'
print('ignored     : request, change, and a report cut short')

# --------------------------------------------------------------------- writing

sent = []
mx.transmit = lambda data: (sent.append(data), len(data))[1]

def call(coro):
    return asyncio.new_event_loop().run_until_complete(coro)

def refused(coro, why):
    n = len(sent)
    assert call(coro) is False, why
    assert len(sent) == n, f'{why}: refused, but transmitted anyway'

def payload(target):
    frame = sent[-1]
    assert int.from_bytes(frame[20:22], 'little') == 0x4E
    assert frame[2] == 0x2B, f'stamped {frame[2]:#x}'
    p = frame[24:]
    assert len(p) == 56, len(p)
    assert p[:16] == target
    return p

# Each write puts its part at its own offsets behind its own bit, and leaves
# every other byte zero.
s = sink(0x12, V2IPFpgaFeature.SINK_TEST_PATTERN)
assert call(s.request_v2ip_testcard()) is True
assert payload(uid(0x12))[16:] == bytes(40), 'a request carries only the uid'

assert call(s.set_v2ip_test_pattern(P.GRID, 0x123456)) is True
assert payload(uid(0x12))[16:] == bytes([1, 1, 4, 0, 0x56, 0x34, 0x12, 0]) + bytes(32), 'the pattern'

assert call(s.set_v2ip_test_tone(V2IPTestTone(mode=T.CONTINUOUS, freq=0x0457, level=-23,
                                             channels=6, rate=48000))) is True
p = payload(uid(0x12))
assert p[16:20] == bytes([1, 2, 0, 1]), p[16:20].hex()
assert p[20:32] == bytes([0, 0, 0, 0, 0x57, 0x04, 0xE9, 6, 0x80, 0xBB, 0, 0]), p[20:32].hex()
assert p[32:] == bytes(24), 'the tone'

assert call(s.set_v2ip_test_sync(V2IPTestSync(period=0x0312, lead=0x0211, offset=0x00ABCDEF,
                                             beep_ms=0x0765))) is True
p = payload(uid(0x12))
assert p[16:18] == bytes([1, 4]) and p[18:32] == bytes(14), p[16:32].hex()
assert p[32:42] == bytes([0x12, 0x03, 0x11, 0x02, 0xEF, 0xCD, 0xAB, 0x00, 0x65, 0x07]), 'the lip-sync'
assert p[42:] == bytes(14), 'reserved and counters'
assert s.v2ip_testcard is None, 'a write was cached'
print('write       : each part behind its own bit, the rest zero')

# A write the sink could not take, and a sink that cannot draw a test card, are
# refused before anything is sent.
without = sink(0x13, V2IPFpgaFeature.SINK_STATE)
unreported = sink(0x14, 0)
old = sink(0x15, V2IPFpgaFeature.SINK_TEST_PATTERN, protocol=0x2A)
refused(s.set_v2ip_test_pattern(7, 0), 'a pattern this library does not name')
refused(s.set_v2ip_test_pattern(P.FLAT, 0x1000000), 'a colour wider than 24 bits')
tone = V2IPTestTone(mode=T.LINEUP, freq=1000, level=0, channels=2, rate=48000)
for bad in (dict(mode=5), dict(freq=19), dict(freq=20001), dict(level=-61), dict(level=1),
            dict(channels=1), dict(channels=9), dict(rate=32000)):
    refused(s.set_v2ip_test_tone(V2IPTestTone(**{**tone.__dict__, **bad})), f'tone {bad}')
sync = V2IPTestSync(period=10, lead=9, offset=0xFFFFFF, beep_ms=10000)
for bad in (dict(lead=10), dict(period=0), dict(offset=0x1000000), dict(beep_ms=0), dict(beep_ms=10001)):
    refused(s.set_v2ip_test_sync(V2IPTestSync(**{**sync.__dict__, **bad})), f'sync {bad}')
refused(without.request_v2ip_testcard(), 'a sink without the feature')
refused(unreported.request_v2ip_testcard(), 'a sink whose processor reported nothing')
refused(old.request_v2ip_testcard(), 'a sink below the opcode\'s protocol')

# The edges that are taken, and a tone turned off whatever it holds.
n = len(sent)
assert call(s.set_v2ip_test_tone(tone)) is True, 'a two-channel line-up'
assert call(s.set_v2ip_test_tone(V2IPTestTone(**{**tone.__dict__, 'freq': 20, 'level': -60,
                                                 'channels': 8, 'rate': 96000}))) is True, 'the low edges'
assert call(s.set_v2ip_test_tone(V2IPTestTone())) is True, 'off'
assert call(s.set_v2ip_test_sync(sync)) is True, 'the high edges'
assert call(s.set_v2ip_test_sync(V2IPTestSync(beep_ms=1))) is True, 'no marks at all'
assert call(s.set_v2ip_test_pattern(P.CARD, 0xFFFFFF)) is True, 'the last pattern and the widest colour'
assert len(sent) == n + 6
print('refusals    : nothing a sink ignores is sent')

print('ALL OK')
