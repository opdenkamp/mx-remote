#!/usr/bin/env python3
######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''The port metadata a mesh keeps: MESH_CONFIG (0x57) kinds 6 to 8, METADATA,
METADATA INDEX and METADATA REQUEST.

Each layout is composed here byte by byte from the one the Rust crate pins, so
it rules out a slip in the builders and decoders, not a shared misreading.
Every behaviour is asserted in both directions: what is taken beside what is
dropped, what is sent beside what is not.'''

import asyncio, os, struct, sys, logging, time, zlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import DeviceFeature as D, MxrDeviceUid, MeshPort, PortMetadata, PortMetadataField as F, PortMetadataStore
from mx_remote.proto.Factory import create_mxr_frame
from mx_remote.proto.FrameMeshConfig import (decode_metadata_index, decode_port_metadata, encode_port_metadata,
                                             metadata_index_payloads)

ADDR = ('192.0.2.9', 8812)
OURS = bytes(range(0x20, 0x30))

class Seen(mx_remote.MxrCallbacks):
    def __init__(self):
        self.changed = []
        self.generations = []
    def on_port_metadata_changed(self, source, metadata):
        self.changed.append((source, metadata))
    def on_port_metadata_generation_changed(self, source, generation):
        self.generations.append((source, generation))

def client():
    seen = Seen()
    mx = mx_remote.Remote(open_connection=False, callbacks=seen)
    mx._uid = OURS
    mx.sent = []
    mx.transmit = lambda data, to=None: (mx.sent.append((bytes(data), to)), len(data))[1]
    return mx, seen

def uid(n):
    return bytes([n]) * 16

def U(n):
    return MxrDeviceUid(uid(n))

def name(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def rx(mx, sender, payload, at=None, opcode=0x57, protocol=0x33):
    frame = bytearray(create_mxr_frame(sender, opcode, payload))
    frame[2] = protocol
    mx.process_frame(time.time() if at is None else at, bytes(frame), ADDR)

def hello(mx, sender):
    rx(mx, sender, struct.pack('<H', 0x33) + name('ONEIP') + name('P8SN%08d' % sender[0]) + name('5.0.0')
                   + struct.pack('<I', int(D.ONEIP_SINK | D.MESH)), opcode=0x00, protocol=0x01)
    return mx.get_by_uid(MxrDeviceUid(sender))

def reports(mx, sender, controller):
    '''sender's membership report, naming controller.'''
    rx(mx, sender, bytes([0xFF, 0, 0, 0]) + controller + bytes(16) + bytes(4), opcode=0x3B, protocol=0x1D)

def call(coro):
    return asyncio.run(coro)

def crc32(b):
    return zlib.crc32(b) & 0xFFFFFFFF

def header(kind, flags, first, total, crc, subject, pad=0xA5):
    '''The 32-byte MESH_CONFIG header: version 1, kind, flags, a reserved byte,
    u16 offset, u16 length, u32 crc32, four reserved bytes and the subject.
    Received fixtures fill the reserved bytes with pad; what this client sends
    zeroes them.'''
    return bytes([1, kind, flags, pad]) + struct.pack('<HHI', first, total, crc) + bytes([pad] * 4) + subject

def body(*pairs):
    return b''.join(k.encode() + b'\0' + v.encode() + b'\0' for k, v in pairs)

def metadata(unit, is_input, data, crc=None, total=None, pad=0xA5):
    return header(6, 4 if is_input else 0, 0, len(data) if total is None else total,
                  crc32(data) if crc is None else crc, unit, pad) + data

def entry(unit, is_input, crc, pad=0xA5):
    return unit + bytes([1 if is_input else 0, pad, pad, pad]) + struct.pack('<I', crc)

def index(sender, generation, entries, first=0, total=None, crc=None, pad=0xA5):
    '''One index frame carrying entries, the whole index's total and crc32
    given when this frame holds only part of it.'''
    data = b''.join(entries)
    return header(7, 0, first, len(entries) if total is None else total, crc32(data) if crc is None else crc,
                  sender, pad) + struct.pack('<I', generation) + data

