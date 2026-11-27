######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''A OneIP controller's driver proxy, found on a flat network.

On its uplink a controller sends a reduced hello under its uplink uid - no
MANAGER, no bays - and PROXY ANNOUNCE (0x59) under the same uid every 10 s. The
ANNOUNCE fixture is the controller's own published datagram (driver-proxy.md
section 8), not one this library built.
'''

import os, struct, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import DeviceFeature, MxrDeviceUid
from mx_remote.proto.Factory import create_mxr_frame

UPLINK = bytes.fromhex('c0' * 16)
ADDR = ('192.0.2.40', 8811)
ANNOUNCE = bytes.fromhex('50383600c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0590002000001')

class Watching(mx_remote.MxrCallbacks):
    def __init__(self):
        self.events = []
    def on_proxy_controller_changed(self, dev, announced):
        self.events.append(('changed', dev.remote_id, announced, dev.proxy_controller))
    def on_proxy_found(self, uid, address, name, serial, version):
        self.events.append(('found', uid, address, name, serial, version))
    def on_device_config_complete(self, dev):
        self.events.append(('complete', dev.remote_id, dev.proxy_controller))

def nm(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def fresh():
    seen = Watching()
    mx = mx_remote.Remote(open_connection=False, callbacks=seen)
    mx._uid = bytes(range(0x20, 0x30))
    sent = []
    mx.transmit = lambda data, to=None: (sent.append(bytes(data)), len(data))[1]
    return mx, seen, sent

def hello(mx, at, uid=UPLINK, features=DeviceFeature.MESH_MEMBER, name='OneIP Controller'):
    frame = bytearray(create_mxr_frame(uid, 0x00, struct.pack('<H', 0x36) + nm(name) + nm('P8SN00001234')
                                       + nm('1.1.0') + struct.pack('<I', int(features))))
    mx.process_frame(at, bytes(frame), ADDR)

def announce(mx, at, datagram=ANNOUNCE):
    mx.process_frame(at, datagram, (ADDR[0], 8813))

uid = MxrDeviceUid(UPLINK)

# ---- hello first, then ANNOUNCE: reported once, the mark set before the
# configuration completes, so a caller can skip it there.
mx, seen, _ = fresh()
hello(mx, 100.0)
dev = mx.get_by_uid(uid)
assert dev is not None and not dev.proxy_controller and not dev.configuration_complete, \
    'a hello with no MANAGER and no bays is an incomplete device'
assert seen.events == []
announce(mx, 101.0)
assert seen.events == [('changed', uid, True, True),
                       ('found', uid, ADDR[0], 'OneIP Controller', 'P8SN00001234', '1.1.0'),
                       ('complete', uid, True)], seen.events
assert dev.proxy_controller and dev.configuration_complete
announce(mx, 111.0)
assert len(seen.events) == 3, 'a repeated ANNOUNCE reports nothing'
print('announce    : after the hello, reported once, complete with no bays')

# ---- a complete proxy is not asked again for a description it never sends
mx2, seen2, sent2 = fresh()
hello(mx2, 0.0)
announce(mx2, 1.0)
d2 = mx2.get_by_uid(uid)
d2._hello_received = 0.0        # long past the configuration timeout
assert d2.check_configuration_complete_timeout() is True, 'a proxy must not be re-asked'
print('announce    : no per-uid discover re-ask')

# ---- ANNOUNCE first: dropped like any frame but a hello from a stranger; the
# next one, 10 s on, marks it
mx, seen, _ = fresh()
announce(mx, 200.0)
assert mx.get_by_uid(uid) is None and seen.events == []
hello(mx, 201.0)
dev = mx.get_by_uid(uid)
assert not dev.proxy_controller, 'an ANNOUNCE from a sender not yet heard was kept'
announce(mx, 210.0)
assert dev.proxy_controller
assert [e[0] for e in seen.events] == ['changed', 'found', 'complete'], seen.events
print('announce    : before the hello, dropped; the next one marks it')

# ---- the mark lapses PROXY_ANNOUNCE_WINDOW (30 s) after the last ANNOUNCE;
# the device stays configured
seen.events.clear()
mx._lapse_proxies(210.0 + 29.9)
assert dev.proxy_controller and seen.events == [], 'dropped before 30 s'
mx._lapse_proxies(210.0 + 30.0)
assert not dev.proxy_controller
assert seen.events == [('changed', uid, False, False)], seen.events
assert dev.configuration_complete, 'a proxy that stopped announcing is no longer configured'
announce(mx, 250.0)
assert dev.proxy_controller
assert [e[0] for e in seen.events[1:]] == ['changed', 'found'], 'announcing again is found again'
print('announce    : lapses 30 s after the last, found again when it returns')

# The probe loop is what lapses it on a running client.
import time
dev._proxy_announced = time.time() - 31
mx._probe_once()
assert not dev.proxy_controller, 'the probe loop does not lapse a silent proxy'
print('announce    : the probe loop lapses it')

# ---- any ANNOUNCE version marks: a controller this library cannot join
# refuses with RESULT 5, which says why. Other sub-ops do not mark.
mx, seen, _ = fresh()
hello(mx, 400.0)
def proxy(payload):
    dg = bytearray(ANNOUNCE[:24]) + payload
    dg[22:24] = struct.pack('<H', len(payload))
    return bytes(dg)
for what, payload in (('a JOIN', b'\x01\x01' + bytes(16)), ('no version', b'\x00')):
    announce(mx, 401.0, proxy(payload))
    assert not mx.get_by_uid(uid).proxy_controller, f'{what} marked a proxy'
assert seen.events == []
announce(mx, 402.0, proxy(b'\x00\x02'))
assert mx.get_by_uid(uid).proxy_controller, 'an ANNOUNCE of version 2 did not mark'
print('announce    : sub-op 0 of any version marks, nothing else')

# ---- a unit without an ANNOUNCE is no proxy
mx, seen, _ = fresh()
hello(mx, 500.0)
assert not mx.get_by_uid(uid).proxy_controller and seen.events == []
print('ALL OK')
