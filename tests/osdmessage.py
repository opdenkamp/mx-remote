######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''The message on a unit's output, carried by the overlay sync opcode (0x53)
as kinds 4 to 6: asked for, written, and the unit's answer.

Every refusal sits next to a command that goes out.
'''

import asyncio, os, struct, sys, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import DeviceFeature, MxrDeviceUid, OsdMessage
from mx_remote.proto.Constants import OSD_MESSAGE_TEXT_MAX, OsdMessageFlag as F, OsdMessagePriority as P
from mx_remote.proto.Factory import create_mxr_frame

ADDR = ('192.0.2.9', 8812)

class Watching(mx_remote.MxrCallbacks):
    def __init__(self):
        self.messages = []
    def on_osd_message_changed(self, dev, message):
        self.messages.append((dev, message))

seen = Watching()
mx = mx_remote.Remote(open_connection=False, callbacks=seen)
mx._uid = bytes(range(0x20, 0x30))
sent = []
mx.transmit = lambda data: (sent.append(bytes(data)), len(data))[1]

def uid(n):
    return bytes([n]) * 16

def nm(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def rx(sender, opcode, payload=b'', protocol=0x2F):
    frame = bytearray(create_mxr_frame(sender, opcode, payload))
    frame[2] = protocol
    mx.process_frame(time.time(), bytes(frame), ADDR)

def hello(sender, features, protocol=0x2F):
    rx(sender, 0x00, struct.pack('<H', protocol) + nm('ONEIP') + nm('P8SN%08d' % sender[0]) + nm('4.8.0')
                   + struct.pack('<I', int(features)), protocol=0x01)
    return mx.get_by_uid(MxrDeviceUid(sender))

def call(coro):
    return asyncio.run(coro)

def message(kind, target, flags, logo, priority, text, length=None):
    t = text.encode()
    return (bytes([2, kind, 0, 0]) + target + bytes([flags, logo & 0xFF, priority, 0xA5])
            + struct.pack('<H', len(t) if (length is None) else length) + t)

# ------------------------------------------------------------------- reading
out = hello(uid(0x10), DeviceFeature.ONEIP_SINK)
assert out.osd_message is None
state = message(6, uid(0x10), int(F.SET | F.SHOWN | F.SUPPORTED), -1, 2, 'Back at <b>3</b>')
rx(uid(0x10), 0x53, state + b'\0junk')
m = out.osd_message
assert m == OsdMessage(flags=F.SET | F.SHOWN | F.SUPPORTED, logo=-1, priority=P.TOP, text='Back at <b>3</b>'), m
assert seen.messages == [(out, m)], seen.messages
rx(uid(0x10), 0x53, state)
assert len(seen.messages) == 1, 'an unchanged message was reported'
print('decode      :', m)

# A unit answers for its own output only, and with all the text it counts; the
# request and the write are for a unit, not reports.
other = hello(uid(0x11), DeviceFeature.ONEIP_SINK)
for what, frame in (('an answer about another unit', message(6, uid(0x10), 1, 0, 0, 'x')),
                    ('an answer short of its text', message(6, uid(0x11), 1, 0, 0, 'abc', length=4)),
                    ('a write', message(5, uid(0x11), 1, 0, 0, 'x')),
                    ('a request', message(4, uid(0x11), 0, 0, 0, '')),
                    ('a frame short of its length', message(6, uid(0x11), 1, 0, 0, '')[:25])):
    rx(uid(0x11), 0x53, frame)
    assert other.osd_message is None, f'{what} was kept'
print('ignored     : only a unit\'s answer about itself, with all its text')

# ------------------------------------------------------------------- writing
sent.clear()
assert call(out.show_osd_message('Back at <b>3</b>', logo=-1, priority=P.TOP)) is True
f = sent[-1]
assert int.from_bytes(f[20:22], 'little') == 0x53, f[:24].hex()
assert f[24:] == message(5, uid(0x10), int(F.SET), -1, 2, 'Back at <b>3</b>')[:23] + bytes([0]) \
    + struct.pack('<H', 16) + b'Back at <b>3</b>', f[24:].hex()
assert call(out.request_osd_message()) is True
assert sent[-1][24:] == bytes([2, 4, 0, 0]) + uid(0x10) + bytes(6), sent[-1][24:].hex()
assert call(out.clear_osd_message()) is True
assert sent[-1][24:] == bytes([2, 5, 0, 0]) + uid(0x10) + bytes(6), sent[-1][24:].hex()
assert call(out.show_osd_message('x' * OSD_MESSAGE_TEXT_MAX, logo=5)) is True
assert call(out.show_osd_message('', logo=0, priority=P.LOW)) is True
print('write       : show, clear and request, the text unterminated')

def refused(coro, why):
    n = len(sent)
    assert call(coro) is False, why
    assert len(sent) == n, f'{why}: refused, but transmitted anyway'
refused(out.show_osd_message('x' * (OSD_MESSAGE_TEXT_MAX + 1)), 'a text over 255 bytes')
refused(out.show_osd_message('a\nb'), 'a control character')
refused(out.show_osd_message('x', logo=6), 'a logo past 5')
refused(out.show_osd_message('x', logo=-2), 'a logo below -1')
refused(out.show_osd_message('x', priority=3), 'a priority past TOP')
src = hello(uid(0x12), DeviceFeature.ONEIP_SOURCE)
refused(src.show_osd_message('x'), 'a unit with no OneIP output')
refused(src.request_osd_message(), 'a unit with no OneIP output')
refused(src.clear_osd_message(), 'a unit with no OneIP output')
print('refusals    : nothing a unit would refuse is sent')

print('ALL OK')