def sent(mx, kind=None):
    '''The 0x57 payloads mx sent, with their addressee, each checked for its
    stamp; only those of kind when given.'''
    out = []
    for f, to in mx.sent:
        if int.from_bytes(f[20:22], 'little') != 0x57:
            continue
        assert f[2] == 0x33, f'0x57 stamped {f[2]:#04x}'
        p = f[24:24 + int.from_bytes(f[22:24], 'little')]
        if (kind is None) or (p[1] == kind):
            out.append((p, None if to is None else to.remote_id))
    return out

def request(unit, is_input):
    return bytes([1, 8, 4 if is_input else 0, 0]) + bytes(12) + unit

PS4 = (F('device_type', 'Sony PlayStation 4'), F('logo', 'http://x/ps4.png'))
PS4_BODY = body(('device_type', 'Sony PlayStation 4'), ('logo', 'http://x/ps4.png'))

# ============================================================== encoding
assert encode_port_metadata(PS4) == PS4_BODY
assert decode_port_metadata(PS4_BODY) == PS4
assert encode_port_metadata(()) == b'' and decode_port_metadata(b'') == ()
assert encode_port_metadata([F('k' * 31, 'v' * 255)]) is not None
for k, v in (('', 'v'), ('k' * 32, 'v'), ('a.b', 'v'), ('k', ''), ('k', 'v' * 256), ('k', 'a"b'), ('k', 'a\\b'),
             ('k', 'a\nb'), ('k', 'a\x7fb'), ('ké', 'v')):
    assert encode_port_metadata([F(k, v)]) is None, (k, v)
assert encode_port_metadata([F('k', 'é' * 127)]) is not None and encode_port_metadata([F('k', 'é' * 128)]) is None, \
    'a value is counted in bytes of UTF-8'
assert encode_port_metadata([F('k', 'v')] * 16) is not None and encode_port_metadata([F('k', 'v')] * 17) is None
# 4 fields of 3 + 253 bytes are 1024, and one byte more is too many.
assert len(encode_port_metadata([F('k', 'v' * 253)] * 4)) == 1024
assert encode_port_metadata([F('k', 'v' * 253)] * 3 + [F('k', 'v' * 254)]) is None
for bad in (b'k\0v', b'k\0', b'k\0\xff\0', b'a.b\0v\0', body(('k', 'v')) * 17):
    assert decode_port_metadata(bad) is None, bad
assert decode_port_metadata(body(('k', 'a'), ('k', 'b'))) == (F('k', 'a'), F('k', 'b')), 'a repeated key is carried'
print('encoding    : key NUL value NUL in order, refused as a unit refuses')

# An index goes in frames of 48 entries, every one carrying the generation and
# the crc32 of all of them.
entries = [(MeshPort(U(i), i % 2 == 1), 0x01020304 * i) for i in range(50)]
pages = metadata_index_payloads(U(0x3C), 0xA1B2C3D4, entries)
wire = [entry(uid(i), i % 2 == 1, 0x01020304 * i, pad=0) for i in range(50)]
crc_all = crc32(b''.join(wire))
assert pages == [index(uid(0x3C), 0xA1B2C3D4, wire[:48], 0, 50, crc_all, pad=0),
                 index(uid(0x3C), 0xA1B2C3D4, wire[48:], 48, 50, crc_all, pad=0)], pages
assert [len(p) for p in pages] == [32 + 4 + 48 * 24, 32 + 4 + 2 * 24]
assert decode_metadata_index(pages[1][32:]) == (0xA1B2C3D4, tuple(entries[48:]))
assert decode_metadata_index(pages[1][32:-1]) is None and decode_metadata_index(b'\0\0\0') is None
none, = metadata_index_payloads(U(0x3C), 7, [])
assert len(none) == 36 and none[4:12] == bytes(8), 'no entries, with crc 0'
print('index       : 48 entries to a frame, offset and length in entries, crc32 over every one')

