#!/usr/bin/env python3
'''The mesh module's opcodes: replacing a mesh unit (0x56) and the settings a
mesh keeps of its units (0x57).

Each layout is composed here from the firmware's, byte by byte, so it rules out
a slip in the builders and decoders, not a shared misreading of the layout.'''

import asyncio, os, struct, sys, logging, time, zlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import DeviceFeature as D, MxrDeviceUid
from mx_remote.Interface import MeshBay, MeshBays, MeshReplaceUnit, MeshSetting, MeshConfigDigest
from mx_remote.proto.Constants import (MESH_BAYS_MAX, MESH_CONFIG_MAX, MESH_REPLACE_UNITS_MAX, MXR_OPCODE_VERSIONS,
                                       MXR_PROTOCOL_VERSION, MeshReplaceResult)
from mx_remote.proto.Factory import create_mxr_frame
from mx_remote.proto.FrameMeshConfig import decode_settings, encode_bays, encode_settings

ADDR = ('192.0.2.9', 8812)

class Seen(mx_remote.MxrCallbacks):
    def __init__(self):
        self.events = []
    def on_mesh_replace_queried(self, dev):
        self.events.append(('queried', dev.remote_id))
    def on_mesh_replace_units_received(self, dev, units):
        self.events.append(('units', dev.remote_id, units))
    def on_mesh_replace_requested(self, dev, unit):
        self.events.append(('requested', dev.remote_id, unit))
    def on_mesh_replace_answered(self, dev, unit, result):
        self.events.append(('answered', dev.remote_id, unit, result))
    def on_mesh_config_requested(self, dev, subject):
        self.events.append(('config requested', dev.remote_id, subject))
    def on_mesh_config_received(self, dev, config):
        self.events.append(('config', dev.remote_id, config))
    def on_mesh_config_set_requested(self, dev, settings):
        self.events.append(('set', dev.remote_id, settings))
    def on_mesh_bays_requested(self, dev, subject):
        self.events.append(('bays requested', dev.remote_id, subject))
    def on_mesh_bays_received(self, dev, bays):
        self.events.append(('bays', dev.remote_id, bays))
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

def rx(mx, sender, opcode, payload=b'', protocol=0x33, at=None):
    frame = bytearray(create_mxr_frame(sender, opcode, payload))
    frame[2] = protocol
    mx.process_frame(time.time() if at is None else at, bytes(frame), ADDR)

