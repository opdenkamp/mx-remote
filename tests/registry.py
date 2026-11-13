######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''The device registry kept as a unit keeps it.

Who is in the mesh and how each device reads follows a unit's own registry: a
tree its peers' topology reports shape, devices forgotten after three offline
windows of silence, liveness kept by every frame with a valid header, identity
as announced, and bays counted online only once they have arrived. The cases
and edges are the ones the Rust crate pins against the firmware.

Padding and fields a case does not read are filled with 0xA5, so a field read
at the right offset with the wrong width returns a wrong value.
'''

import asyncio, os, struct, sys, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from datetime import datetime, timedelta
from mx_remote import DeviceFeature, Endpoints, MxrDeviceUid
from mx_remote.proto.Constants import MXR_OPCODE_VERSIONS, BayStatusMask, bay_status_hdcp
from mx_remote.proto.Factory import create_mxr_frame

ADDR = ('192.0.2.9', 8812)
OURS = bytes([0xFE]) * 16
M, B = Endpoints.MULTICAST, Endpoints.BROADCAST
HELLO, BAY_CONFIG, LINKS, BAY_CONFIG_SECONDARY, SOURCES = 0x00, 0x02, 0x03, 0x23, 0x26
NET_LINK_STATUS, PULSE, TOPOLOGY, BAY_STATUS, MESH_OPERATION = 0x29, 0x2B, 0x30, 0x39, 0x3B
THIRD_PARTY = 0x55

def poisoned(n):
    return bytearray([0xA5] * n)

def uid(n):
    return bytes([n]) * 16

def nm(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def frame(sender, opcode, payload=b'', protocol=None):
    '''A frame stamped as a device stamps it: at the opcode's own row.'''
    data = bytearray(create_mxr_frame(sender, opcode, bytes(payload)))
    data[2] = MXR_OPCODE_VERSIONS.get(opcode, 1) if (protocol is None) else protocol
    return bytes(data)

def hello_payload(protocol=0x2A, name='ONEIP', serial='RG0001', features=DeviceFeature.MESH):
    return struct.pack('<H', protocol) + nm(name) + nm(serial) + nm('4.8.0') + struct.pack('<I', int(features))

def bay(port=0, name='Input 1', status=0, features=(1 << 1)):
    '''One 61-byte bay record: an input unless features say otherwise.'''
    return bytes([port, 0, 0, 0, 0]) + nm(name) + nm(name) + nm('1080p') + struct.pack('<II', status, features)

class Watching(mx_remote.MxrCallbacks):
    def __init__(self):
        self.unregistered = []
        self.linked = 0
        self.changed = 0
    def on_device_unregistered(self, dev):
        self.unregistered.append(dev)
    def on_bay_linked(self, bay, linked_serial, linked_bay, features):
        self.linked += 1
    def on_device_config_changed(self, dev):
        self.changed += 1

class DualConn:
    '''Stands in for a ConnectionAsync running both endpoints.'''
    def __init__(self):
        self.is_dual = True
        self.sent = []
    def transmit(self, data, endpoints=M):
        self.sent.append((bytes(data), endpoints))
        return len(data)

def client(callbacks=None, dual=False):
    mx = mx_remote.Remote(open_connection=False, callbacks=callbacks)
    mx._uid = OURS
    if dual:
        mx.conn = DualConn()
    else:
        mx.transmit = lambda data, to=None: len(data)
    return mx

def feed(mx, sender, opcode, payload=b'', path=None, at=None, protocol=None):
    mx.process_frame(time.time() if (at is None) else at, frame(sender, opcode, payload, protocol), ADDR, path)

def device(mx, sender):
    return mx.get_by_uid(MxrDeviceUid(sender))

def heard_since(dev):
    '''Seconds since the device was last counted alive.'''
    return (datetime.now() - dev._last_ping).total_seconds()

# ------------------------------------------------------------- identity as announced
def raw_hello(name, version):
    '''A hello whose fields sit over poison: a name of 16 bytes has no
    terminator, and the version stops at a NUL with poison behind it.'''
    p = poisoned(54)
    p[0:2] = struct.pack('<H', 0x2F)
    p[2:2 + len(name)] = name
    if len(name) < 16:
        p[2 + len(name)] = 0
    p[18:26] = b'RAW0001\0'
    p[34:34 + len(version)] = version
    if len(version) < 16:
        p[34 + len(version)] = 0
    p[50:54] = struct.pack('<I', int(DeviceFeature.MESH))
    return p

