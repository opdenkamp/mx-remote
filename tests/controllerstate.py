#!/usr/bin/env python3
'''CONTROLLER_STATE (0x58): the hello with which a dedicated mesh controller,
such as a router, marks itself.

Each layout is composed here from the firmware's, byte by byte, so it rules out
a slip in the builders and decoders, not a shared misreading of the layout.'''

import asyncio, os, struct, sys, logging, time
from datetime import timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import DeviceFeature as D, MxrDeviceUid
from mx_remote.Interface import ControllerHello, ControllerPart
from mx_remote.proto.Constants import (CONTROLLER_PARTS_MAX, MXR_OPCODE_VERSIONS, MXR_PROTOCOL_VERSION,
                                       ControllerRole)
from mx_remote.proto.Factory import create_mxr_frame
from mx_remote.proto.FrameControllerState import FrameControllerState, StateHeader
import zlib

ADDR = ('192.0.2.9', 8812)

class Seen(mx_remote.MxrCallbacks):
    def __init__(self):
        self.events = []
    def on_controller_hello_changed(self, dev, hello):
        self.events.append(('hello', dev.remote_id, hello))
    def on_controller_part_received(self, dev, part, generation, data):
        self.events.append(('received', dev.remote_id, part, generation, data))
    def on_controller_part_failed(self, dev, part, generation):
        self.events.append(('failed', dev.remote_id, part, generation))
    def of(self, kind):
        return [e for e in self.events if e[0] == kind]

def client(own=bytes(range(0x20, 0x30)), **kw):
    seen = Seen()
    mx = mx_remote.Remote(open_connection=False, callbacks=seen, **kw)
    mx._uid = own
    mx.sent = []
    mx.transmit = lambda data, to=None: (mx.sent.append(bytes(data)), len(data))[1]
    return mx, seen

def uid(n):
    return bytes([n]) * 16

def U(n):
    return MxrDeviceUid(uid(n))

