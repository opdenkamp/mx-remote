######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''How a OneIP source unit encrypts its streams (0x54), and asking it.

Every field of every stream is distinct from the others and from stream to
stream, with a port and a key version too wide for a narrower read and the
reserved bytes set, so a field read at a neighbour's offset shows.
'''

import asyncio, os, struct, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import DeviceFeature, MxrDeviceUid, OneIPPrivacyStream
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

def rx(sender, opcode, payload=b'', protocol=0x30):
    frame = bytearray(create_mxr_frame(sender, opcode, payload))
    frame[2] = protocol
    mx.process_frame(0.0, bytes(frame), ADDR)

def hello(sender, protocol, features):
    rx(sender, 0x00, struct.pack('<H', protocol) + name('ONEIP') + name('P8SN%08d' % sender[0])
                   + name('5.0.0') + struct.pack('<I', int(features)), protocol=0x01)
    return mx.get_by_uid(MxrDeviceUid(sender))

def call(coro):
    return asyncio.run(coro)

def stream(n):
    '''Stream n; stream 2 is in the clear.'''
    s = bytes([239, 0, 0, n]) + struct.pack('<H', 5000 + n * 0x101) + bytes([0x10 + n, 0xEE])
    s += bytes([int(n != 2), 0x20 + n, 0x30 + n])
    s += bytes(0x40 + n * 16 + i for i in range(8))
    s += bytes(0x80 + n * 16 + i for i in range(16))
    s += bytes(0xC0 + n * 8 + i for i in range(8))
    s += struct.pack('<I', 0x01020304 * n) + bytes([0xEE])
    assert len(s) == 48, len(s)
    return s

def expected(n):
    return OneIPPrivacyStream(group=f'239.0.0.{n}', port=5000 + n * 0x101, version=0x10 + n, on=(n != 2),
                              full_id=0x20 + n, short_id=0x30 + n,
                              iv=bytes(0x40 + n * 16 + i for i in range(8)),
                              key_generator=bytes(0x80 + n * 16 + i for i in range(16)),
                              key_id=bytes(0xC0 + n * 8 + i for i in range(8)),
                              key_version=0x01020304 * n)

def report(header_uid, count=3):
    return header_uid + bytes([0, count, 0xA5, 0x5A]) + b''.join(stream(n) for n in range(1, count + 1))

# ------------------------------------------------------------------- reading
# A report is filed under its sender, whatever uid its header names.
src = hello(uid(0x10), 0x30, DeviceFeature.ONEIP_SOURCE)
assert src.oneip_privacy is None
rx(uid(0x10), 0x54, report(uid(0x11)))
p = src.oneip_privacy
assert p is not None, 'no report was kept'
assert (p.video, p.audio, p.anc) == (expected(1), expected(2), expected(3)), p
assert mx.get_by_uid(MxrDeviceUid(uid(0x11))) is None
print('decode      :', p)

# Only a whole report of three streams is kept; a longer one is read for its
# first three.
other = hello(uid(0x12), 0x30, DeviceFeature.ONEIP_SOURCE)
whole = report(uid(0x12))
request = whole[:16] + bytes([1]) + whole[17:]
two = whole[:17] + bytes([2]) + whole[18:]
for what, frame in (('a request', request), ('a count of two', two), ('a frame a byte short', whole[:-1])):
    rx(uid(0x12), 0x54, frame)
    assert other.oneip_privacy is None, f'{what} was kept'
rx(uid(0x12), 0x54, report(uid(0x12), count=4))
assert other.oneip_privacy is not None and other.oneip_privacy.anc == expected(3), 'a longer report was dropped'
print('whole       : only a report of all three streams is kept')

# ------------------------------------------------------------------- asking
sent.clear()
assert call(src.request_oneip_privacy()) is True
frame = sent[-1]
assert int.from_bytes(frame[20:22], 'little') == 0x54 and frame[2] == 0x30, frame[:24].hex()
assert frame[24:] == uid(0x10) + bytes([1, 0, 0, 0]), frame[24:].hex()
sent.clear()
assert call(mx.request_all_oneip_privacy()) is True
assert sent[-1][24:] == bytes(16) + bytes([1, 0, 0, 0]) and sent[-1][2] == 0x30, sent[-1].hex()
print('request     : names the unit asked, or the zero uid for every one, stamped 0x30')

def refused(coro, why):
    n = len(sent)
    assert call(coro) is False, why
    assert len(sent) == n, f'{why}: refused, but transmitted anyway'
refused(hello(uid(0x13), 0x2F, DeviceFeature.ONEIP_SOURCE).request_oneip_privacy(), 'a source below 0x30')
refused(hello(uid(0x14), 0x30, DeviceFeature.ONEIP_SINK).request_oneip_privacy(), 'a unit that is not a source')
print('refusals    : nothing a unit would ignore is sent')

print('ALL OK')