seen = Watching()
mx = client(seen)
PEER = uid(0x46)
name = b'Caf\xe9 lounge 1234'
assert len(name) == 16
feed(mx, PEER, HELLO, raw_hello(name, b'4.8\xb1-7'))
dev = device(mx, PEER)
assert dev.raw_name == name, dev.raw_name
assert dev.raw_version == b'4.8\xb1-7', dev.raw_version
assert dev.raw_serial == b'RAW0001', dev.raw_serial

# Both bytes outside ASCII decode to the same replacement character, so only
# the raw name tells this hello apart from the last.
seen.changed = 0
feed(mx, PEER, HELLO, raw_hello(b'Caf\xe8 lounge 1234', b'4.8\xb1-7'))
assert seen.changed == 1, 'a renamed device was not reported changed'
feed(mx, PEER, HELLO, raw_hello(b'Caf\xe8 lounge 1234', b'4.8\xb2-7'))
assert seen.changed == 2, 'a new version was not reported changed'
feed(mx, PEER, HELLO, raw_hello(b'Caf\xe8 lounge 1234', b'4.8\xb2-7'))
assert seen.changed == 2, 'an unchanged hello was reported changed'

serial = raw_hello(b'Unit', b'4.8.0')
serial[18:34] = b'SN\xc900001\0' + bytes(poisoned(7))
feed(mx, PEER, HELLO, serial)
assert dev.raw_serial == b'SN\xc900001', dev.raw_serial
seen.changed = 0
serial[20] = 0xCA
feed(mx, PEER, HELLO, serial)
assert seen.changed == 1, 'a new serial was not reported changed'
serial[18:34] = b'SN\xc90000123456789'
feed(mx, PEER, HELLO, serial)
assert dev.raw_serial == b'SN\xc90000123456789', 'a serial filling its field was not cut at the field'

feed(mx, PEER, HELLO, raw_hello(b'', b'5.0'))
assert dev.raw_name == b'', 'an empty name was substituted'
assert dev.raw_version == b'5.0'
feed(mx, PEER, HELLO, raw_hello(b'   ', b'5.0'))
assert dev.raw_name == b'   ', 'a blank name was substituted'
print('identity  : name, version and serial are reported as the bytes announced')

# ------------------------------------------------------------- a hello is taken whole
mx = client()
short = hello_payload(name='Short', serial='SH0001')[:53]
feed(mx, PEER, HELLO, short)
assert device(mx, PEER) is None, 'registered by a short hello'
feed(mx, PEER, HELLO, hello_payload(name='Long', serial='SH0001') + bytes(poisoned(6)))
dev = device(mx, PEER)
assert dev.name == 'Long' and dev.features == DeviceFeature.MESH, (dev.name, dev.features)
feed(mx, PEER, HELLO, hello_payload(name='Renamed', serial='SH0001')[:53])
assert dev.name == 'Long', 'updated by a short hello'

dev._last_ping -= timedelta(seconds=61)
feed(mx, PEER, HELLO, hello_payload(serial='SH0002')[:53])
assert not dev.online, 'back by a short hello'
feed(mx, PEER, HELLO, hello_payload(serial='SH0002'))
assert dev.online
print('hello     : one shorter than 54 bytes is ignored whole; a longer one is read')

# ------------------------------------------------------------- what keeps a device alive
seen = Watching()
mx = client()
feed(mx, PEER, HELLO, hello_payload())
dev = device(mx, PEER)
pulse = frame(PEER, PULSE)
now = time.time()
dev._last_ping -= timedelta(seconds=50)
mx.process_frame(now, pulse, ADDR, M)
assert heard_since(dev) < 5, 'a frame kept no live device alive'
dev._last_ping -= timedelta(seconds=50)
mx.process_frame(now + 0.05, pulse, ADDR, B)
assert heard_since(dev) < 5, 'a second copy kept no live device alive'
dev._last_ping -= timedelta(seconds=50)
feed(mx, PEER, 0x17, b'')
assert heard_since(dev) < 5, 'an opcode nothing decodes kept no live device alive'