# ============================================================== as a member
C, M = uid(0x31), uid(0x32)
mx, seen = client()
hello(mx, C)
other = hello(mx, uid(0x33))
mx.set_mesh_controller(U(0x31))
port_a, port_b = MeshPort.input_of(U(0x41)), MeshPort.output_of(U(0x42))
a_crc, b_body = crc32(PS4_BODY), body(('room', 'Lounge'))
now = time.time()

# A request for every port missing, direct to the sender.
mx.sent.clear()
rx(mx, C, index(C, 5, [entry(uid(0x41), True, a_crc), entry(uid(0x42), False, crc32(b_body))]), at=now)
assert sent(mx, 8) == [(request(uid(0x41), True), U(0x31)), (request(uid(0x42), False), U(0x31))], sent(mx)
assert seen.generations == [(U(0x31), 5)], 'the whole index sets the generation'
rx(mx, C, metadata(uid(0x41), True, PS4_BODY), at=now + 1)
rx(mx, C, metadata(uid(0x42), False, b_body), at=now + 1)
assert mx.port_metadata(port_a) == PS4 and mx.port_metadata(port_b) == (F('room', 'Lounge'),)
assert mx.port_metadata(MeshPort.output_of(U(0x41))) is None, 'the INPUT flag names the port'
assert seen.changed == [(U(0x31), PortMetadata(port_a, PS4)), (U(0x31), PortMetadata(port_b, (F('room', 'Lounge'),)))]
# The same index again asks for nothing, and reports nothing.
seen.changed.clear(); seen.generations.clear(); mx.sent.clear()
rx(mx, C, index(C, 5, [entry(uid(0x41), True, a_crc), entry(uid(0x42), False, crc32(b_body))]), at=now + 2)
assert sent(mx) == [] and seen.changed == [] and seen.generations == []
print('member      : asks its controller for each port it lacks, and takes the answers')

# Metadata is taken from the controller at any time, and from no one else.
rx(mx, uid(0x33), metadata(uid(0x41), True, b_body), at=now + 2)
assert mx.port_metadata(port_a) == PS4, 'metadata from a unit not its controller'
rx(mx, C, metadata(uid(0x41), True, b_body), at=now + 1000)
assert mx.port_metadata(port_a) == (F('room', 'Lounge'),), 'its controller, after the window'
rx(mx, C, metadata(uid(0x41), True, PS4_BODY), at=now + 1000)
# Dropped for a length, crc32 or field a unit refuses.
for bad in (metadata(uid(0x41), True, b_body, total=len(b_body) + 1),
            metadata(uid(0x41), True, b_body, crc=crc32(b_body) ^ 1),
            metadata(uid(0x41), True, body(('a.b', 'v')))):
    rx(mx, C, bad, at=now + 3)
    assert mx.port_metadata(port_a) == PS4, bad
# No fields removes the port's.
rx(mx, C, metadata(uid(0x41), True, b''), at=now + 3)
assert mx.port_metadata(port_a) is None and seen.changed[-1] == (U(0x31), PortMetadata(port_a, ()))
rx(mx, C, metadata(uid(0x41), True, PS4_BODY), at=now + 3)
print('taken       : from its controller, whole and valid; none removes it')

# Asked with request_port_metadata(), a holder's answer is taken for 30 s.
mx.sent.clear()
assert call(mx.request_port_metadata(other, port_b)) is True
assert sent(mx) == [(request(uid(0x42), False), U(0x33))], sent(mx)
asked = time.time()
rx(mx, uid(0x33), metadata(uid(0x42), False, body(('room', 'Kitchen'))), at=asked + 29)
assert mx.port_metadata(port_b) == (F('room', 'Kitchen'),), 'the holder asked'
rx(mx, uid(0x33), metadata(uid(0x42), False, b_body), at=asked + 31)
assert mx.port_metadata(port_b) == (F('room', 'Kitchen'),), 'the holder asked, 31 s on'
print('asked       : a holder\'s answer is taken for 30 s')