def hello(mx, sender, features=D.ONEIP_SINK | D.MESH, protocol=0x33):
    rx(mx, sender, 0x00, struct.pack('<H', protocol) + name('ONEIP') + name('P8SN%08d' % sender[0]) + name('5.0.0')
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

def refused(mx, coro, why):
    n = len(mx.sent)
    assert call(coro) is False, why
    assert len(mx.sent) == n, f'{why}: refused, but transmitted anyway'

assert MXR_PROTOCOL_VERSION >= 0x33, hex(MXR_PROTOCOL_VERSION)
assert (MXR_OPCODE_VERSIONS[0x56], MXR_OPCODE_VERSIONS[0x57]) == (0x32, 0x33)
print('versions    : 0x56 stamped 0x32, 0x57 0x33')

# ============================================================ 0x56 MESH_REPLACE
def replace_header(kind, first=0, total=0, flags=0):
    '''The header, its reserved byte poisoned.'''
    return bytes([1, kind]) + struct.pack('<HH', first, total) + bytes([flags, 0xA5])

def record(n):
    '''A record whose every field is distinct from its neighbours, and wider
    than a narrowed read could reproduce.'''
    return (uid(n) + struct.pack('<IHH', 0x80400018 + n, 0x0301 + n, 0x0702 + n)
            + b'Lounge TV input!' + b'Bar\0' + b'\xA5' * 12)

def units_frame(first, total, flags, records):
    return replace_header(1, first, total, flags) + b''.join(record(n) for n in records)

def kept(seen):
    return [u.uid for u in seen.of('units')[-1][2].units]

# A list is read by whole records.
mx, seen = client()
ctrl = hello(mx, uid(0x31))
rx(mx, uid(0x31), 0x56, units_frame(0, 3, 1, [1, 2]) + record(3)[:55])
units = seen.of('units')[-1][2]
assert (units.offline_controller, units.total) == (True, 3), units
assert [u.uid for u in units.units] == [U(1), U(2)], 'a part record was read'
u = units.units[1]
assert (int(u.features), u.input, u.output) == (0x8040001A, 0x0303, 0x0704), u
assert (u.input_name, u.output_name) == ('Lounge TV input!', 'Bar'), u
assert [r.unit.uid for r in mx.mesh_replaceable] == [U(1), U(2)]
assert mx.mesh_replaceable[0].lister == U(0x31) and mx.mesh_replaceable[0].offline_controller
print('units       : whole records, every field at its offset')

# A frame from the first record replaces the last list; a later one adds to it.
rx(mx, uid(0x31), 0x56, units_frame(0, 30, 0, range(1, 25)))
rx(mx, uid(0x31), 0x56, units_frame(24, 30, 0, range(25, 31)))
assert kept(seen) == [U(n) for n in range(1, 31)], 'a later frame did not add'
rx(mx, uid(0x31), 0x56, units_frame(0, 1, 0, [40]))
assert kept(seen) == [U(40)], 'a first frame did not replace'
# A later frame of a list no longer kept starts it again.
rx(mx, uid(0x31), 0x56, units_frame(24, 30, 0, [41]), at=time.time() + 31)
assert kept(seen) == [U(41)], 'added to a list 31 s old'
rx(mx, uid(0x31), 0x56, units_frame(0, 1, 0, [42]), at=time.time() - 31)
assert mx.mesh_replaceable == [], 'a list 31 s old is replaceable'
print('pages       : from the first record replaces, later ones add')

# No more units are kept of every sender together than a controller lists.
mx, seen = client()
a = hello(mx, uid(0x31))
b = hello(mx, uid(0x32))
rx(mx, uid(0x31), 0x56, units_frame(0, 20, 0, range(1, 21)))
rx(mx, uid(0x32), 0x56, units_frame(0, 20, 0, range(41, 61)))
assert kept(seen) == [U(n) for n in range(41, 41 + MESH_REPLACE_UNITS_MAX - 20)], kept(seen)
assert len(mx.mesh_replaceable) == MESH_REPLACE_UNITS_MAX
# A unit two devices list appears once, under the first lister by uid.
rx(mx, uid(0x32), 0x56, units_frame(0, 1, 0, [1]))
assert [(r.lister, r.unit.uid) for r in mx.mesh_replaceable if r.unit.uid == U(1)] == [(U(0x31), U(1))]
print('limit       : 32 units of every sender together, each once')

# A frame of another version, or too short for its kind, is dropped.
mx, seen = client()
hello(mx, uid(0x31))
p = bytearray(units_frame(0, 1, 0, [1]))
p[0] = 2
rx(mx, uid(0x31), 0x56, bytes(p))
assert not seen.of('units'), 'version 2 was read'
rx(mx, uid(0x31), 0x56, bytes([1, 0, 0, 0, 0, 0, 0]))
assert not seen.of('queried'), '7 bytes'
rx(mx, uid(0x31), 0x56, replace_header(0))
assert seen.of('queried') == [('queried', U(0x31))]
request = replace_header(2) + uid(9) + b'\xA5' * 7
rx(mx, uid(0x31), 0x56, request)
assert not seen.of('requested'), '31 bytes'
rx(mx, uid(0x31), 0x56, request + b'\0')
assert seen.of('requested') == [('requested', U(0x31), U(9))]
print('drops       : another version, or too short for its kind')

# --------------------------------------------------------- requesting a unit
mx, seen = client()
lister = hello(mx, uid(0x31))
rx(mx, uid(0x31), 0x56, units_frame(0, 1, 0, [7]) + uid(8) + struct.pack('<IHH', 0, 1, 2) + bytes(32))
mx.sent.clear()
refused(mx, mx.request_mesh_replace(lister, U(9)), 'a unit the device has not listed')
refused(mx, mx.request_mesh_replace(lister, U(7)), 'a unit with a OneIP feature this client lacks')
assert call(mx.request_mesh_replace(lister, U(8))) is True, 'a unit of no feature this client lacks'
p, = sent(mx, 0x56)
assert p == bytes([1, 2, 0, 0, 0, 0, 0, 0]) + uid(8) + bytes(8), p.hex()
assert mx._mesh.pending == (U(0x31), U(8))

# An answer is read only for the unit asked about, and only once.
def result(unit, value):
    return replace_header(3) + uid(unit) + bytes([value]) + b'\xA5' * 7
rx(mx, uid(0x31), 0x56, result(7, 0))
assert not seen.of('answered'), 'an answer about another unit'
rx(mx, uid(0x31), 0x56, result(8, 0x42))
assert seen.of('answered') == [('answered', U(0x31), U(8), 0x42)], seen.of('answered')
rx(mx, uid(0x31), 0x56, result(8, 5))
assert len(seen.of('answered')) == 1, 'answered twice'
call(mx.request_mesh_replace(lister, U(8)))
rx(mx, uid(0x31), 0x56, result(8, 5))
assert seen.of('answered')[-1][3] is MeshReplaceResult.BUSY
print('request     : a listed unit, answered once for that unit')

# A listing more than 30 s old is not one to ask about.
rx(mx, uid(0x31), 0x56, units_frame(0, 1, 0, []) + uid(8) + bytes(40), at=time.time() - 31)
refused(mx, mx.request_mesh_replace(lister, U(8)), 'a unit listed 31 s ago')
rx(mx, uid(0x31), 0x56, units_frame(0, 1, 0, []) + uid(8) + bytes(40))
mx.set_mesh_controller(U(0x31))
refused(mx, mx.request_mesh_replace(lister, U(8)), 'a client in a mesh')
mx.set_mesh_controller(None)
mx._serial = 'P9SN00001234'
refused(mx, mx.request_mesh_replace(lister, U(8)), 'a client on a default serial')
mx._serial = 'P9SN00000000'
assert call(mx.request_mesh_replace(lister, U(8))) is True, "this client's default serial is not a default one"
print('refusals    : a stale listing, a mesh member, a default serial')

# The query is sent at most every 2 s, to every unit.
mx.sent.clear()
mx._mesh._queried = None
assert call(mx.query_mesh_replaceable()) is True
assert call(mx.query_mesh_replaceable()) is True
assert sent(mx, 0x56) == [bytes([1, 0, 0, 0, 0, 0, 0, 0])], sent(mx, 0x56)
mx._mesh._queried -= 2
call(mx.query_mesh_replaceable())
assert len(sent(mx, 0x56)) == 2, 'a query 2 s later was not sent'
print('query       : the header alone, at most every 2 s')

# ------------------------------------------------------------ listing units
mx.sent.clear()
unit = lambda n: MeshReplaceUnit(uid=U(n), features=D(0x01020304 + n), input=0x1100 + n, output=0x2200 + n,
                                 input_name=f'in{n}', output_name='o' * 16)
assert call(mx.send_mesh_replaceable(lister, True, [unit(n) for n in range(30)])) is True
first, second = sent(mx, 0x56)
assert (len(first), len(second)) == (8 + 24 * 56, 8 + 6 * 56)
assert second[:8] == bytes([1, 1, 24, 0, 30, 0, 1, 0]), second[:8].hex()
r = second[8:64]
assert r[:16] == uid(24) and r[16:20] == struct.pack('<I', 0x01020304 + 24)
assert r[20:24] == struct.pack('<HH', 0x1118, 0x2218)
assert r[24:40] == b'in24' + bytes(12) and r[40:56] == b'o' * 16
mx.sent.clear()
assert call(mx.send_mesh_replaceable(lister, False, [])) is True
assert sent(mx, 0x56) == [bytes([1, 1, 0, 0, 0, 0, 0, 0])], 'an empty list'
refused(mx, mx.send_mesh_replaceable(lister, False, [unit(n) for n in range(33)]), '33 units')
refused(mx, mx.send_mesh_replaceable(lister, False, [MeshReplaceUnit(uid=U(1), input_name='x' * 17)]),
        'a 17-byte name')
mx.sent.clear()
assert call(mx.send_mesh_replace_result(lister, U(3), MeshReplaceResult.BUSY)) is True
assert sent(mx, 0x56) == [bytes([1, 3, 0, 0, 0, 0, 0, 0]) + uid(3) + bytes([5]) + bytes(7)]
print('lists       : 24 records a frame, 32 units, 16-byte names; a 32-byte result')

# A unit that predates the module is not sent its frames.
old = hello(mx, uid(0x35), protocol=0x31)
refused(mx, mx.send_mesh_replace_result(old, U(3), MeshReplaceResult.BUSY), 'a unit below 0x32')
print('gate        : nothing to a unit below the opcode')

# ============================================================= 0x57 MESH_CONFIG
assert encode_settings([MeshSetting('led.status', '0'), MeshSetting('ir.profile', '')]) \
    == b'\x0aled.status\x010\x0air.profile\x00'
assert decode_settings(b'\x0aled.status\x010\x0air.profile\x00') \
    == (MeshSetting('led.status', '0'), MeshSetting('ir.profile', ''))
assert decode_settings(b'\x02ab\x03cd') is None, 'a short value'
assert decode_settings(b'\x02ab') is None, 'a name without a value'
assert encode_settings([MeshSetting('x' * 256, '')]) is None
assert encode_settings([MeshSetting('a', 'x' * 256)]) is None
assert encode_settings([MeshSetting('a', 'x' * 255)]) is not None
assert encode_settings([MeshSetting('a\0b', '')]) is None
fill = [MeshSetting('', 'v' * 246)] * 8
assert len(encode_settings(fill)) == MESH_CONFIG_MAX
assert encode_settings(fill + [MeshSetting('', '')]) is None
print('settings    : length-prefixed pairs, 255 bytes each, 1984 together')

def config_header(kind, flags, offset, total, crc, subject):
    '''The header, its reserved bytes poisoned.'''
    return bytes([1, kind, flags, 0xA5]) + struct.pack('<HHI', offset, total, crc) + b'\xA5' * 4 + subject

def crc32(b):
    return zlib.crc32(b) & 0xFFFFFFFF

SETTINGS = (MeshSetting('a', 'b'), MeshSetting('n' * 120, 'v' * 130), MeshSetting('', ''))
BYTES = encode_settings(SETTINGS)
assert len(BYTES) == 4 + 252 + 2, len(BYTES)

def pages(kind, flags, subject, data, crc, size=100):
    return [config_header(kind, flags, o, len(data), crc, subject) + data[o:o + size]
            for o in range(0, len(data), size)]

# A hello is read only about its sender.
mx, seen = client()
unit_a = hello(mx, uid(0x31))
rx(mx, uid(0x31), 0x57, config_header(0, 0, 0, 293, 0xDEADBEEF, uid(0x32)))
assert unit_a.mesh_config_digest is None, 'a hello about another unit'
rx(mx, uid(0x31), 0x57, config_header(0, 0, 0, 293, 0xDEADBEEF, uid(0x31))[:31])
assert unit_a.mesh_config_digest is None, '31 bytes'
rx(mx, uid(0x31), 0x57, config_header(0, 0, 0, 293, 0xDEADBEEF, uid(0x31)))
assert unit_a.mesh_config_digest == MeshConfigDigest(length=293, crc32=0xDEADBEEF), unit_a.mesh_config_digest
print('hello       : the length and crc32 a unit announces of itself')

# Settings are taken once every frame has arrived.
rx(mx, uid(0x31), 0x57, config_header(1, 0, 0, 0, 0, uid(0x33)))
assert seen.of('config requested') == [('config requested', U(0x31), U(0x33))]
frames = pages(2, 1, uid(0x33), BYTES, crc32(BYTES))
assert len(frames) == 3
for f in frames[:-1]:
    rx(mx, uid(0x31), 0x57, f)
assert not seen.of('config') and mx.mesh_config(U(0x33)) is None, 'taken before the last frame'
rx(mx, uid(0x31), 0x57, frames[-1])
config = mx.mesh_config(U(0x33))
assert config is not None and seen.of('config') == [('config', U(0x31), config)]
assert (config.subject, config.holder, config.copy, config.settings) == (U(0x33), U(0x31), True, SETTINGS), config
print('dump        : whole, in order, kept by its unit')

# Out of order, or with another crc or header, a sender's settings are dropped.
mx, seen = client()
hello(mx, uid(0x31))
hello(mx, uid(0x32))
f = pages(2, 0, uid(0x31), BYTES, crc32(BYTES))
for order in ([f[0], f[2], f[1]], [f[1], f[2]], [f[0], f[1], f[1], f[2]]):
    for frame in order:
        rx(mx, uid(0x31), 0x57, frame)
    assert mx.mesh_config(U(0x31)) is None, 'out of order'
# A frame at the wrong offset is dropped even when its bytes would pass the crc32.
half = encode_settings([MeshSetting('a' * 48, 'b' * 49)])
whole = half + half
rx(mx, uid(0x31), 0x57, config_header(2, 0, 0, len(whole), crc32(whole), uid(0x31)) + half)
rx(mx, uid(0x31), 0x57, config_header(2, 0, 120, len(whole), crc32(whole), uid(0x31)) + half)
assert mx.mesh_config(U(0x31)) is None, 'a frame at the wrong offset'
bad = pages(2, 0, uid(0x31), BYTES, crc32(BYTES) ^ 1)
for frame in bad:
    rx(mx, uid(0x31), 0x57, frame)
assert mx.mesh_config(U(0x31)) is None, 'a wrong crc32'
for frame in (f[0], pages(2, 1, uid(0x31), BYTES, crc32(BYTES))[1], f[2]):
    rx(mx, uid(0x31), 0x57, frame)
assert mx.mesh_config(U(0x31)) is None, 'a frame of other flags'
# Another sender's frames in between leave the first sender's alone.
for mine, theirs in zip(f, pages(2, 0, uid(0x32), BYTES, crc32(BYTES))):
    rx(mx, uid(0x31), 0x57, mine)
    rx(mx, uid(0x32), 0x57, theirs)
assert mx.mesh_config(U(0x31)) is not None and mx.mesh_config(U(0x32)) is not None, 'interleaved senders'
assert mx.mesh_config(U(0x31)).copy is False
# Bytes past the length, and bytes that end inside a pair, are not settings.
mx, seen = client()
hello(mx, uid(0x31))
rx(mx, uid(0x31), 0x57, config_header(2, 0, 0, 2, crc32(b'\x01a'), uid(0x31)) + b'\x01a\x00')
assert mx.mesh_config(U(0x31)) is None, 'bytes past the length'
rx(mx, uid(0x31), 0x57, config_header(2, 0, 0, 2, crc32(b'\x01a'), uid(0x31)) + b'\x01a')
assert mx.mesh_config(U(0x31)) is None, 'a name without a value'
big = b'\x00' * (MESH_CONFIG_MAX + 2)
for frame in pages(2, 0, uid(0x31), big, crc32(big), size=1024):
    rx(mx, uid(0x31), 0x57, frame)
assert mx.mesh_config(U(0x31)) is None, 'settings over 1984 bytes'
rx(mx, uid(0x31), 0x57, config_header(2, 0, 0, 0, 0, uid(0x31)))
assert mx.mesh_config(U(0x31)).settings == (), 'no settings at all'
p = bytearray(config_header(2, 0, 0, 0, 0, uid(0x34)))
rx(mx, uid(0x31), 0x57, bytes(p[:31]))
assert mx.mesh_config(U(0x34)) is None, '31 bytes were read'
from mx_remote.proto.FrameMeshConfig import FrameMeshConfig
from mx_remote.proto.FrameHeader import FrameHeader
short = FrameMeshConfig(FrameHeader(mx, create_mxr_frame(uid(0x31), 0x57, bytes(p[:31])), ADDR))
assert short.kind is None and str(short) == 'mesh config <dropped>', str(short)
p[0] = 2
rx(mx, uid(0x31), 0x57, bytes(p))
assert mx.mesh_config(U(0x34)) is None, 'version 2 was read'
print('drops       : out of order, another crc32 or header, past the length, or too long')

# A set is reported only from this client's controller, about this client.
mx, seen = client()
ctrl = hello(mx, uid(0x31))
own = bytes(mx.uid.byte_value)
def set_(subject):
    n = len(seen.of('set'))
    for frame in pages(3, 0, subject, BYTES, crc32(BYTES)):
        rx(mx, uid(0x31), 0x57, frame)
    return len(seen.of('set')) > n
assert not set_(own), 'from a unit this client does not follow'
mx.set_mesh_controller(U(0x31))
assert not set_(uid(7)), 'for another unit'
assert set_(own)
assert seen.of('set')[-1] == ('set', U(0x31), SETTINGS)
assert mx.mesh_config(mx.uid) is None, 'a set kept as a dump'
print('set         : only from the controller, about this client, never kept')

# ------------------------------------------------------------ sending settings
mx, seen = client()
member = hello(mx, uid(0x31))
refused(mx, mx.send_mesh_config_hello(SETTINGS), 'a hello from a client in no mesh')
mx.set_mesh_controller(mx.uid)
refused(mx, mx.send_mesh_config_hello([MeshSetting('a\0', '')]), 'a setting no unit takes')
mx.sent.clear()
assert call(mx.send_mesh_config_hello(SETTINGS)) is True
p, = sent(mx, 0x57)
assert p == bytes([1, 0, 0, 0, 0, 0]) + struct.pack('<HI', len(BYTES), crc32(BYTES)) + bytes(4) + own, p.hex()

mx.sent.clear()
assert call(mx.request_mesh_config(member, U(0x33))) is True
assert sent(mx, 0x57) == [bytes([1, 1]) + bytes(14) + uid(0x33)]

long = tuple(MeshSetting('n' * 200, 'v' * 200) for _ in range(4))
data = encode_settings(long)
for subject, flags in ((own, 0), (uid(0x33), 1)):
    mx.sent.clear()
    assert call(mx.send_mesh_config(member, MxrDeviceUid(subject), long)) is True
    out = sent(mx, 0x57)
    assert [len(x) for x in out] == [32 + 1024, 32 + len(data) - 1024], [len(x) for x in out]
    for x, offset in zip(out, (0, 1024)):
        assert x[:16] == bytes([1, 2, flags, 0]) + struct.pack('<HHI', offset, len(data), crc32(data)) + bytes(4)
        assert x[16:32] == subject and x[32:] == data[offset:offset + 1024]
mx.sent.clear()
assert call(mx.send_mesh_config(member, mx.uid, ())) is True
assert sent(mx, 0x57) == [bytes([1, 2, 0, 0]) + struct.pack('<HHI', 0, 0, 0) + bytes(4) + own], 'no settings'

refused(mx, mx.send_mesh_config_set(member, SETTINGS), 'a member that has not reported its controller')
member.mesh_master = U(0x32)
refused(mx, mx.send_mesh_config_set(member, SETTINGS), 'a member of another controller')
member.mesh_master = mx.uid
mx.sent.clear()
assert call(mx.send_mesh_config_set(member, SETTINGS)) is True
p, = sent(mx, 0x57)
assert p == bytes([1, 3, 0, 0]) + struct.pack('<HHI', 0, len(BYTES), crc32(BYTES)) + bytes(4) + uid(0x31) + BYTES
print('send        : hello, request, dump in 1024-byte frames, set to a member of this controller')

# ----------------------------------------------------- a controller's numbering

def bays_entry(input, bay, features, unit):
    '''One entry, its reserved byte poisoned.'''
    return bytes([1 if input else 0, 0xA5]) + struct.pack('<HI', bay, features) + unit

# 50 bays: inputs 0 to 24 of units 0 to 24, then outputs 1 to 25 of units 100
# to 124, each with features of its own.
NUMBERING, NUMBERED = [], b''
for n in range(50):
    entry = MeshBay(input=(n < 25), bay=(n if (n < 25) else n - 24), features=D(0x00400018 ^ n),
                    unit=U(n if (n < 25) else n + 75))
    NUMBERING.append(entry)
    NUMBERED += bays_entry(entry.input, entry.bay, int(entry.features), entry.unit.byte_value)
assert len(NUMBERED) == 1200
assert encode_bays(NUMBERING) == NUMBERED.replace(b'\xA5', b'\0'), 'encoded otherwise than composed'

# Taken entry by entry once every frame has arrived.
mx, seen = client()
holder = hello(mx, uid(0x31))
frames = pages(5, 1, uid(7), NUMBERED, crc32(NUMBERED), size=1008)
assert len(frames) == 2
for i, f in enumerate(frames):
    assert mx.mesh_bays(U(7)) is None, f'taken after {i} frames'
    rx(mx, uid(0x31), 0x57, f)
expected = MeshBays(subject=U(7), holder=U(0x31), copy=True, bays=tuple(NUMBERING))
assert mx.mesh_bays(U(7)) == expected, mx.mesh_bays(U(7))
assert seen.of('bays') == [('bays', U(0x31), expected)], seen.of('bays')
assert mx.mesh_config(U(7)) is None, 'a numbering kept as settings'

# A numbering of ragged entries or another crc is dropped.
def fed(data, crc):
    mx, _ = client()
    hello(mx, uid(0x31))
    for f in pages(5, 0, uid(7), data, crc):
        rx(mx, uid(0x31), 0x57, f)
    return mx.mesh_bays(U(7))
assert fed(NUMBERED, crc32(NUMBERED)) is not None
assert fed(NUMBERED[:-1], crc32(NUMBERED[:-1])) is None, 'a part entry'
assert fed(NUMBERED, crc32(NUMBERED) ^ 1) is None, 'another crc'
# A numbering longer than a settings dump, and not past 512 entries.
big = bays_entry(True, 1, 0, uid(1)) * MESH_BAYS_MAX
assert fed(big, crc32(big)) is not None, f'{MESH_BAYS_MAX} entries'
big += bays_entry(True, 1, 0, uid(1))
assert fed(big, crc32(big)) is None, f'{MESH_BAYS_MAX + 1} entries'

# Only mode 1 is an input.
odd = bays_entry(True, 3, 0, uid(1)).replace(b'\x01\xA5', b'\x02\xA5', 1)
assert not fed(odd, crc32(odd)).bays[0].input, 'mode 2 read as an input'

# A numbering of no bays, and a request for one.
mx, seen = client()
hello(mx, uid(0x31))
rx(mx, uid(0x31), 0x57, config_header(5, 0, 0, 0, crc32(b''), uid(7)))
assert mx.mesh_bays(U(7)) == MeshBays(subject=U(7), holder=U(0x31), copy=False, bays=()), mx.mesh_bays(U(7))
rx(mx, uid(0x31), 0x57, config_header(4, 0, 0, 0, 0, uid(9)))
assert seen.of('bays requested') == [('bays requested', U(0x31), U(9))], seen.events
print('bays recv   : 24-byte entries put together as a dump is, a request handed on')

# Asked of a unit at 0x33, sent in frames of 42 entries, a copy flagged.
mx, seen = client()
new = hello(mx, uid(0x31))
old = hello(mx, uid(0x32), protocol=0x32)
mx.sent.clear()
assert call(mx.request_mesh_bays(new, U(9))) is True
assert sent(mx, 0x57) == [bytes([1, 4]) + bytes(14) + uid(9)]
refused(mx, mx.request_mesh_bays(old, U(9)), 'a unit below 0x33')
mx.sent.clear()
assert call(mx.send_mesh_bays(new, U(9), NUMBERING)) is True
first, second = sent(mx, 0x57)
assert first[:3] == bytes([1, 5, 1]) and len(first) == 32 + 42 * 24, (first[:3], len(first))
assert second[4:8] == struct.pack('<HH', 1008, 1200), second[4:8].hex()
assert first[8:12] == second[8:12] == struct.pack('<I', crc32(encode_bays(NUMBERING)))
assert first[32:] + second[32:] == encode_bays(NUMBERING)
assert first[32:40] == bytes([1, 0, 0, 0]) + struct.pack('<I', 0x00400018), first[32:40].hex()
mx.sent.clear()
assert call(mx.send_mesh_bays(new, mx.uid, [])) is True
p, = sent(mx, 0x57)
assert p[:8] == bytes([1, 5, 0, 0, 0, 0, 0, 0]), 'its own, of no bays, in one frame'
refused(mx, mx.send_mesh_bays(new, U(9), [NUMBERING[0]] * (MESH_BAYS_MAX + 1)), '513 bays')
assert call(mx.send_mesh_bays(new, U(9), [NUMBERING[0]] * MESH_BAYS_MAX)) is True, '512 bays'
print('bays send   : asked of 0x33, 42 entries a frame, a copy flagged, 512 at most')

print('ALL OK')