# A bay list from a device gone silent is taken, and does not bring it back.
ROUTER = uid(0x47)
feed(mx, ROUTER, HELLO, hello_payload(serial='RF0002', features=DeviceFeature.VIDEO_ROUTING))
router = device(mx, ROUTER)
router._last_ping -= timedelta(seconds=61)
mx._probe_once()
feed(mx, ROUTER, BAY_CONFIG, bay())
assert router.get_by_portnum(0) is not None, 'the bay list was not taken'
assert not router.online, 'brought back by its bay list'
assert not router.bays_online, 'its bays online while silent'
mx._probe_once()
feed(mx, ROUTER, HELLO, hello_payload(serial='RF0002', features=DeviceFeature.VIDEO_ROUTING))
assert router.online
assert not router.bays_online, 'online by the bay list it sent while silent'
print('alive     : every frame with a valid header keeps a live device so; only a hello revives one')

# A frame whose opcode is 0x59 or above has no valid header to a unit: it neither
# keeps its sender alive nor proves its path. Below that, a frame does both
# whether or not a handler takes it, as an empty 0x58 and an application's
# message at 0x55 do.
class Messages(mx_remote.MxrCallbacks):
    def __init__(self):
        self.messages = []
    def on_third_party_message(self, dev, message):
        self.messages.append(message)

seen = Messages()
mx = client(seen)
APP = uid(0x48)
feed(mx, APP, HELLO, hello_payload(serial='OP0001', features=DeviceFeature.MANAGER))
app = device(mx, APP)
app._last_ping -= timedelta(seconds=50)
feed(mx, APP, 0x59, b'', path=M)
assert heard_since(app) >= 50, 'kept alive by 0x59'
assert app._heard_multicast is None, '0x59 proved its path'
feed(mx, APP, 0x58, b'', path=M)
assert heard_since(app) < 50, '0x58 did not keep its sender alive'
assert app._heard_multicast is not None, '0x58 did not prove its path'
app._last_ping -= timedelta(seconds=50)
app._heard_multicast = None
feed(mx, APP, THIRD_PARTY, bytes([0x00, 0x00, 0x1E, 0xC2]) + b'hello', path=M)
assert len(seen.messages) == 1, "the application's message was dropped"
assert heard_since(app) < 50, '0x55 did not keep its sender alive'
assert app._heard_multicast is not None, '0x55 did not prove its path'
print('table     : an opcode from 0x59 on touches no timer; 0x58 and 0x55 keep their sender alive')

# ------------------------------------------------------------- bays online
mx = client()
ONEIP = uid(0x49)
feed(mx, ONEIP, HELLO, hello_payload(protocol=0x2F, serial='ON0001', features=DeviceFeature.ONEIP_SINK))
oneip = device(mx, ONEIP)
assert not oneip.bays_online, 'online from its hello alone'
feed(mx, ONEIP, BAY_CONFIG, bay())
feed(mx, ONEIP, BAY_CONFIG_SECONDARY, bay())
assert not oneip.bays_online, 'a OneIP device online by its bay list'
feed(mx, ONEIP, SOURCES, poisoned(39))
assert not oneip.bays_online, 'online by a list a unit refuses'
feed(mx, ONEIP, SOURCES, b'')
assert oneip.bays_online, 'a OneIP device not online by its source list'

MATRIX = uid(0x4A)
feed(mx, MATRIX, HELLO, hello_payload(protocol=0x2F, name='FF88', serial='MX0001', features=DeviceFeature.VIDEO_ROUTING))
matrix = device(mx, MATRIX)
feed(mx, MATRIX, SOURCES, b'')
feed(mx, MATRIX, BAY_CONFIG_SECONDARY, bay())
feed(mx, MATRIX, BAY_CONFIG, b'')
assert not matrix.bays_online, 'online by a source list, a secondary list or an empty one'
feed(mx, MATRIX, BAY_CONFIG, bay())
assert matrix.bays_online, 'not online by its primary bay list'