# A newer index drops the ports it does not name, once whole.
seen.changed.clear(); seen.generations.clear()
t = now + 100
full = [entry(uid(0x41), True, a_crc)] + [entry(uid(0x50 + i), False, 0) for i in range(48)]
crc_all = crc32(b''.join(full))
rx(mx, C, index(C, 6, full[:48], 0, 49, crc_all), at=t)
assert mx.port_metadata(port_b) is not None and seen.generations == [], 'dropped before the index was whole'
rx(mx, uid(0x33), index(uid(0x33), 6, full[48:], 48, 49, crc_all), at=t)
rx(mx, C, index(C, 6, full[48:], 47, 49, crc_all), at=t)
rx(mx, C, index(C, 6, full[48:], 48, 49, crc_all ^ 1), at=t)
assert seen.generations == [], 'a later frame from another sender, offset or crc32'
rx(mx, C, index(C, 6, full[48:], 48, 49, crc_all), at=t)
assert mx.port_metadata(port_b) is None and mx.port_metadata(port_a) == PS4
assert seen.changed == [(U(0x31), PortMetadata(port_b, ()))] and seen.generations == [(U(0x31), 6)]
# The index's sender is taken from for 30 s from its first frame.
rx(mx, C, metadata(uid(0x50), False, b_body), at=t + 1)
mx.set_mesh_controller(U(0x34))
rx(mx, C, metadata(uid(0x51), False, b_body), at=t + 29)
rx(mx, C, metadata(uid(0x52), False, b_body), at=t + 31)
assert mx.port_metadata(MeshPort.output_of(U(0x51))) is not None, 'the index sender within 30 s'
assert mx.port_metadata(MeshPort.output_of(U(0x52))) is None, 'the index sender after 30 s'
mx.set_mesh_controller(U(0x31))
print('index taken : whole, in order, from one sender; drops what it does not name')

# An older index is answered with the member's own, direct to the controller,
# at most every 60 s; and taken from the controller alone.
mx.sent.clear(); seen.generations.clear()
rx(mx, C, index(C, 2, []), at=t + 40)
own = sent(mx, 7)
assert own and all(to == U(0x31) for _, to in own), own
assert struct.unpack_from('<I', own[0][0], 32)[0] == 6 and own[0][0][16:32] == OURS, 'its own index, as its own'
assert seen.generations == [], 'an older index taken'
mx.sent.clear()
rx(mx, C, index(C, 2, []), at=t + 99)
assert sent(mx) == [], 'offered again within 60 s'
rx(mx, C, index(C, 2, []), at=t + 101)
assert sent(mx, 7), 'not offered again after 60 s'
mx.sent.clear()
rx(mx, uid(0x33), index(uid(0x33), 9, [entry(uid(0x60), True, 1)]), at=t + 102)
assert sent(mx) == [] and mx.port_metadata_store().generation == 6, 'an index from a unit not its controller'
print('older index : answered with its own, to the controller, every 60 s at most')

# A request is answered with what is held, and no fields when none.
mx.sent.clear()
rx(mx, uid(0x33), request(uid(0x41), True))
rx(mx, uid(0x33), request(uid(0x41), False))
assert sent(mx) == [(metadata(uid(0x41), True, PS4_BODY, pad=0), U(0x33)),
                    (bytes([1, 6, 0, 0]) + bytes(12) + uid(0x41), U(0x33))], sent(mx)
print('request     : answered by every unit, with what it holds')

# A member's metadata is set on its controller.
mx.sent.clear()
assert call(mx.set_port_metadata(port_a, [F('k', 'v')])) is False and mx.port_metadata(port_a) == PS4
assert sent(mx) == []

# ============================================================== as controller
mx, seen = client()
member = hello(mx, M)
outsider = hello(mx, uid(0x33))
reports(mx, M, OURS)
reports(mx, uid(0x33), uid(0x39))
assert member.mesh_master_uid == MxrDeviceUid(OURS)
# In no mesh, it keeps it alone.
assert call(mx.set_port_metadata(port_a, PS4)) is True
assert sent(mx) == [] and mx.port_metadata(port_a) == PS4
mx._probe_once()
assert sent(mx) == [], 'an index from a unit that controls no mesh'
assert seen.generations == [(MxrDeviceUid(OURS), 1)] and seen.changed == [(MxrDeviceUid(OURS), PortMetadata(port_a, PS4))]
mx.set_mesh_controller(MxrDeviceUid(OURS))
# Refused: a key set twice, a field no unit takes.
for fields in ([F('k', 'a'), F('k', 'b')], [F('a.b', 'v')], [F('k', 'v')] * 17):
    assert call(mx.set_port_metadata(port_b, fields)) is False, fields