def name(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def rx(mx, sender, opcode, payload=b'', protocol=0x34):
    frame = bytearray(create_mxr_frame(sender, opcode, payload))
    frame[2] = protocol
    mx.process_frame(time.time(), bytes(frame), ADDR)

def hello(mx, sender, features=D.MESH, protocol=0x34):
    rx(mx, sender, 0x00, struct.pack('<H', protocol) + name('Router') + name('SH%04d' % sender[0]) + name('1.0')
                       + struct.pack('<I', int(features)), protocol=0x01)
    return mx.get_by_uid(MxrDeviceUid(sender))

def call(coro):
    return asyncio.run(coro)

def sent(mx, opcode):
    '''The payloads mx sent of opcode, each checked for its stamp.'''
    out = []
    for f in mx.sent:
        if int.from_bytes(f[20:22], 'little') == opcode:
            assert f[2] == MXR_OPCODE_VERSIONS[opcode], (hex(opcode), f[2])
            out.append(f[24:])
    return out

assert MXR_PROTOCOL_VERSION == 0x34, hex(MXR_PROTOCOL_VERSION)
assert MXR_OPCODE_VERSIONS[0x58] == 0x34
print('versions    : 0x58 stamped 0x34, announced 0x34')

# ------------------------------------------------------------------ the hello

def controller_hello(version, kind, role, primary, parts, generation=0x01020304):
    '''A hello, byte by byte: the header, role, part count, two reserved bytes
    poisoned, the primary and one entry per part.'''
    p = bytes([version, kind, 0, 0xA5]) + struct.pack('<I', generation) + bytes(12)
    p += bytes([role, len(parts), 0xA5, 0xA5]) + primary
    for part, length, crc in parts:
        p += bytes([part, 0xA5, 0xA5, 0xA5]) + struct.pack('<II', length, crc)
    return p

# Built as routers.md lays it out.
mx, _ = client()
built = FrameControllerState.construct_hello(mx, ControllerHello(
    role=ControllerRole.PRIMARY, generation=0x11223344, primary=U(0x5A),
    parts=(ControllerPart(part=2, length=0x0A0B, crc=0xDEADBEEF),)))
assert built.payload == (bytes([1, 0, 0, 0]) + struct.pack('<I', 0x11223344) + bytes(12) + bytes([1, 1, 0, 0])
                         + uid(0x5A) + bytes([2, 0, 0, 0]) + struct.pack('<II', 0x0A0B, 0xDEADBEEF)), built.payload.hex()
# The default: role 0, no primary, no parts, 40 bytes.
built = FrameControllerState.construct_hello(mx, ControllerHello())
assert built.payload == bytes([1]) + bytes(39), built.payload.hex()
# Only the first five parts are sent.
built = FrameControllerState.construct_hello(mx, ControllerHello(parts=(ControllerPart(0, 0, 0),) * 7))
assert built.payload[21] == CONTROLLER_PARTS_MAX and len(built.payload) == 40 + 5 * 12, built.payload.hex()
print('build       : header, role, part count, primary, 12 bytes a part, five at most')

# A hello (version 1, kind 0, 40 bytes or more) from a known sender marks it as
# a dedicated controller; one of another version or kind, or shorter, is
# dropped, as is a stranger's.
mx, seen = client()
rx(mx, uid(84), 0x58, controller_hello(1, 0, 1, uid(84), []))
assert mx.get_by_uid(U(84)) is None, 'a stranger registered'
router = hello(mx, uid(84))
for what, payload in (('version 2', controller_hello(2, 0, 1, uid(84), [])),
                      ('a request', controller_hello(1, 1, 1, uid(84), [])),
                      ('39 bytes', controller_hello(1, 0, 1, uid(84), [])[:39])):
    rx(mx, uid(84), 0x58, payload)
    assert router.controller_hello is None, what
    assert not router.dedicated_controller, what
p = controller_hello(1, 0, 2, uid(85), [(0, 0x1234, 0xCAFEF00D), (3, 0x0800, 0x0BADBEEF)])
# A part entry cut short is left out.
p += bytes([4, 0, 0, 0, 1])
p = p[:21] + bytes([3]) + p[22:]
rx(mx, uid(84), 0x58, p)
expected = ControllerHello(role=ControllerRole.FAILSAFE, generation=0x01020304, primary=U(85),
                           parts=(ControllerPart(0, 0x1234, 0xCAFEF00D), ControllerPart(3, 0x0800, 0x0BADBEEF)))
assert router.controller_hello == expected, router.controller_hello
assert router.dedicated_controller
assert seen.of('hello') == [('hello', U(84), expected)], seen.events
rx(mx, uid(84), 0x58, p)
assert len(seen.of('hello')) == 1, 'the same hello again reported'
# A count below the entries present reads that many.
rx(mx, uid(84), 0x58, controller_hello(1, 0, 2, uid(85), [(0, 1, 2), (3, 4, 5)])[:21] + bytes([1])
                       + controller_hello(1, 0, 2, uid(85), [(0, 1, 2), (3, 4, 5)])[22:])
assert router.controller_hello.parts == (ControllerPart(0, 1, 2),), router.controller_hello.parts
# A role without a name passes through, and a zero primary is none.
rx(mx, uid(84), 0x58, controller_hello(1, 0, 9, bytes(16), []))
assert router.controller_hello.role == 9 and router.controller_hello.primary is None, router.controller_hello
print('read        : a known sender\'s hello of version 1, kind 0, 40 bytes or more')

# ---------------------------------------------------------- this client's own

# A dedicated controller follows its 54-byte hello with a CONTROLLER_STATE
# hello, which marks it as one to a peer; any other client sends the hello
# alone.
for dedicated in (False, True):
    mx, _ = client(dedicated_controller=dedicated)
    mx.tx_hello()
    assert [int.from_bytes(f[20:22], 'little') for f in mx.sent] == ([0x00, 0x58] if dedicated else [0x00])
    assert len(mx.sent[0]) - 24 == 54, 'the hello'
    peer, _ = client()
    peer._uid = uid(0x70)
    for f in mx.sent:
        peer.process_frame(time.time(), f, ADDR)
    seen_as = peer.get_by_uid(MxrDeviceUid(mx.uid))
    assert seen_as.dedicated_controller == dedicated
    assert seen_as.controller_hello == (ControllerHello() if dedicated else None), seen_as.controller_hello
print('own hello   : a dedicated controller follows its hello with one, read back by a peer')

# The controller hello follows a hello at most every 10 s, and goes at once when
# the application changes it, but not when it sets the same one again.
mx, _ = client(dedicated_controller=True)
mx.tx_hello()
assert len(sent(mx, 0x58)) == 1, 'after the first hello'
mx.tx_hello()
assert len(sent(mx, 0x58)) == 1, 'within 10 s of the last'
mx._own_controller.sent -= 10
mx.tx_hello()
assert len(sent(mx, 0x58)) == 2, '10 s after the last'
assert mx.set_controller_role(ControllerRole.PRIMARY, mx.uid) is True
assert len(sent(mx, 0x58)) == 3, 'at once on a change'
p = sent(mx, 0x58)[-1]
assert p[20] == 1 and p[24:40] == mx.uid.byte_value, p.hex()
assert mx.set_controller_role(ControllerRole.PRIMARY, mx.uid) is True
assert len(sent(mx, 0x58)) == 3, 'the same one again'
assert mx.set_controller_role(ControllerRole.PRIMARY, U(9)) is True
assert len(sent(mx, 0x58)) == 4, 'another primary'
# A new socket sends one with its first hello.
mx._own_controller.sent = None
mx.tx_hello()
assert len(sent(mx, 0x58)) == 5, 'after the first hello on a new socket'

# New sockets, from start_async() or a changed address, send one with their
# first hello, however recently the last went out.
class FakeConn:
    def __init__(self, *args, **kw):
        self.sent = []
    async def start_srv(self):
        return (None, None)
    def transmit(self, data, endpoints=None):
        self.sent.append(bytes(data))
        return len(data)
    def close(self):
        pass

def opcodes(frames):
    return [int.from_bytes(f[20:22], 'little') for f in frames]

async def reopened():
    import mx_remote.remote.Remote as module
    mx = mx_remote.Remote(open_connection=False, dedicated_controller=True)
    mx._uid = bytes(range(0x40, 0x50))
    mx._probe_once = lambda: None
    mx.conn = FakeConn()
    mx._own_controller.sent = time.time()
    await mx.start_async()
    started = opcodes(mx.conn.sent)
    real, module.ConnectionAsync = module.ConnectionAsync, FakeConn
    try:
        await mx.update_config(local_ip='192.0.2.77')
        mx.tx_hello()
        moved = opcodes(mx.conn.sent)
    finally:
        module.ConnectionAsync = real
        await mx.close()
    return started, moved
started, moved = asyncio.run(reopened())
assert 0x58 in started, [hex(o) for o in started]
assert moved == [0x00, 0x58], [hex(o) for o in moved]

plain, _ = client()
assert plain.set_controller_role(ControllerRole.PRIMARY) is False
assert plain.sent == [], 'a refused role sent anyway'
print('own timing  : every 10 s behind a hello, at once on a change, refused unless dedicated')

# ------------------------------------------------- pulling another's state

def crc32(b):
    return zlib.crc32(b) & 0xFFFFFFFF

def state(n):
    return bytes((i * 7) % 251 for i in range(n))

def frames_of(mx):
    """The CONTROLLER_STATE frames mx sent since the last call."""
    out = [f for f in mx.sent if int.from_bytes(f[20:22], 'little') == 0x58]
    mx.sent.clear()
    return out

def header(frame):
    return StateHeader.decode(frame[24:])

def deliver(frames, to):
    for f in frames:
        to.process_frame(time.time(), f, ADDR)

class Pair:
    """A primary leading its mesh, and a failsafe following it, each having had
    the other's hello and controller hello."""
    def __init__(self):
        self.primary, _ = client(own=uid(0x60), dedicated_controller=True)
        self.failsafe, self.seen = client(own=uid(0x61), dedicated_controller=True)
        self.primary.tx_hello()
        self.failsafe.tx_hello()
        p, f = list(self.primary.sent), list(self.failsafe.sent)
        deliver(p, self.failsafe)
        deliver(f, self.primary)
        self.primary.set_mesh_controller(self.primary.uid)
        self.failsafe.set_mesh_controller(self.primary.uid)
        # The primary knows the failsafe follows it from its membership
        # report; here it is told outright.
        self.primary.get_by_uid(self.failsafe.uid).mesh_master = self.primary.uid
        self.primary.sent.clear()
        self.failsafe.sent.clear()
        self.from_primary = self.failsafe.get_by_uid(self.primary.uid)

    def pump(self):
        for _ in range(64):
            asks, data = frames_of(self.failsafe), frames_of(self.primary)
            if not asks and not data:
                return
            deliver(asks, self.primary)
            deliver(data, self.failsafe)
        raise AssertionError('the pull never settled')

    def received(self):
        return self.seen.of('received')

    def failed(self):
        return self.seen.of('failed')

P = U(0x60)

# A part is pulled in windows of 8192 bytes, in frames of 1024.
pair = Pair()
data = state(20000)
assert pair.primary.set_controller_parts(3, [(0, data)]) is True
frames_of(pair.primary)
assert call(pair.failsafe.pull_controller_part(pair.from_primary, 0, 3, 20000, crc32(data))) is True
asks = frames_of(pair.failsafe)
assert len(asks) == 1
ask = header(asks[0])
assert (ask.kind, ask.part, ask.generation, ask.offset, ask.length) == (1, 0, 3, 0, 8192), ask
assert len(asks[0]) - 24 == 20, 'a request is the header alone'
deliver(asks, pair.primary)
answer = frames_of(pair.primary)
assert len(answer) == 8, 'the window in frames of 1024'
for i, f in enumerate(answer):
    h = header(f)
    assert (h.kind, h.offset, h.length, h.crc) == (2, i * 1024, 20000, crc32(data)), h
    assert f[24 + 20:] == data[i * 1024:(i + 1) * 1024]
deliver(answer, pair.failsafe)
nxt = frames_of(pair.failsafe)
assert len(nxt) == 1, 'the next window once this one is in'
assert (header(nxt[0]).offset, header(nxt[0]).length) == (8192, 8192)
deliver(nxt, pair.primary)
pair.pump()
assert pair.received() == [('received', P, 0, 3, data)], [e[:4] for e in pair.received()]
assert pair.failed() == []

# A lost frame ends the window, which is asked again from there, once.
pair = Pair()
data = state(5000)
pair.primary.set_controller_parts(1, [(0, data)])
frames_of(pair.primary)
call(pair.failsafe.pull_controller_part(pair.from_primary, 0, 1, 5000, crc32(data)))
deliver(frames_of(pair.failsafe), pair.primary)
answer = frames_of(pair.primary)
assert len(answer) == 5
del answer[1]
deliver(answer, pair.failsafe)
asks = frames_of(pair.failsafe)
assert len(asks) == 1, 'once, however many frames followed the gap'
assert header(asks[0]).offset == 1024
deliver(asks, pair.primary)
pair.pump()
assert pair.received() == [('received', P, 0, 1, data)]

# A pull asks again after 2 s without data.
pair = Pair()
call(pair.failsafe.pull_controller_part(pair.from_primary, 0, 1, 100, crc32(state(100))))
assert len(frames_of(pair.failsafe)) == 1
now = time.time()
pair.failsafe._check_controller_pulls(now + 1)
assert frames_of(pair.failsafe) == [], 'within 2 s'
pair.failsafe._check_controller_pulls(now + 3)
asks = frames_of(pair.failsafe)
assert len(asks) == 1 and header(asks[0]).offset == 0

# It gives up after ten asks without progress.
pair = Pair()
call(pair.failsafe.pull_controller_part(pair.from_primary, 0, 1, 100, 0x1234))
now = time.time()
for _ in range(11):
    now += 2
    pair.failsafe._check_controller_pulls(now)
assert len(frames_of(pair.failsafe)) == 11, 'the first and ten more'
assert pair.failed() == [('failed', P, 0, 1)], pair.failed()

# And at once when its device goes offline.
pair = Pair()
call(pair.failsafe.pull_controller_part(pair.from_primary, 0, 1, 100, 0x1234))
pair.from_primary._last_ping -= timedelta(seconds=pair.from_primary.offline_window)
pair.failsafe._check_controller_pulls(time.time())
assert pair.failed() == [('failed', P, 0, 1)], pair.failed()
frames_of(pair.failsafe)
refused = call(pair.failsafe.pull_controller_part(pair.from_primary, 0, 1, 100, 0x1234))
assert refused is False and frames_of(pair.failsafe) == [], 'a pull from an offline device'

# A generation no longer held ends the pull.
pair = Pair()
data = state(3000)
pair.primary.set_controller_parts(1, [(0, data)])
pair.primary.set_controller_parts(2, [(0, state(10))])
frames_of(pair.primary)
call(pair.failsafe.pull_controller_part(pair.from_primary, 0, 1, 3000, crc32(data)))
deliver(frames_of(pair.failsafe), pair.primary)
answer = frames_of(pair.primary)
assert len(answer) == 1, 'one frame without bytes'
assert header(answer[0]).generation == 2 and len(answer[0]) - 24 == 20
deliver(answer, pair.failsafe)
assert pair.failed() == [('failed', P, 0, 1)]
assert frames_of(pair.failsafe) == []

# A part other than the one asked for ends the pull.
pair = Pair()
pair.primary.set_controller_parts(1, [(0, state(300))])
frames_of(pair.primary)
call(pair.failsafe.pull_controller_part(pair.from_primary, 0, 1, 300, 0xBAD))
pair.pump()
assert pair.failed() == [('failed', P, 0, 1)] and pair.received() == []

# Data sent straight to a pull, as the primary would send it.
def data_frame(pair, generation, offset, length, crc, data, part=0):
    rx(pair.failsafe, pair.primary.uid.byte_value, 0x58,
       StateHeader(kind=2, part=part, generation=generation, offset=offset, length=length, crc=crc).encode() + data)
    return frames_of(pair.failsafe)

def pulling(length, crc, generation=1):
    pair = Pair()
    call(pair.failsafe.pull_controller_part(pair.from_primary, 0, generation, length, crc))
    frames_of(pair.failsafe)
    return pair

# Bytes of another generation end the window, which is asked again; the pull
# goes on.
data = state(3000)
pair = pulling(3000, crc32(data))
asks = data_frame(pair, 2, 0, 3000, crc32(data), data[:1024])
assert len(asks) == 1 and header(asks[0]).offset == 0 and pair.failed() == [], (asks, pair.failed())
# A part of another length than its hello said fails on its first frame.
pair = pulling(20000, crc32(data))
assert data_frame(pair, 1, 0, 3000, crc32(data), data[:1024]) == []
assert pair.failed() == [('failed', P, 0, 1)], pair.failed()
# So does one of another crc32.
data = state(3000)
pair = pulling(3000, crc32(data))
assert data_frame(pair, 1, 0, 3000, crc32(data) ^ 1, data[:1024]) == []
assert pair.failed() == [('failed', P, 0, 1)], pair.failed()
# A frame without bytes of the current generation, where bytes were due, asks
# again.
pair = pulling(3000, crc32(data))
asks = data_frame(pair, 1, 0, 3000, crc32(data), b'')
assert len(asks) == 1 and header(asks[0]).offset == 0 and pair.failed() == [], asks
# Bytes past the end of the part are left out.
data = state(100)
pair = pulling(100, crc32(data))
data_frame(pair, 1, 0, 100, crc32(data), data + b'\xA5' * 50)
assert pair.received() == [('received', P, 0, 1, data)], pair.received()
# A part whose bytes do not match the crc32 its header gives fails once whole.
pair = pulling(100, crc32(data))
data_frame(pair, 1, 0, 100, crc32(data), b'\xA5' + data[1:])
assert pair.failed() == [('failed', P, 0, 1)] and pair.received() == [], pair.failed()
# A gap after an answer that started again is asked again at once.
data = state(5000)
pair = pulling(5000, crc32(data))
assert len(data_frame(pair, 1, 1024, 5000, crc32(data), data[1024:2048])) == 1, 'the first gap'
assert data_frame(pair, 1, 0, 5000, crc32(data), data[:1024]) == []
assert len(data_frame(pair, 1, 2048, 5000, crc32(data), data[2048:3072])) == 1, 'a second gap'

# A pull of a part already being pulled replaces it.
data = state(100)
pair = pulling(100, 0x1234)
call(pair.failsafe.pull_controller_part(pair.from_primary, 0, 2, 100, crc32(data)))
frames_of(pair.failsafe)
data_frame(pair, 2, 0, 100, crc32(data), data)
assert pair.received() == [('received', P, 0, 2, data)], pair.received()
# Data of the same part from another device is no part of the pull.
pair = pulling(100, crc32(data))
other, _ = client(own=uid(0x67), dedicated_controller=True)
other.tx_hello()
deliver(other.sent, pair.failsafe)
pair.failsafe.allow_controller_state(other.uid)
frames_of(pair.failsafe)
rx(pair.failsafe, uid(0x67), 0x58, StateHeader(kind=2, generation=1, length=100, crc=crc32(data)).encode() + data)
assert pair.received() == [], 'taken from another device'
# Pulls of other parts, and of other devices, run alongside.
pair = Pair()
a, b = state(3000), state(50)
pair.primary.set_controller_parts(1, [(0, a), (2, b)])
frames_of(pair.primary)
call(pair.failsafe.pull_controller_part(pair.from_primary, 0, 1, 3000, crc32(a)))
call(pair.failsafe.pull_controller_part(pair.from_primary, 2, 1, 50, crc32(b)))
other, _ = client(own=uid(0x67), dedicated_controller=True)
other.tx_hello()
deliver(other.sent, pair.failsafe)
pair.failsafe.allow_controller_state(other.uid)
call(pair.failsafe.pull_controller_part(pair.failsafe.get_by_uid(other.uid), 0, 1, 50, crc32(b)))
rx(pair.failsafe, uid(0x67), 0x58, StateHeader(kind=2, generation=1, length=50, crc=crc32(b)).encode() + b)
pair.pump()
assert sorted((e[1].byte_value, e[2], e[3]) for e in pair.received()) == [(uid(0x60), 0, 1), (uid(0x60), 2, 1), (uid(0x67), 0, 1)], pair.received()

# The probe loop asks again.
pair = pulling(100, crc32(data))
pair.failsafe._controller_pulls[0].last -= 3
pair.failsafe._probe_once()
assert [header(f).kind for f in frames_of(pair.failsafe) if header(f).kind != 0] == [1], 'no ask from the probe loop'

# An empty part arrives at once, or fails at once against another crc.
pair = Pair()
call(pair.failsafe.pull_controller_part(pair.from_primary, 4, 9, 0, crc32(b'')))
call(pair.failsafe.pull_controller_part(pair.from_primary, 3, 9, 0, 1))
assert frames_of(pair.failsafe) == []
assert pair.received() == [('received', P, 4, 9, b'')] and pair.failed() == [('failed', P, 3, 9)]
print('pull        : windows of 8192 in frames of 1024, asked again on a gap or 2 s, ended on failure')

# A request past the end, and one for a part not held, get one frame with no
# bytes; a window is never more than 8192 bytes.
pair = Pair()
pair.primary.set_controller_parts(5, [(0, state(9000)), (2, state(10))])
frames_of(pair.primary)
def ask(part, offset, length, sender=pair.failsafe):
    rx(pair.primary, sender.uid.byte_value, 0x58,
       StateHeader(kind=1, part=part, generation=5, offset=offset, length=length).encode())
    return frames_of(pair.primary)
assert len(ask(0, 0, 20000)) == 8, '8192 bytes at most'
answer = ask(0, 8192, 8192)
assert len(answer) == 1 and len(answer[0]) - 24 - 20 == 9000 - 8192
answer = ask(0, 9000, 100)
assert len(answer) == 1 and len(answer[0]) - 24 == 20 and header(answer[0]).length == 9000, 'past the end'
answer = ask(3, 0, 100)
assert len(answer) == 1 and header(answer[0]).length == 0, 'a part not held'
answer = ask(2, 4, 100)
assert len(answer) == 1 and answer[0][24 + 20:] == state(10)[4:]
# The hello lists each part's length and crc32 under its generation.
pair.primary._own_controller.sent = None
pair.primary.tx_hello()
listed = frames_of(pair.primary)[-1][24:]
assert listed[4:8] == struct.pack('<I', 5) and listed[21] == 2, listed.hex()
assert listed[40:52] == bytes([0, 0, 0, 0]) + struct.pack('<II', 9000, crc32(state(9000))), listed[40:52].hex()
assert listed[52:64] == bytes([2, 0, 0, 0]) + struct.pack('<II', 10, crc32(state(10))), listed[52:64].hex()

# A request is answered only for a dedicated controller of this client's mesh,
# or the one allowed.
stranger, _ = client(own=uid(0x62), dedicated_controller=True)
stranger.tx_hello()
deliver(stranger.sent, pair.primary)
frames_of(pair.primary)
assert ask(0, 0, 10, stranger) == [], 'of no mesh'
pair.primary.allow_controller_state(stranger.uid)
assert len(ask(0, 0, 10, stranger)) == 1, 'allowed'
pair.primary.allow_controller_state(None)
assert ask(0, 0, 10, stranger) == [], 'no longer'
# The mesh's controller itself is taken from.
pair.failsafe.set_controller_parts(1, [(0, state(10))])
frames_of(pair.failsafe)
rx(pair.failsafe, pair.primary.uid.byte_value, 0x58, StateHeader(kind=1, generation=1, length=10).encode())
assert len(frames_of(pair.failsafe)) == 1, 'a request from the controller this client follows'

# A request from a device that sent no controller hello is dropped, even from
# the mesh's own controller.
lone, _ = client(own=uid(0x63), dedicated_controller=True)
unit = hello(lone, uid(0x64))
lone.set_mesh_controller(U(0x64))
lone.set_controller_parts(1, [(0, state(10))])
lone.sent.clear()
rx(lone, uid(0x64), 0x58, StateHeader(kind=1, generation=1, length=10).encode())
assert frames_of(lone) == []
# Nor from a dedicated controller of no mesh to a client in none.
outside, _ = client(own=uid(0x68), dedicated_controller=True)
hello(outside, uid(0x69))
rx(outside, uid(0x69), 0x58, controller_hello(1, 0, 1, uid(0x69), []))
outside.set_controller_parts(1, [(0, state(10))])
outside.sent.clear()
rx(outside, uid(0x69), 0x58, StateHeader(kind=1, generation=1, length=10).encode())
assert frames_of(outside) == [], 'answered with neither in a mesh'
# Nor does a client that is no dedicated controller answer one.
plain, _ = client(own=uid(0x65))
hello(plain, uid(0x66))
rx(plain, uid(0x66), 0x58, controller_hello(1, 0, 1, uid(0x66), []))
plain.allow_controller_state(U(0x66))
plain.sent.clear()
rx(plain, uid(0x66), 0x58, StateHeader(kind=1, generation=0, length=10).encode())
assert frames_of(plain) == [], 'answered by a client that is no dedicated controller'
print('serve       : the window asked, nothing past the end, only to a controller of the mesh or the one allowed')

# Parts the hello can't list, or lists ambiguously, are refused.
remote, _ = client(dedicated_controller=True)
assert remote.set_controller_parts(1, [(p, bytes([p])) for p in range(6)]) is False
assert remote.set_controller_parts(1, [(1, b'1'), (1, b'2')]) is False
assert remote.set_controller_parts(1, [(256, b'1')]) is False
assert remote.sent == [], 'refused parts sent anyway'
assert remote.set_controller_parts(1, [(p, bytes([p])) for p in range(5)]) is True
assert len(sent(remote, 0x58)) == 1, 'at once on a change'
assert remote.set_controller_parts(1, [(p, bytes([p])) for p in range(5)]) is True
assert len(sent(remote, 0x58)) == 1, 'the same parts again'
assert remote.set_controller_parts(2, [(p, bytes([p])) for p in range(5)]) is True
assert len(sent(remote, 0x58)) == 2, 'another generation'
assert plain.set_controller_parts(1, []) is False, 'a client that is no dedicated controller'
print('parts       : five at most, each once, sent at once on a change')

print('ALL OK')