plain = DeviceFeature(0)
feed(mx, MATRIX, HELLO, hello_payload(protocol=0x2F, name='FF88', serial='MX0001', features=DeviceFeature.STATUS_REBOOTING))
assert not matrix.bays_online, 'still online while rebooting'
assert matrix.online, 'a rebooting device is no longer connected'
feed(mx, MATRIX, HELLO, hello_payload(protocol=0x2F, name='FF88', serial='MX0001', features=plain))
assert not matrix.bays_online, 'online again by its hello'
feed(mx, MATRIX, BAY_CONFIG, bay())
assert matrix.bays_online
matrix._last_ping -= timedelta(seconds=61)
assert not matrix.bays_online, 'online while silent'
mx._probe_once()
feed(mx, MATRIX, HELLO, hello_payload(protocol=0x2F, name='FF88', serial='MX0001', features=plain))
assert not matrix.bays_online, 'back online by its hello'
feed(mx, MATRIX, BAY_CONFIG, bay())
assert matrix.bays_online
print('bays      : a OneIP device by its source list, any other by its primary bay list')

# ------------------------------------------------------------- reached by multicast
mx = client(dual=True)
REACHED = uid(0x4B)
t0 = time.time() - 300
feed(mx, REACHED, HELLO, hello_payload(serial='MC0001'), path=M, at=t0)
reached = device(mx, REACHED)
assert reached.multicast is False, 'reached by the frame that registered it'
feed(mx, REACHED, HELLO, hello_payload(serial='MC0002'), path=B, at=t0 + 1)
assert reached.multicast is False, 'reached by broadcast'
feed(mx, REACHED, HELLO, hello_payload(serial='MC0003'), path=M, at=time.time() - 119)
assert reached.multicast is True, 'forgotten inside two minutes'
feed(mx, REACHED, HELLO, hello_payload(serial='MC0004'), path=B, at=time.time())
reached._heard_multicast = time.time() - 120
assert reached.multicast is False, 'kept past two minutes'

single = client()
single.conn = DualConn()
single.conn.is_dual = False
feed(single, REACHED, HELLO, hello_payload(serial='MC0005'), path=M)
feed(single, REACHED, HELLO, hello_payload(serial='MC0006'), path=M)
assert device(single, REACHED).multicast is None, 'one endpoint claimed to know'
assert device(client(), REACHED) is None
print('multicast : by a frame by multicast in two minutes; unknown on one endpoint')

# ------------------------------------------------------------- forgetting
for protocol, forget in ((0x2A, 180), (0x29, 45), (0x1F, 540)):
    seen = Watching()
    mx = client(seen)
    feed(mx, PEER, HELLO, hello_payload(protocol=protocol, serial='FG0002'))
    dev = device(mx, PEER)
    dev._last_ping = datetime.now() - timedelta(seconds=forget - 1)
    mx._probe_once()
    assert device(mx, PEER) is not None, f'forgotten early at {protocol:#x}'
    assert seen.unregistered == []
    dev._last_ping = datetime.now() - timedelta(seconds=forget)
    mx._probe_once()
    assert device(mx, PEER) is None, f'kept at {forget}s'
    assert seen.unregistered == [dev], seen.unregistered
    assert [e.uid for e in mx.device_tree] == [MxrDeviceUid(OURS)], 'left in the tree'
print('forget    : three offline windows after the last frame, to the second')

# One heard again is registered anew, at the end of the list, without its links.
seen = Watching()
mx = client(seen)
LINKED, LATER = uid(0x4C), uid(0x4D)
def matrix_with_one_bay(sender):
    feed(mx, sender, HELLO, hello_payload(name='FF88', serial='LK0001', features=DeviceFeature.VIDEO_ROUTING))
    feed(mx, sender, BAY_CONFIG, bay())
link = bytes([0, 0]) + nm('P8SN00000001') + nm('Out 1') + struct.pack('<I', 1)
matrix_with_one_bay(LINKED)
feed(mx, LATER, HELLO, hello_payload(serial='LK0002'))
feed(mx, LINKED, LINKS, link)
assert seen.linked == 1
device(mx, LINKED)._last_ping -= timedelta(seconds=600)
mx._probe_once()
assert device(mx, LINKED) is None
matrix_with_one_bay(LINKED)
assert [e.uid for e in mx.device_tree] == [MxrDeviceUid(u) for u in (OURS, LATER, LINKED)], mx.device_tree
feed(mx, LINKED, LINKS, link)
assert seen.linked == 2, 'the link of a forgotten device was remembered'
print('forget    : one heard again is new, listed last, and its links are new')

