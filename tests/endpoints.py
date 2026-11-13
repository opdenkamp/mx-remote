######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Running both endpoints a unit has, and picking each frame's endpoints as a
unit does.

A unit runs the group 224.8.8.8 on 8812 and the subnet broadcast on 8811. A
frame for every unit goes to both, one for a single device by the endpoint it
is heard by, and any other to the group, and to broadcast as well while some
peer has not been heard by multicast for two minutes or reports its multicast
fails. The choices and the reboot-all frames are the ones the Rust crate pins.

No socket is opened: a connection that records what it is asked to send
stands in for the transport, and the transport's own routing is checked with
endpoints that record instead of sending.
'''

import asyncio, os, socket, struct, sys, time, logging, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import DeviceFeature, Endpoints, MxrDeviceUid
from mx_remote.proto.Factory import create_mxr_frame
import mx_remote.remote.ConnectionAsync as connection_module
from mx_remote.remote.ConnectionAsync import ConnectionAsync

ADDR = ('192.0.2.9', 8812)
OURS = bytes(range(0x20, 0x30))
M, B, BOTH = Endpoints.MULTICAST, Endpoints.BROADCAST, Endpoints.BOTH

class DualConn:
    '''Stands in for a ConnectionAsync running both endpoints.'''
    def __init__(self, dual=True):
        self.is_dual = dual
        self.sent = []
    def transmit(self, data, endpoints=Endpoints.MULTICAST):
        self.sent.append((bytes(data), endpoints))
        return len(data)
    def close(self):
        pass

class Messages(mx_remote.MxrCallbacks):
    def __init__(self):
        self.messages = []
    def on_third_party_message(self, dev, message):
        self.messages.append(message)

def client(dual=True, callbacks=None):
    mx = mx_remote.Remote(open_connection=False, callbacks=callbacks)
    mx._uid = OURS
    mx.conn = DualConn(dual)
    return mx

def uid(n):
    return bytes([n]) * 16

def nm(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def hello(sender, serial, features=DeviceFeature.MESH, protocol=0x2F):
    frame = bytearray(create_mxr_frame(sender, 0x00, struct.pack('<H', protocol) + nm('ONEIP') + nm(serial)
                                       + nm('4.8.0') + struct.pack('<I', int(features))))
    frame[2] = protocol
    return bytes(frame)

def message(sender, n):
    '''A third-party message from sender, distinct per n: each one processed
    shows up once at on_third_party_message.'''
    return create_mxr_frame(sender, 0x55, bytes([0x00, 0x00, 0x1E, 0xC2]) + struct.pack('<I', n))

def opcode_of(frame):
    return int.from_bytes(frame[20:22], 'little')

def call(coro):
    return asyncio.run(coro)

# --- a datagram arriving by both endpoints is acted on once, and proves both paths
seen = Messages()
mx = client(callbacks=seen)
PEER = uid(0x61)
mx.process_frame(1000.0, hello(PEER, 'PA0001'), ADDR, M)
dev = mx.get_by_uid(mx_remote.MxrDeviceUid(PEER))
assert dev is not None
assert dev._heard_multicast is None, 'a device was recorded heard by the hello that made it known'

# A monitoring pulse proves a path, as every frame in a unit's opcode table
# does; the application's message past it proves none, but shows what is acted on.
pulse = create_mxr_frame(PEER, 0x2B, b'')
mx.process_frame(1000.5, pulse, ADDR, M)
assert dev._heard_multicast == 1000.5
mx.process_frame(1000.51, pulse, ADDR, B)
assert dev._heard_broadcast == 1000.51, 'the second copy did not prove its path'

data = message(PEER, 1)
mx.process_frame(1001.0, data, ADDR, M)
assert len(seen.messages) == 1, seen.messages
mx.process_frame(1001.01, data, ADDR, B)
assert len(seen.messages) == 1, 'the second copy was acted on'
mx.process_frame(1001.15, data, ADDR, M)
assert len(seen.messages) == 2, 'a repeat after 100 ms was dropped'
mx.process_frame(1001.15, data, ADDR, None)
mx.process_frame(1001.15, data, ADDR, None)
assert len(seen.messages) == 4, 'one endpoint has no second copies to drop'
print('dup ok    : a second copy within 100 ms is dropped after proving its path')

# --- the duplicate check remembers the last 64 datagrams
seen = Messages()
mx = client(callbacks=seen)
mx.process_frame(2000.0, hello(PEER, 'PA0002'), ADDR, M)
first = message(PEER, 0)
for n in range(64):
    mx.process_frame(2000.0, message(PEER, n), ADDR, M)
mx.process_frame(2000.0, first, ADDR, B)
assert len(seen.messages) == 64, 'a datagram among the last 64 was acted on twice'
mx.process_frame(2000.0, message(PEER, 64), ADDR, M)
mx.process_frame(2000.0, first, ADDR, B)
assert len(seen.messages) == 66, 'a datagram pushed out of the last 64 was still dropped'
print('ring ok   : the duplicate check holds the last 64 datagrams')

# --- a peer not heard by multicast for two minutes needs broadcast too
mx = client()
mx.process_frame(3000.0, hello(PEER, 'PB0001'), ADDR, M)
mx.process_frame(3001.0, hello(PEER, 'PB0002'), ADDR, M)
assert not mx._judge_paths(3002.0)
assert not mx._broadcast_needed and not mx.multicast_fault
mx.process_frame(3110.0, hello(PEER, 'PB0003'), ADDR, B)
assert not mx._judge_paths(3119.0) and not mx._broadcast_needed, 'heard by multicast 118 s ago'
assert mx._judge_paths(3121.0), 'a fault appearing is not reported as a change'
assert mx._broadcast_needed, 'two minutes without multicast'
assert mx.multicast_fault, 'heard by broadcast only'
mx.process_frame(3122.0, hello(PEER, 'PB0004', DeviceFeature.MESH | DeviceFeature.STATUS_REBOOTING), ADDR, B)
assert mx._judge_paths(3122.0), 'a fault clearing is not reported as a change'
assert mx._broadcast_needed and not mx.multicast_fault, 'a peer about to reboot proved a fault'

mx = client()
OTHER = uid(0x62)
mx.process_frame(3000.0, hello(OTHER, 'PB0010', DeviceFeature.MESH | DeviceFeature.STATUS_MCAST_FAULT), ADDR, M)
mx.process_frame(3001.0, hello(OTHER, 'PB0011', DeviceFeature.MESH | DeviceFeature.STATUS_MCAST_FAULT), ADDR, M)
mx._judge_paths(3002.0)
assert mx._broadcast_needed, 'a peer reporting its multicast fault was not reached by broadcast'
assert not mx.multicast_fault

# A peer counts towards the fault only 60 s after it was first heard, and, for
# every peer, 60 s after this client opened its endpoints.
mx = client()
mx.process_frame(4000.0, hello(PEER, 'PG0001'), ADDR, B)
mx.process_frame(4001.0, hello(PEER, 'PG0004'), ADDR, B)    # a known sender's path is recorded
assert mx.get_by_uid(MxrDeviceUid(PEER)).heard_broadcast_lately(4059.0), 'nothing heard by broadcast'
assert not mx._judge_paths(4059.0) and not mx.multicast_fault, 'a fault within 60 s of first hearing the peer'
assert mx._broadcast_needed, 'the grace held back broadcast as well'
mx.process_frame(4060.0, hello(PEER, 'PG0002'), ADDR, B)
assert mx._judge_paths(4060.0) and mx.multicast_fault, '60 s after first hearing the peer'
mx._endpoints_opened = 4100.0
assert mx._judge_paths(4159.0) and not mx.multicast_fault, 'a fault within 60 s of opening the endpoints'
mx.process_frame(4160.0, hello(PEER, 'PG0003'), ADDR, B)
assert mx._judge_paths(4160.0) and mx.multicast_fault, '60 s after opening the endpoints'

# Opening the endpoints, at start or on a changed address, starts the grace.
class Opened:
    def __init__(self, *args, **kw):
        self.is_dual = True
    async def start_srv(self):
        return (None, None)
    def transmit(self, data, endpoints=None):
        return len(data)
    def close(self):
        pass

async def opened():
    import asyncio, mx_remote.remote.Remote as module
    mx = mx_remote.Remote(open_connection=False)
    mx._uid = OURS
    mx._probe_once = lambda: None
    mx.conn = Opened()
    before = time.time()
    await mx.start_async()
    started = mx._endpoints_opened
    mx._endpoints_opened = None
    real, module.ConnectionAsync = module.ConnectionAsync, Opened
    try:
        await mx.update_config(local_ip='192.0.2.77')
    finally:
        module.ConnectionAsync = real
        await mx.close()
    return before, started, mx._endpoints_opened
import asyncio
before, started, moved = asyncio.run(opened())
assert (started is not None) and (started >= before), 'start_async did not start the grace'
assert (moved is not None) and (moved >= before), 'new endpoints did not start the grace'
print('grace ok  : a peer counts towards the fault 60 s after it was first heard or the endpoints opened')

single = client(dual=False)
single.process_frame(3000.0, hello(OTHER, 'PB0012'), ADDR, None)
assert not single._judge_paths(3500.0) and not single._broadcast_needed, 'one endpoint judged paths'
print('judge ok  : broadcast after two silent minutes; the fault needs a broadcast-only peer')

# --- what every unit sends to both goes to both, whatever peers need
mx = client()
def endpoints(opcode, payload, needed=False):
    mx._broadcast_needed = needed
    mx.conn.sent.clear()
    mx.transmit(create_mxr_frame(OURS, opcode, payload))
    return mx.conn.sent[-1][1]
for opcode, payload in ((0x01, b''), (0x28, b''), (0x28, b'\xff'), (0x3A, b''), (0x3A, b'\xff'),
                        (0x2B, b''), (0x21, b''), (0x2C, b'')):
    assert endpoints(opcode, payload) == BOTH, (hex(opcode), payload)
for opcode, payload in ((0x01, uid(5)), (0x28, uid(5)), (0x3A, uid(5)), (0x3B, bytes(40)), (0x55, bytes(8))):
    assert endpoints(opcode, payload) == M, (hex(opcode), payload)
    assert endpoints(opcode, payload, needed=True) == BOTH, (hex(opcode), payload)
print('all ok    : a frame for every unit goes to both; one naming a unit as any other')

# --- the hello reaches broadcast at least every 30 s
mx = client()
def hello_on():
    mx.tx_hello()
    frame, on = mx.conn.sent[-1]
    assert opcode_of(frame) == 0x00
    return on
assert hello_on() == BOTH, 'the first hello'
assert hello_on() == M, 'a hello inside 30 s'
mx._hello_on_broadcast = time.time() - 29
assert hello_on() == M, '29 s after the last'
mx._hello_on_broadcast = time.time() - 30
assert hello_on() == BOTH, '30 s after the last'
assert hello_on() == M
mx._broadcast_needed = True
assert hello_on() == BOTH, 'a peer needing broadcast'
print('hello ok  : on broadcast first, then every 30 s or while a peer needs it')

# --- a frame for one device goes by the endpoint that device is heard by
mx = client()
mx.process_frame(time.time(), hello(PEER, 'PG0001', protocol=0x2A), ADDR, B)
mx.process_frame(time.time(), hello(PEER, 'PG0002', protocol=0x2A), ADDR, B)
dev = mx.get_by_uid(mx_remote.MxrDeviceUid(PEER))
mx._broadcast_needed = False
assert call(dev.ping()) is True
frame, on = mx.conn.sent[-1]
assert (opcode_of(frame), on) == (0x4A, B), 'a ping to a device heard by broadcast alone'
mx.process_frame(time.time(), hello(PEER, 'PG0003', protocol=0x2A), ADDR, M)
mx._broadcast_needed = True
assert call(dev.ping()) is True
assert mx.conn.sent[-1][1] == M, 'a ping to a device heard by multicast'
print('direct ok : a ping goes by the one endpoint its device is heard by')

# --- a multicast fault is announced as soon as it appears
mx = client()
mx.on_datagram_received(hello(PEER, 'MF0001'), ADDR, B)
assert not mx.multicast_fault
mx.get_by_uid(MxrDeviceUid(PEER))._first_heard -= 60    # past its grace
mx.conn.sent.clear()
mx.on_datagram_received(hello(PEER, 'MF0002'), ADDR, B)
hellos = [f for f, _ in mx.conn.sent if opcode_of(f) == 0x00]
assert hellos, 'the fault was not announced when it appeared'
features = DeviceFeature(struct.unpack_from('<I', hellos[-1], 24 + 2 + 48)[0])
assert DeviceFeature.STATUS_MCAST_FAULT in features, features
mx.conn.sent.clear()
mx.on_datagram_received(hello(PEER, 'MF0003'), ADDR, B)
assert not [f for f, _ in mx.conn.sent if opcode_of(f) == 0x00], 'an unchanged fault was announced again'
print('fault ok  : a multicast fault is announced at once, and only on a change')

# --- reboot or factory-reset every unit
mx = client()
for send, opcode, payload in ((mx.reboot_all, 0x28, b'\xff'), (mx.reboot_mesh, 0x28, b''),
                              (mx.factory_reset_all, 0x3A, b'\xff')):
    mx.conn.sent.clear()
    assert call(send()) is True
    (frame, on), = mx.conn.sent
    assert (opcode_of(frame), frame[24:], on) == (opcode, payload, BOTH), (send.__name__, frame.hex(), on)
mx.process_frame(time.time(), hello(PEER, 'PR0001'), ADDR, M)
mx.process_frame(time.time(), hello(PEER, 'PR0002'), ADDR, M)
mx._broadcast_needed = False
mx.conn.sent.clear()
assert call(mx.get_by_uid(mx_remote.MxrDeviceUid(PEER)).reboot()) is True
(frame, on), = mx.conn.sent
assert (opcode_of(frame), frame[24:], on) == (0x28, PEER, M), 'a reboot of one unit went to both'
print('reboot ok : every unit rebooted or reset by both endpoints; one unit as any other')

# --- the transport opens both endpoints, routes by them and names the path
real_broadcast = connection_module.mxr_broadcast_address
connection_module.mxr_broadcast_address = lambda local_ip=None: '192.0.2.255'
try:
    conn = ConnectionAsync(callbacks=None, local_ip='192.0.2.9')
finally:
    connection_module.mxr_broadcast_address = real_broadcast
assert conn.is_dual
assert [(e.target_ip, e.port, e.path) for e in conn.endpoints] == [('224.8.8.8', 8812, M), ('192.0.2.255', 8811, B)]
wire = []
for e in conn.endpoints:
    e.transmit = lambda data, e=e: (wire.append(e.path), len(data))[1]
conn._closed = False
for asked, went in ((M, [M]), (B, [B]), (BOTH, [M, B])):
    wire.clear()
    assert conn.transmit(b'x' * 30, asked) == 30
    assert wire == went, (asked, wire)

class Heard:
    def __init__(self):
        self.paths = []
    def on_datagram_received(self, data, addr, path=None):
        self.paths.append(path)
heard = Heard()
conn._callbacks = heard
conn.endpoints[1].datagram_received(b'x', ADDR)
assert heard.paths == [B]

one = ConnectionAsync(callbacks=heard, local_ip='192.0.2.9', target_ip='239.255.77.90', port=18890)
assert not one.is_dual
assert [(e.target_ip, e.port) for e in one.endpoints] == [('239.255.77.90', 18890)]
one.endpoints[0].datagram_received(b'x', ADDR)
assert heard.paths == [B, None], 'one endpoint named a path'
wire.clear()
one.endpoints[0].transmit = lambda data: (wire.append('one'), len(data))[1]
one._closed = False
assert one.transmit(b'x', B) == 1 and wire == ['one'], 'one endpoint did not send everything by it'
print('conn ok   : both endpoints open, each frame leaves by the ones asked')

# --- a selected interface is the only one datagrams are taken from
# The datagram goes to 127.0.0.1, so it arrives on lo. An endpoint on lo takes
# it, and one on the host's other interface does not; an endpoint on no
# interface in particular takes it first, which proves the host delivers it to
# that port at all. Linux only: elsewhere nothing reports the arrival
# interface.
ARRIVAL_PORT = 18820
arrivals = []
async def arrives(local_ip):
    got = []
    class Taking:
        def on_datagram_received(self, data, addr, path=None):
            got.append(data)
        def on_connection_made(self):
            pass
    conn = ConnectionAsync(callbacks=Taking(), local_ip=local_ip, target_ip='127.0.0.1', port=ARRIVAL_PORT)
    # The sending socket on a port of its own: bound to the selected address at
    # the arrival port, it would take the unicast this sends ahead of the
    # receiving one.
    for e in conn.endpoints:
        e._create_tx_socket = lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    await conn.start_srv()
    arrivals.append(conn.endpoints[0].arrival)
    try:
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sender.sendto(b'ping', ('127.0.0.1', ARRIVAL_PORT))
        sender.close()
        for _ in range(100):
            if got:
                break
            await asyncio.sleep(0.02)
    finally:
        conn.close()
    return got == [b'ping']

if sys.platform.startswith('linux'):
    others = [a for a in mx_remote.Interface.mxr_valid_addresses()]
    if not asyncio.run(arrives(None)):
        print('arrive    : skipped, the host does not deliver to the arrival port')
    elif not others:
        print('arrive    : skipped, the host has no interface besides loopback')
    else:
        assert arrivals == [None], f'no address selected, yet confined to {arrivals}'
        assert asyncio.run(arrives('127.0.0.1')), 'dropped on its own interface'
        assert not asyncio.run(arrives(others[0])), f"taken from {others[0]}'s interface by way of lo"
        try:
            asyncio.run(arrives('192.0.2.250'))
            raise AssertionError('opened on an address no interface holds')
        except OSError as e:
            assert 'no interface holds' in str(e), e
        print('arrive    : only from the selected interface, and none for an address no interface holds')

# --- an interface only announced on gets the hellos, less what invites action
from mx_remote.remote.Remote import announced_only
from mx_remote.remote.ConnectionAsync import Announcer
kept = (DeviceFeature.CONFIG_INITIALISED | DeviceFeature.MESH | DeviceFeature.MESH_MEMBER
        | DeviceFeature.SETUP_COMPLETED | DeviceFeature.STATUS_MCAST_FAULT)
for invites in (DeviceFeature.MANAGER, DeviceFeature.MESH_MASTER, DeviceFeature.OSD_SYNC):
    assert announced_only(kept | invites) == kept, f'{invites!r} kept'
# An interface without an address is sent nothing, and that is no error: it is
# how an interface waiting on DHCP looks.
absent = Announcer('mxr-absent0')
assert absent.announce(b'ping', [('224.8.8.8', 8812)]) == 0 and absent._bound is None

# Live: the announced interface is the one the endpoint is on too, so one
# listener hears both, told apart by the port they come from.
import netifaces
ANNOUNCED = ('239.255.77.92', 18823)
def interface_holding(address):
    return next((n for n in netifaces.interfaces()
                 if any(e.get('addr') == address for e in netifaces.ifaddresses(n).get(netifaces.AF_INET, []))), None)

async def announced(later):
    local = mx_remote.Interface.mxr_valid_addresses()[0]
    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(('', ANNOUNCED[1]))
    listener.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(ANNOUNCED[0]) + socket.inet_aton(local))
    listener.settimeout(0.1)
    names = [interface_holding(local)]
    mx = mx_remote.Remote(target_ip=ANNOUNCED[0], port=ANNOUNCED[1], local_ip=local, osd_sync=True,
                          dedicated_controller=True, announce_interfaces=([] if later else names))
    mx._uid = bytes(range(0x70, 0x80))
    mx._probe_once = lambda: None
    await mx.start_async()
    if later:
        mx.set_announce_interfaces(names)
    seen = {}
    deadline = time.time() + 2
    try:
        wanted = {(0x00, True), (0x00, False), (0x58, False)}
        while (time.time() < deadline) and not wanted.issubset(seen):
            try:
                frame, (_, port) = listener.recvfrom(2048)
            except socket.timeout:
                continue
            by_endpoint = (port == ANNOUNCED[1])
            seen.setdefault((opcode_of(frame), by_endpoint), frame)
    finally:
        listener.close()
        await mx.close()
    return seen

if mx_remote.Interface.mxr_valid_addresses():
    for later in (False, True):
        seen = asyncio.run(announced(later))
        if (0x00, True) not in seen:
            print('announce  : skipped, no multicast loopback delivery')
            break
        endpoint = DeviceFeature(struct.unpack_from('<I', seen[(0x00, True)], 24 + 50)[0])
        assert DeviceFeature.OSD_SYNC in endpoint and DeviceFeature.MANAGER in endpoint, repr(endpoint)
        assert (0x00, False) in seen, f'no hello from the announcing socket (named later: {later})'
        only = DeviceFeature(struct.unpack_from('<I', seen[(0x00, False)], 24 + 50)[0])
        assert DeviceFeature.OSD_SYNC not in only and DeviceFeature.MANAGER not in only, repr(only)
        assert DeviceFeature.CONFIG_INITIALISED in only, repr(only)
        assert (0x58, False) in seen, f'no CONTROLLER_STATE hello from the announcing socket (named later: {later})'
    else:
        print('announce  : the hellos alone on an interface only announced on, from the start or named later')

# A socket bound to an address the interface no longer holds is rebound.
if mx_remote.Interface.mxr_valid_addresses():
    local = mx_remote.Interface.mxr_valid_addresses()[0]
    moved = Announcer(interface_holding(local))
    stale = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    moved._bound = ('192.0.2.250', stale)
    assert moved.announce(b'ping', [('239.255.77.89', 18825)]) == 4
    assert moved._bound[0] == local and stale.fileno() == -1, moved._bound
    moved.close()

# The frame leaves by the named interface, not the one multicast is routed by:
# an interface a plain socket's multicast does not reach is the proof.
PINNED = ('239.255.77.88', 18826)
def reaches(address, send):
    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(('', PINNED[1]))
    listener.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(PINNED[0]) + socket.inet_aton(address))
    listener.settimeout(0.3)
    try:
        send()
        while True:
            data, _ = listener.recvfrom(64)
            if data == b'pinned':
                return True
    except socket.timeout:
        return False
    finally:
        listener.close()
def plain_send():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(b'pinned', PINNED)
    s.close()
elsewhere = [a for a in mx_remote.Interface.mxr_valid_addresses() if not reaches(a, plain_send)]
if elsewhere:
    pinned = Announcer(interface_holding(elsewhere[0]))
    assert reaches(elsewhere[0], lambda: pinned.announce(b'pinned', [PINNED])), f'not sent by {pinned.interface}'
    pinned.close()
    print('pinned    : an announcer sends by its own interface, rebinding when its address moves')
else:
    print('pinned    : skipped, multicast reaches every interface unpinned')

# --- the broadcast option is accepted, ignored and deprecated
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter('always')
    mx = mx_remote.Remote(open_connection=False, broadcast=True)
assert any(issubclass(w.category, DeprecationWarning) for w in caught)
assert mx.target_ip == '224.8.8.8' and mx.port == 8812
print('compat ok : Remote(broadcast=...) warns and runs both endpoints')

print('ALL OK')
