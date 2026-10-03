######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''A device that may hold state this client missed is asked for it.

A device repeats a frame in only a couple of periodic broadcasts after it
changes, and resends everything only every few minutes. So a device this client
first hears, or hears again after counting it offline, is sent a discover
naming it - unless its own boot or a recent discover to every device already
covers that.
'''

import os, struct, sys, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.proto.Factory import create_mxr_frame
from datetime import timedelta

F = mx_remote.DeviceFeature
ADDR = ('192.0.2.9', 8812)
HELLO, DISCOVER = 0x00, 0x01
OURS = bytes(range(0x20, 0x30))

def name(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def uid(n):
    return bytes([n]) * 16

def hello(mx, peer, features):
    mx.on_datagram_received(create_mxr_frame(peer, HELLO, struct.pack('<H', 0x2A) + name('ONEIP')
                                             + name('SR0001') + name('1.0.0')
                                             + struct.pack('<I', int(features))), ADDR)

def silence(mx, peer):
    '''Move the last time peer was heard far enough back to count as offline.'''
    dev = mx.get_by_uid(mx_remote.MxrDeviceUid(peer))
    dev._last_ping -= timedelta(seconds=600)
    assert not dev.online

def discovers(sent):
    '''The discovers sent, as their payloads.'''
    return [f[24:] for f in sent if int.from_bytes(f[20:22], 'little') == DISCOVER]

def client():
    mx = mx_remote.Remote(open_connection=False)
    mx._uid = OURS
    mx._hello_due = time.time() + 3600          # nothing is due on the clock
    sent = []
    mx.transmit = lambda data: (sent.append(data), len(data))[1]
    return mx, sent

ROUTING = F.VIDEO_ROUTING

# ---- asked: a device first heard, and one back from offline
mx, sent = client()
peer = uid(0x21)
hello(mx, peer, ROUTING)
assert discovers(sent) == [peer], 'a device this client first heard'
print('asked       : a device first heard is sent a discover naming it')

sent.clear()
hello(mx, peer, ROUTING)
assert discovers(sent) == [], 'a device that never went away'
print('asked       : not again while it stays online')

silence(mx, peer)
hello(mx, peer, ROUTING)
assert discovers(sent) == [peer], 'a device back from offline'
print('asked       : again once it comes back from offline')

# ---- not asked: a device that sends everything anyway, or holds nothing
mx, sent = client()
rebooted = uid(0x23)
hello(mx, rebooted, ROUTING)
silence(mx, rebooted)
sent.clear()
hello(mx, rebooted, ROUTING | F.BOOT_BIT)
assert discovers(sent) == [], 'a device whose reboot toggle flipped'
print('not asked   : a device whose reboot toggle flipped')

rebooting = uid(0x24)
hello(mx, rebooting, ROUTING | F.STATUS_REBOOTING)
assert discovers(sent) == [], 'a device about to reboot'
print('not asked   : a device about to reboot')

manager = uid(0x25)
hello(mx, manager, F.MANAGER)
assert discovers(sent) == [], 'a management client'
print('not asked   : a management client')

# ---- covered: a discover to every device already asked each one
mx, sent = client()
mx.tx_discover()
sent.clear()
hello(mx, uid(0x27), ROUTING)
assert discovers(sent) == [], 'asked again inside the window'
print('covered     : a discover to every device covers one heard within 60s')

mx._discover_timeout = time.time() - 61
hello(mx, uid(0x28), ROUTING)
assert discovers(sent) == [uid(0x28)], 'not asked once the window had passed'
print('covered     : but not one heard after')

# ---- replay: processing a capture asks nothing, there is no one to ask
mx = mx_remote.Remote(open_connection=False)
mx._uid = OURS
mx.process_frame(time.time(), create_mxr_frame(uid(0x29), HELLO, struct.pack('<H', 0x2A) + name('ONEIP')
                                               + name('SR0001') + name('1.0.0')
                                               + struct.pack('<I', int(ROUTING))), ADDR)
assert mx.get_by_uid(mx_remote.MxrDeviceUid(uid(0x29))) is not None
print('replay      : a capture registers the device without sending')

print('ALL OK')