# ------------------------------------------------------------- a bay's whole status word
mx = client()
feed(mx, MATRIX, HELLO, hello_payload(protocol=0x2F, name='FF88', serial='SW0001', features=DeviceFeature.VIDEO_ROUTING))
first = 0x0080_0008
feed(mx, MATRIX, BAY_CONFIG, bay(status=first))
in1 = device(mx, MATRIX).get_by_portnum(0)
assert in1.status_word == first, in1.status_word
record = poisoned(32)
record[0:2] = struct.pack('<H', 0)
nxt = int(BayStatusMask.ENCODER_ERROR) | (2 << 22)
record[20:24] = struct.pack('<I', nxt)
record[24:28] = struct.pack('<I', 1 << 1)
feed(mx, MATRIX, BAY_STATUS, record)
assert in1.status_word == nxt, in1.status_word
assert BayStatusMask.ENCODER_ERROR in in1.status_word
assert bay_status_hdcp(in1.status_word) == 2
print('status    : a bay reports its whole status word, as last sent')

# ------------------------------------------------------------- the IGMP querier
IGMP, UPLINK = (1 << 3), (1 << 6)
def uplink(features, querier, length):
    p = poisoned(length)
    p[0:2] = struct.pack('<H', 3)
    p[2:4] = struct.pack('<H', features)
    p[4:21] = bytes(17)
    p[28:32] = bytes([10, 8, 8, 9])
    p[32:36] = bytes(querier)
    return p
mx = client()
feed(mx, ONEIP, HELLO, hello_payload(protocol=0x2F, serial='IG0001', features=DeviceFeature.ONEIP_SINK))
unit = device(mx, ONEIP)
assert unit.igmp_querier is None
feed(mx, ONEIP, NET_LINK_STATUS, uplink(IGMP | UPLINK, [10, 1, 2, 3], 144), protocol=0x22)
assert unit.igmp_querier == '10.1.2.3', unit.igmp_querier
for protocol, payload in ((0x22, uplink(IGMP, [10, 9, 9, 9], 144)),
                          (0x22, uplink(IGMP | UPLINK, [10, 9, 9, 9], 143)),
                          (0x21, uplink(IGMP | UPLINK, [10, 9, 9, 9], 152))):
    feed(mx, ONEIP, NET_LINK_STATUS, payload, protocol=protocol)
    assert unit.igmp_querier == '10.1.2.3', (hex(protocol), len(payload), unit.igmp_querier)
feed(mx, ONEIP, NET_LINK_STATUS, uplink(UPLINK, [10, 1, 2, 3], 144), protocol=0x22)
assert unit.igmp_querier is None, 'a report without IGMP support'
feed(mx, ONEIP, NET_LINK_STATUS, uplink(IGMP | UPLINK, [10, 1, 2, 3], 144), protocol=0x22)
feed(mx, ONEIP, NET_LINK_STATUS, uplink(IGMP | UPLINK, [0, 0, 0, 0], 144), protocol=0x22)
assert unit.igmp_querier is None, '0.0.0.0'
print('querier   : the last whole uplink report of the current layout names it')

# ------------------------------------------------------------- a first membership report
mx = client()
feed(mx, ONEIP, HELLO, hello_payload(protocol=0x2F, serial='MR0001',
                                     features=DeviceFeature.ONEIP_SINK | DeviceFeature.MESH))
member = device(mx, ONEIP)
fired = []
member.register_callback(lambda d: fired.append(d))
mesh = poisoned(40)
mesh[0] = 0xFF
mesh[4:20] = bytes(16)
feed(mx, ONEIP, MESH_OPERATION, mesh)
assert fired and member.mesh_master_uid == MxrDeviceUid(bytes(16)), 'a first report naming no master was swallowed'
fired.clear()
feed(mx, ONEIP, MESH_OPERATION, mesh)
assert not fired, 'an unchanged report fired again'
print('mesh      : a first membership report naming no master is reported once')

# ------------------------------------------------------------- the registry as a tree
def topology(uids):
    '''A topology list naming uids, each with a mask of its own and its padding
    poisoned.'''
    p = poisoned(24 * len(uids))
    for i, u in enumerate(uids):
        p[i * 24:i * 24 + 16] = u
        p[i * 24 + 16:i * 24 + 20] = struct.pack('<I', 0x10 + i)
    return p

