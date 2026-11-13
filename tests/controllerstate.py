#!/usr/bin/env python3
'''CONTROLLER_STATE (0x58): the hello with which a dedicated mesh controller,
such as a router, marks itself.

Each layout is composed here from the firmware's, byte by byte, so it rules out
a slip in the builders and decoders, not a shared misreading of the layout.'''

import asyncio, os, struct, sys, logging, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import DeviceFeature as D, MxrDeviceUid
from mx_remote.Interface import ControllerHello, ControllerPart
from mx_remote.proto.Constants import (CONTROLLER_PARTS_MAX, MXR_OPCODE_VERSIONS, MXR_PROTOCOL_VERSION,
                                       ControllerRole)
from mx_remote.proto.Factory import create_mxr_frame
from mx_remote.proto.FrameControllerState import FrameControllerState

ADDR = ('192.0.2.9', 8812)

class Seen(mx_remote.MxrCallbacks):
    def __init__(self):
        self.events = []
    def on_controller_hello_changed(self, dev, hello):
        self.events.append(('hello', dev.remote_id, hello))
    def of(self, kind):
        return [e for e in self.events if e[0] == kind]

def client(**kw):
    seen = Seen()
    mx = mx_remote.Remote(open_connection=False, callbacks=seen, **kw)
    mx._uid = bytes(range(0x20, 0x30))
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

print('ALL OK')
