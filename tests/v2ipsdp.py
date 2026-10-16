######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''What a OneIP output plays from a session description (0x52), and handing it
one.

The report is composed from its declaration with every field distinct, so a
field read at a neighbour's offset shows, and its strings fill their fields to
the last byte, which the output keeps for the terminator.

Commands are asserted in both directions: every refusal sits next to a command
that goes out.
'''

import asyncio, os, struct, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import DeviceFeature, MxrDeviceUid
from mx_remote.proto.Constants import (ONEIP_SDP_MAX, OneIPSdpClockMode, OneIPSdpClockState, OneIPSdpEncoding,
                                       OneIPSdpFlag, OneIPSdpMediaClock, OneIPSdpRefClock)
from mx_remote.proto.Factory import create_mxr_frame

ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False)
mx._uid = bytes(range(0x20, 0x30))
sent = []
mx.transmit = lambda data: (sent.append(bytes(data)), len(data))[1]

def uid(n):
    return bytes([n]) * 16

def name(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def rx(sender, opcode, payload=b'', protocol=0x2E):
    frame = bytearray(create_mxr_frame(sender, opcode, payload))
    frame[2] = protocol
    mx.process_frame(0.0, bytes(frame), ADDR)

def hello(sender, protocol, features):
    rx(sender, 0x00, struct.pack('<H', protocol) + name('ONEIP') + name('P8SN%08d' % sender[0])
                   + name('5.0.0') + struct.pack('<I', int(features)), protocol=0x01)
    return mx.get_by_uid(MxrDeviceUid(sender))

def call(coro):
    return asyncio.run(coro)

def report(sender):
    status = (bytes([int(OneIPSdpFlag.ACTIVE | OneIPSdpFlag.CLOCK), 2, 2, 8, 97, 1, 1, 1, 3, 0xA5])
              + struct.pack('<HII', 5004, 48000, 0x01020304) + bytes([239, 69, 1, 2])
              + b'S' * 48 + b'L' * 8)
    assert len(status) == 80, len(status)
    return sender + bytes([0, 0xA5, 0xA5, 0xA5]) + status

# ------------------------------------------------------------------- reading
out = hello(uid(0x10), 0x2E, DeviceFeature.ONEIP_SINK)
rx(uid(0x10), 0x52, report(uid(0x10)))
s = out.oneip_sink_sdp
assert s is not None and s.active, s
assert (s.flags, s.screen, s.channels, s.payload_type) == (OneIPSdpFlag.ACTIVE | OneIPSdpFlag.CLOCK, 2, 8, 97), s
assert (s.encoding, s.media_clock, s.ref_clock) == (OneIPSdpEncoding.L24, OneIPSdpMediaClock.DIRECT, OneIPSdpRefClock.PTP)
assert (s.clock_mode, s.clock_state) == (OneIPSdpClockMode.PTP, OneIPSdpClockState.TIMED)
assert (s.port, s.rate_hz, s.media_clock_offset, s.group) == (5004, 48000, 0x01020304, '239.69.1.2'), s
assert (s.name, s.layout) == ('S' * 47, 'L' * 7), 'the last byte of each field is the terminator'
print('decode      :', s)

# A command addressed to an output is not its report, and a report grows at the
# back, so a short one reads as far as it goes.
ctrl = hello(uid(0x11), 0x2E, DeviceFeature.ONEIP_SINK)
rx(uid(0x11), 0x52, uid(0x10) + bytes([2, 0, 0, 0]))
assert ctrl.oneip_sink_sdp is None and out.oneip_sink_sdp == s, 'a command was read as a report'
rx(uid(0x10), 0x52, report(uid(0x10))[:20 + 16])
assert out.oneip_sink_sdp.port == 5004 and out.oneip_sink_sdp.name == '', out.oneip_sink_sdp
print('ignored     : a command is not a report; a short report reads as far as it goes')

# ------------------------------------------------------------------- writing
sent.clear()
text = 'v=0\r\n' + 'a=x\r\n' * 300
assert len(text) > 1024
assert call(out.play_oneip_sdp(text)) is True
assert len(sent) == 2, 'pages of up to 1 KB'
for i, frame in enumerate(sent):
    p = frame[24:]
    assert int.from_bytes(frame[20:22], 'little') == 0x52 and frame[2] == 0x2E
    assert p[:20] == uid(0x10) + bytes([1, 0, 0, 0]), p[:20].hex()
    total, offset, length = struct.unpack_from('<HHH', p, 20)
    assert (total, offset) == (len(text), i * 1024) and p[26:28] == bytes(2)
    assert p[28:] == text.encode()[offset:offset + 1024] and length == len(p) - 28
for coro, kind, value in ((out.stop_oneip_sdp(), 2, 0), (out.set_oneip_sdp_screen(5), 3, 5),
                          (out.request_oneip_sink_sdp(), 4, 0)):
    sent.clear()
    assert call(coro) is True, kind
    assert sent[-1][24:] == uid(0x10) + bytes([kind, value, 0, 0]), sent[-1][24:].hex()
print('write       : 1 KB pages, and stop, screen and request')

def refused(coro, why):
    n = len(sent)
    assert call(coro) is False, why
    assert len(sent) == n, f'{why}: refused, but transmitted anyway'
refused(out.play_oneip_sdp(''), 'an empty description')
assert call(out.play_oneip_sdp('x' * ONEIP_SDP_MAX)) is True
refused(out.play_oneip_sdp('x' * (ONEIP_SDP_MAX + 1)), 'a description an output drops after its last page')
src = hello(uid(0x12), 0x2E, DeviceFeature.ONEIP_SOURCE)
refused(src.play_oneip_sdp('v=0'), 'a device that is not a OneIP output')
refused(src.stop_oneip_sdp(), 'a device that is not a OneIP output')
old = hello(uid(0x13), 0x2D, DeviceFeature.ONEIP_SINK)
refused(old.play_oneip_sdp('v=0'), 'an output below 0x2E')
refused(old.request_oneip_sink_sdp(), 'an output below 0x2E')
refused(out.set_oneip_sdp_screen(256), 'a screen past the field')
print('refusals    : nothing an output ignores is sent')

print('ALL OK')