def heard(ns):
    '''A registry that has heard ns in that order.'''
    mx = client()
    for n in ns:
        feed(mx, uid(n), HELLO, hello_payload(serial='TR0001'))
    return mx

def tree(mx):
    '''The tree as (n, depth), this client as 0xFE.'''
    return [(e.uid.byte_value[0], e.depth) for e in mx.device_tree]

def report(mx, sender, ns):
    feed(mx, uid(sender), TOPOLOGY, topology([uid(n) for n in ns]))

mx = heard([30, 10, 20])
assert tree(mx) == [(0xFE, 0), (30, 0), (10, 0), (20, 0)], tree(mx)
print('tree      : this client heads the root, and each device joins its end')

mx = heard([1, 2, 3, 4])
report(mx, 1, [4, 2])
assert tree(mx) == [(0xFE, 0), (1, 0), (4, 1), (2, 1), (3, 0)], tree(mx)
report(mx, 1, [2])
assert tree(mx) == [(0xFE, 0), (1, 0), (2, 1), (3, 0), (4, 0)], tree(mx)
report(mx, 3, [1])
assert tree(mx) == [(0xFE, 0), (3, 0), (1, 1), (2, 2), (4, 0)], ('a subtree moves whole', tree(mx))
print('tree      : a list moves devices under its sender, and one left out back to the root')

mx = heard([1, 2, 3])
report(mx, 2, [3])
report(mx, 1, [2])
assert tree(mx) == [(0xFE, 0), (1, 0), (2, 1), (3, 2)], tree(mx)
report(mx, 1, [3, 2])
assert tree(mx) == [(0xFE, 0), (1, 0), (2, 1), (3, 2)], tree(mx)
print('tree      : a device below the sender already stays where it is')

mx = heard([1, 2])
same = topology([uid(2), uid(3)])
feed(mx, uid(1), TOPOLOGY, same)
assert tree(mx) == [(0xFE, 0), (1, 0), (2, 1)], tree(mx)
feed(mx, uid(3), HELLO, hello_payload(serial='TR0003'))
feed(mx, uid(1), TOPOLOGY, same)
assert tree(mx) == [(0xFE, 0), (1, 0), (2, 1), (3, 0)], ('moved by the same list again', tree(mx))
padded = bytearray(same)
padded[44] ^= 0xFF
feed(mx, uid(1), TOPOLOGY, padded)
assert tree(mx) == [(0xFE, 0), (1, 0), (2, 1), (3, 1)], tree(mx)
print('tree      : only a list differing byte for byte, padding included, reshapes it')

mx = heard([1, 2, 3, 4])
report(mx, 1, [4])
report(mx, 1, [2, 0x77, 3, 4])
assert tree(mx) == [(0xFE, 0), (1, 0), (4, 1), (2, 1), (3, 1)], tree(mx)
print('tree      : a device not registered is skipped, and the moves go on')

mx = heard([1, 2, 3, 4])
report(mx, 2, [3])
report(mx, 1, [2, 4])
assert tree(mx) == [(0xFE, 0), (1, 0), (2, 1), (3, 2), (4, 1)], tree(mx)
device(mx, uid(2))._last_ping -= timedelta(seconds=200)
mx._probe_once()
assert tree(mx) == [(0xFE, 0), (1, 0), (4, 1), (3, 1)], tree(mx)
print("tree      : a forgotten device's children move to the end of its parent's")

mx = heard([1, 2])
report(mx, 1, [0xFE])
assert tree(mx) == [(1, 0), (0xFE, 1), (2, 0)], tree(mx)
report(mx, 2, [1])
assert tree(mx) == [(2, 0), (1, 1), (0xFE, 2)], tree(mx)
report(mx, 1, [0xFE, 2])
assert tree(mx) == [(2, 0), (1, 1), (0xFE, 2)], ('this client moved from below its sender', tree(mx))
print('tree      : a report moves this client like any device')

mx = heard([1, 2])
report(mx, 2, [1])
report(mx, 1, [1])
assert tree(mx) == [(0xFE, 0), (2, 0), (1, 1)], tree(mx)
print('tree      : a report naming its own sender moves nothing')