assert mx.port_metadata(port_b) is None and sent(mx) == []
# A change goes to every unit at once, and the index 1 s later.
seen.generations.clear()
assert call(mx.set_port_metadata(MeshPort.output_of(U(0x41)), [F('room', 'Lounge')])) is True
mx.sent.clear()
assert call(mx.set_port_metadata(port_b, [F('room', 'Lounge')])) is True
assert sent(mx) == [(metadata(uid(0x42), False, b_body, pad=0), None)], sent(mx)
assert seen.generations[-1] == (MxrDeviceUid(OURS), 3)
mx.sent.clear()
mx._probe_once()
assert sent(mx) == [], 'the index went out before 1 s'
mx._metadata.index_due -= 1
mx._probe_once()
# Entries go by unit, then output before input.
assert sent(mx) == [(index(OURS, 3, [entry(uid(0x41), False, crc32(b_body), pad=0), entry(uid(0x41), True, a_crc, pad=0),
                                    entry(uid(0x42), False, crc32(b_body), pad=0)], pad=0), None)], sent(mx)
# Then every 45 to 60 s.
due = mx._metadata.index_due - time.time()
assert 44 < due <= 60, due
# The same metadata again changes nothing.
mx.sent.clear(); seen.generations.clear()
assert call(mx.set_port_metadata(port_b, [F('room', 'Lounge')])) is True
assert sent(mx) == [] and seen.generations == []
print('controller  : a change to every unit at once, the index 1 s later, then every 45-60 s')

# A member's index is taken only at a newer generation, and from a member.
mx.sent.clear(); seen.generations.clear()
rx(mx, M, index(M, 3, [entry(uid(0x43), True, 7)]))
rx(mx, uid(0x33), index(uid(0x33), 9, [entry(uid(0x43), True, 7)]))
assert sent(mx) == [] and seen.generations == [], 'an index at its own generation, or from a unit not its member'
rx(mx, M, index(M, 4, [entry(uid(0x43), True, 7)]))
assert sent(mx, 8) == [(request(uid(0x43), True), U(0x32))] and seen.generations == [(U(0x32), 4)]
assert mx.port_metadata(port_a) is None, 'the member\'s index dropped what it does not name'
print('new member  : a controller takes a member\'s index only at a newer generation')

# ============================================================== restore
mx, seen = client()
held = PortMetadataStore(generation=9, ports=(PortMetadata(port_a, PS4), PortMetadata(port_b, ()),
                                              PortMetadata(MeshPort.input_of(U(0x44)), (F('k', 'a'), F('k', 'b')))))
assert mx.restore_port_metadata(held) is True
assert mx.port_metadata_store() == PortMetadataStore(9, (PortMetadata(port_a, PS4),
                                                         PortMetadata(MeshPort.input_of(U(0x44)), (F('k', 'a'), F('k', 'b')))))
assert seen.changed == [] and seen.generations == [] and mx.sent == [], 'a restore reports or sends something'
for bad in (PortMetadataStore(1, (PortMetadata(port_a, PS4), PortMetadata(port_a, PS4))),
            PortMetadataStore(1, (PortMetadata(port_a, (F('a.b', 'v'),)),))):
    assert mx.restore_port_metadata(bad) is False and mx.port_metadata_store().generation == 9, bad
mx.set_mesh_controller(MxrDeviceUid(OURS))
assert mx.restore_port_metadata(held) is True and mx._metadata.index_due <= time.time() + 1
print('restore     : replaces what is held, a port listed twice refused')

print('ALL OK')
