######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''A ping addressed to this client is answered with a hello, and a device is
pinged only if it answers one.

A device on 0x2A pings a peer it suspects is gone and takes it offline when
nothing comes back within about 1.5s. This client announces 0x2A, and its next
scheduled hello can be seconds away, so the answer cannot wait for the clock.
'''

import asyncio, os, struct, sys, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.proto.Factory import create_mxr_frame

ADDR = ('192.0.2.9', 8812)
HELLO, PING = 0x00, 0x4A
OURS = bytes(range(0x20, 0x30))

def name(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def opcode(frame):
    return int.from_bytes(frame[20:22], 'little')

def hello(uid, protocol, serial):
    return create_mxr_frame(uid, HELLO, struct.pack('<H', protocol) + name('ONEIP') + name(serial)
                            + name('5.0.0') + struct.pack('<I', int(mx_remote.DeviceFeature.ONEIP_SINK)))

def client():
    mx = mx_remote.Remote(open_connection=False)
    mx._uid = OURS
    mx._hello_due = time.time() + 3600          # nothing is due on the clock
    sent = []
    mx.transmit = lambda data: (sent.append(data), len(data))[1]
    return mx, sent

# ---- answering: a ping for this client is answered at once, whoever sent it
mx, sent = client()
peer = bytes(range(1, 17))
mx.on_datagram_received(create_mxr_frame(peer, PING, OURS), ADDR)
assert [opcode(f) for f in sent] == [HELLO], 'a ping from a stranger went unanswered'
print('answer      : a stranger\'s ping for this client is answered with a hello')

mx.on_datagram_received(hello(peer, 0x2A, 'PR0002'), ADDR)
sent.clear()
mx.on_datagram_received(create_mxr_frame(peer, PING, bytes(range(0x40, 0x50))), ADDR)
assert sent == [], 'a ping for another device was answered'
print('answer      : a ping for another device is not')

mx.on_datagram_received(create_mxr_frame(peer, PING, OURS), ADDR)
assert [opcode(f) for f in sent] == [HELLO], 'a known device\'s ping went unanswered'
print('answer      : a known device\'s ping is answered')

# ---- sending: the ping names its device, and goes only to one on 0x2A or later
mx, sent = client()
new, old = bytes(range(0x60, 0x70)), bytes(range(0x70, 0x80))
mx.on_datagram_received(hello(new, 0x2A, 'PG0001'), ADDR)
mx.on_datagram_received(hello(old, 0x29, 'PG0002'), ADDR)
sent.clear()
assert asyncio.run(mx.get_by_uid(mx_remote.MxrDeviceUid(new)).ping()) is True
frame = sent.pop()
assert opcode(frame) == PING
assert frame[2] == 0x2A, 'the stamp: 0x%02X' % frame[2]
assert frame[24:] == new, 'the payload names another device'
assert asyncio.run(mx.get_by_uid(mx_remote.MxrDeviceUid(old)).ping()) is False
assert sent == [], 'a device below 0x2A was pinged'
print('send        : a 0x2A device is pinged by uid, a 0x29 one is refused')

print('ALL OK')