mx = heard([1, 2, 3, 4])
report(mx, 1, [2])
report(mx, 2, [3])
assert tree(mx) == [(0xFE, 0), (1, 0), (2, 1), (3, 2), (4, 0)], tree(mx)
report(mx, 3, [1, 2, 4])
assert tree(mx) == [(0xFE, 0), (1, 0), (2, 1), (3, 2), (4, 3)], ('an ancestor moved, or the moves stopped at it', tree(mx))
print('tree      : a device above the sender stays put, and the moves go on past it')

mx = heard([1])
one, two = uid(1), uid(10)
feed(mx, one, TOPOLOGY, topology([one, two]))
ragged = bytearray(topology([one, two]))
ragged[0:16] = uid(2)
ragged.append(0)
feed(mx, one, TOPOLOGY, ragged)
assert device(mx, one)._topology[0].uid == MxrDeviceUid(one), 'a ragged list was taken'
print('tree      : a ragged topology list is ignored')

# ------------------------------------------------------------- what this client announces
mx = client(dual=True)
def announced():
    mx.conn.sent.clear()
    mx.tx_hello()
    hello = mx.conn.sent[-1][0]
    return DeviceFeature(struct.unpack_from('<I', hello, 24 + 50)[0])
assert mx.features == announced()
assert DeviceFeature.MANAGER in mx.features
mx.set_mesh_controller(MxrDeviceUid(OURS))
assert DeviceFeature.MESH_MASTER not in mx.features, 'the role was announced with no bays mapped'
mx.set_mesh_bays_mapped(True)
mx._multicast_fault = True
features = mx.features
assert features == announced()
for bit in (DeviceFeature.MESH_MASTER, DeviceFeature.MESH_MEMBER, DeviceFeature.STATUS_MCAST_FAULT):
    assert bit in features, f'{bit!r} not reported'
print('features  : what this client reports announcing is what its hello carries')

# ------------------------------------------------------------- detecting bays
mx = client(dual=True)
assert asyncio.run(mx.send_oneip_detect_bays()) is True
(sent, on), = mx.conn.sent
assert int.from_bytes(sent[20:22], 'little') == 0x21
assert sent[2:4] == bytes([0x06, 0x00]), 'the stamp'
assert len(sent) == 24, 'a payload'
assert on == Endpoints.BOTH
print('detect    : 0x21, empty, stamped 0x06, to both endpoints')

# A device that lost its settings reports its bays' defaults, bit 25 set: the
# name and hidden flag held stay until the bit clears, and a bay first heard
# takes what it is sent.
LOST, HIDDEN = 1 << 25, 1 << 1
mx = client()
UNIT = uid(0x49)
feed(mx, UNIT, HELLO, hello_payload(serial='SL0001', features=DeviceFeature.VIDEO_ROUTING))
feed(mx, UNIT, BAY_CONFIG, bay(port=0, name='Lobby', status=HIDDEN))
dev = device(mx, UNIT)
b = dev.get_by_portnum(0)
assert (b.user_name, b.hidden) == ('Lobby', True), (b.user_name, b.hidden)
feed(mx, UNIT, BAY_CONFIG, bay(port=0, name='Input 1', status=LOST))
assert (b.user_name, b.hidden) == ('Lobby', True), ('defaults taken while lost', b.user_name, b.hidden)
feed(mx, UNIT, BAY_CONFIG, bay(port=0, name='Input 1', status=0))
assert (b.user_name, b.hidden) == ('Input 1', False), ('the bit cleared', b.user_name, b.hidden)
# Its record, as bay() lays it out, with a user name other than its default.
feed(mx, UNIT, BAY_CONFIG, bytes([1, 0, 0, 0, 0]) + nm('Input 2') + nm('Doorway') + nm('1080p')
                           + struct.pack('<II', LOST | HIDDEN, 1 << 1))
fresh = dev.get_by_portnum(1)
assert (fresh.bay_name, fresh.user_name, fresh.hidden) == ('Input 2', 'Doorway', True), \
    (fresh.bay_name, fresh.user_name, fresh.hidden)
print('lost      : a bay keeps its name and hidden flag while its device lost its settings')

print('ALL OK')
