######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Taking a mesh's controller role, and sending what its controller sends.

The layouts asserted here are the firmware-verified ones the Rust crate pins.
Sent frames are read back through this library's own receive path as well,
from a sender rewritten into the header, so a write and its report agree.

Received fixtures fill every byte the decoder must not read with 0xA5 or a
distinct value, so a field read wide or at a neighbour's offset shows.

Commands are asserted in both directions: every refusal sits next to a command
that goes out.
'''

import asyncio, os, struct, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import (DeviceFeature, MeshControllerReport, MeshOperation, MeshOperationMessage, MxrDeviceUid,
                       BayMirrorStatus)
from mx_remote.const import __version__
from mx_remote.proto.Constants import (BayFeaturesMask, MXR_RC_STATUS_MAX, MXR_RC_STATUS_NAME_LEN,
                                       ONEIP_SOURCE_FILTER_MAX, RCType)
from mx_remote.proto.Factory import create_mxr_frame, process_mxr_frame
from mx_remote.proto.FrameV2IPSources import ONEIP_SOURCE_LIST_MAX

ADDR = ('192.0.2.9', 8812)
OURS = bytes(range(0x20, 0x30))

class Listening(mx_remote.MxrCallbacks):
    def __init__(self):
        self.operations = []
    def on_mesh_operation(self, dev, operation):
        self.operations.append((dev, operation))

seen = Listening()

def client(uid_bytes, **kwargs):
    mx = mx_remote.Remote(open_connection=False, callbacks=kwargs.pop('callbacks', None), **kwargs)
    mx._uid = uid_bytes
    mx.sent = []
    mx.transmit = lambda data, mx=mx, to=None: (mx.sent.append(bytes(data)), len(data))[1]
    return mx

mx = client(OURS, callbacks=seen)

def uid(n):
    return bytes([n]) * 16

def U(n):
    return MxrDeviceUid(uid(n))

def nm(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def ip4(s):
    return bytes(int(x) for x in s.split('.'))

def call(coro):
    return asyncio.run(coro)

def rx(sender, opcode, payload=b'', protocol=0x2F, to=None):
    frame = bytearray(create_mxr_frame(sender, opcode, payload))
    frame[2] = protocol
    (to or mx).process_frame(0.0, bytes(frame), ADDR)

def replay(frame, sender, to=None):
    '''A frame this client sent, as though sender had sent it.'''
    frame = bytearray(frame)
    frame[4:20] = sender
    (to or mx).process_frame(0.0, bytes(frame), ADDR)

def hello(sender, protocol, features, model='ONEIP', to=None):
    rx(sender, 0x00, struct.pack('<H', protocol) + nm(model) + nm('P8SN%08d' % sender[0])
                   + nm('5.0.0') + struct.pack('<I', int(features)), protocol=0x01, to=to)
    return (to or mx).get_by_uid(MxrDeviceUid(sender))

def bay_rec(port, mode, num, name, feat):
    return bytes([port, mode, num, 0, 0]) + nm(name) + nm(name) + nm('1080p') + struct.pack('<II', 0, feat)

def sink(n, protocol=0x2F):
    dev = hello(uid(n), protocol, DeviceFeature.ONEIP_SINK | DeviceFeature.VIDEO_ROUTING)
    rx(uid(n), 0x02, bay_rec(16, 1, 0, f'Output {n}', int(BayFeaturesMask.ONEIP_SINK_LOCAL)), protocol=protocol)
    return dev

def opcode(frame):
    return int.from_bytes(frame[20:22], 'little')

MANAGER = uid(0x40)
hello(MANAGER, 0x2F, DeviceFeature.MANAGER, model='MXR Python')

# ------------------------------------------------------------- announcement
# A controller replacing a unit is told apart in the device list by a serial and
# version of its own. A mesh device announces mesh support rather than
# management, membership while it follows a controller, and the controller role
# while that controller is itself. A peer decodes all of it.
peer = client(uid(0x7E))

def heard(remote):
    assert remote.sent, 'nothing was announced'
    replay(remote.sent[-1], remote._uid, to=peer)
    return peer.get_by_uid(MxrDeviceUid(remote._uid))

plain = client(uid(0x7D))
plain.tx_hello()
d = heard(plain)
assert (d.serial, d.version) == ('P9SN00000000', __version__), (d.serial, d.version)
assert DeviceFeature.MANAGER in d.features and DeviceFeature.MESH not in d.features, d.features
assert DeviceFeature.CONFIG_INITIALISED in d.features

def role(dev):
    return (DeviceFeature.MESH_MEMBER in dev.features, DeviceFeature.MESH_MASTER in dev.features)

me = client(uid(0x7C), serial='P9SN66660600', version='1.2.3', mesh_device=True)
me.tx_hello()
d = heard(me)
assert (d.serial, d.version) == ('P9SN66660600', '1.2.3'), (d.serial, d.version)
assert DeviceFeature.MESH in d.features, d.features
assert DeviceFeature.MANAGER not in d.features, 'a mesh device announced management'
assert DeviceFeature.CONFIG_INITIALISED in d.features
assert role(d) == (False, False), d.features

me.sent.clear()
me.set_mesh_controller(U(0x11))
assert me.mesh_controller == U(0x11)
assert role(heard(me)) == (True, False), 'following another controller'
me.sent.clear()
me.set_mesh_controller(MxrDeviceUid(me._uid))
assert role(heard(me)) == (True, False), 'the role was announced with no bays mapped'
me.sent.clear()
me.set_mesh_bays_mapped(True)
assert role(heard(me)) == (True, True), 'taking the role was not announced'
me.sent.clear()
me.set_mesh_bays_mapped(True)
assert not me.sent, 'unchanged bays were re-announced'
me.set_mesh_controller(MxrDeviceUid(me._uid))
assert not me.sent, 'an unchanged controller was re-announced'
me.set_mesh_controller(None)
assert role(heard(me)) == (False, False)
assert me.mesh_controller is None
print('announce    : serial, version, mesh device and controller role reach a peer')

# ------------------------------------------------------------- mesh operations
# 40 bytes: the kind, padding, the target, then the parameter, stamped at the
# opcode's row. A controller report puts its priority and installer id in the low
# half of the parameter's first two words.
controller, previous = U(0x43), U(0x44)
mx.sent.clear()
assert call(mx.send_mesh_operation(MeshOperationMessage.promote_controller(controller, previous))) is True
f = mx.sent[-1]
assert opcode(f) == 0x3B and f[2] == 0x1D, f[:24].hex()
p = f[24:]
assert len(p) == 40, len(p)
assert p[:4] == bytes([5, 0, 0, 0])
assert p[4:20] == uid(0x43) and p[20:36] == uid(0x44)
assert p[36:] == bytes(4), 'the trailing padding'

mx.sent.clear()
assert call(mx.send_mesh_operation(MeshOperationMessage.report_controller(controller, 0x0102, 0x0304))) is True
p = mx.sent[-1][24:]
assert p[:4] == bytes([4, 0, 0, 0]) and p[4:20] == uid(0x43)
assert p[20:28] == bytes([0x02, 0x01, 0, 0, 0x04, 0x03, 0, 0]), p[20:28].hex()
assert p[28:] == bytes(12)

for message, kind, param in ((MeshOperationMessage.register(previous, controller), 0, uid(0x43)),
                             (MeshOperationMessage.unregister(previous, controller), 1, uid(0x43)),
                             (MeshOperationMessage.replace(previous, controller), 2, uid(0x43)),
                             (MeshOperationMessage.regenerate_addresses(previous), 3, bytes(16)),
                             (MeshOperationMessage.auto_addresses(previous), 6, bytes(16))):
    mx.sent.clear()
    assert call(mx.send_mesh_operation(message)) is True
    p = mx.sent[-1][24:]
    assert p[:4] == bytes([kind, 0, 0, 0]), f'operation {kind}'
    assert p[4:20] == uid(0x44) and p[20:36] == param, f'operation {kind}'

mx.sent.clear()
assert call(mx.send_mesh_operation(MeshOperationMessage.report_membership(controller))) is True
p = mx.sent[-1][24:]
assert p[:4] == bytes([0xFF, 0, 0, 0]) and p[4:20] == uid(0x43)

for bad in ((0x10000, 0), (0, 0x10000), (-1, 0)):
    try:
        MeshOperationMessage.report_controller(controller, *bad)
    except ValueError:
        continue
    raise AssertionError(f'a controller report of {bad} was built')
print('operations  : each kind, its target and its parameter at their offsets')

# Every operation but the two reports reaches the caller as it arrived, an
# unnamed one with its raw value, and none names the sender's mesh master.
def poisoned(kind, target, param):
    return bytes([kind, 0xA5, 0xA5, 0xA5]) + target + param + bytes([0xA5] * 4)

member = hello(uid(0x50), 0x2F, DeviceFeature.ONEIP_SINK | DeviceFeature.MESH)
for kind in (0, 1, 2, 3, 5, 6, 7, 0x80):
    seen.operations.clear()
    rx(uid(0x50), 0x3B, poisoned(kind, uid(0x41), uid(0x42)))
    assert len(seen.operations) == 1, f'operation {kind:#04x}: {seen.operations}'
    by, op = seen.operations[0]
    assert by is member, by
    assert int(op.operation) == kind and op.target == U(0x41) and op.param == U(0x42), op
    assert isinstance(op.operation, MeshOperation) == (kind != 0x80), repr(op.operation)
    assert member.mesh_master_uid is None, f'operation {kind:#04x} named a mesh master'
seen.operations.clear()
rx(uid(0x50), 0x3B, poisoned(0xFF, uid(0x41), uid(0x42)))
assert member.mesh_master_uid == U(0x41) and not seen.operations, 'a membership report arrived as an operation'
print('received    : every other operation reaches the caller, an unnamed one raw')

# A controller report is the sender's own: priority and installer each the low
# half of a 32-bit word, the installer only from 0x1D.
ctrl = hello(uid(0x51), 0x2F, DeviceFeature.MESH)
changes = []
ctrl.register_callback(lambda dev: changes.append(dev.mesh_controller_report))
report = poisoned(4, uid(0x51), bytes([0x07, 0x01, 0xEF, 0xBE, 0x42, 0x03, 0xFE, 0xCA]) + bytes([0xA5] * 8))
rx(uid(0x51), 0x3B, report, protocol=0x1C)
assert ctrl.mesh_controller_report == MeshControllerReport(priority=0x0107, installer=0), \
    f'an installer was read below the version that carries it: {ctrl.mesh_controller_report}'
changes.clear()
rx(uid(0x51), 0x3B, report, protocol=0x1D)
assert ctrl.mesh_controller_report == MeshControllerReport(priority=0x0107, installer=0x0342), ctrl.mesh_controller_report
assert len(changes) == 1, changes
rx(uid(0x51), 0x3B, report, protocol=0x1D)
assert len(changes) == 1, 'an unchanged report was announced again'

other = hello(uid(0x52), 0x2F, DeviceFeature.MESH)
seen.operations.clear()
rx(uid(0x52), 0x3B, poisoned(4, uid(0x53), bytes(16)))
assert other.mesh_controller_report is None, 'a report about another device was filed on the sender'
assert not seen.operations, 'a controller report arrived as an operation'
print('controller  : a report about its sender is kept, the installer from 0x1D')

# ------------------------------------------------------------- source list
class Stream:
    def __init__(self, ip, port):
        self.ip, self.port = ip, port

class Sources:
    '''An entry for unit n: every address and port distinct, none the same
    reversed, and an audio-return stream that has no place in a record.'''
    def __init__(self, n, with_uid=True):
        self.uid = U(n) if with_uid else None
        self.video, self.audio, self.anc = (Stream(f'239.{n}.{k}.7', 0x5000 + n * 16 + k) for k in (1, 2, 3))
        self.arc = Stream(f'239.{n}.4.7', 0x5000 + n * 16 + 4)

def record(s):
    return s.uid.byte_value + b''.join(ip4(x.ip) + struct.pack('<I', x.port) for x in (s.video, s.audio, s.anc))

short = [Sources(31), Sources(32)]
mx.sent.clear()
assert call(mx.send_oneip_source_list(short)) is True
assert len(mx.sent) == 1
assert opcode(mx.sent[0]) == 0x26 and mx.sent[0][2] == 0x09, mx.sent[0][:24].hex()
assert mx.sent[0][24:] == b''.join(record(s) for s in short)
target = hello(uid(0x54), 0x2F, DeviceFeature.ONEIP_SOURCE)
replay(mx.sent[0], uid(0x54))
assert [(s.uid, s.video.ip, s.video.port, s.anc.port) for s in target.oneip_sources] \
    == [(s.uid, s.video.ip, s.video.port, s.anc.port) for s in short], target.oneip_sources

mx.sent.clear()
assert call(mx.send_oneip_source_list([])) is True
assert len(mx.sent) == 1 and mx.sent[0][24:] == b'', 'an empty list was not sent'

long = [Sources(n + 100) for n in range(40)]
mx.sent.clear()
assert call(mx.send_oneip_source_list(long)) is True
assert len(mx.sent) == 2, len(mx.sent)
for f, (first, records) in zip(mx.sent, ((0, long[:36]), (36, long[36:]))):
    p = f[24:]
    assert p[:2] == struct.pack('<H', first), 'the page\'s first record'
    assert p[2:4] == struct.pack('<H', 40), 'the whole list\'s length'
    assert p[4:8] == bytes(4), 'the reserved bytes'
    assert p[8:] == b''.join(record(s) for s in records)
    assert len(p) <= 8 + 36 * 40, 'a page outgrew the largest payload'
paged = hello(uid(0x55), 0x2F, DeviceFeature.ONEIP_SOURCE)
for f in mx.sent:
    replay(f, uid(0x55))
assert [s.uid for s in paged.oneip_sources] == [s.uid for s in long], 'the pages did not read back as the list'

mx.sent.clear()
assert call(mx.send_oneip_source_list([Sources(33), Sources(34, with_uid=False)])) is False
assert call(mx.send_oneip_source_list([Sources(1)] * (ONEIP_SOURCE_LIST_MAX + 1))) is False
assert not mx.sent, 'a refused list was sent'
print('sources     : bare records, numbered pages past 36, read back as sent')

# ------------------------------------------------------------- writes to an output
# What is set on an output is held once sent, decodes back through the receive
# path to what was set, and a write a unit would drop is refused unsent.
out = sink(0x60)
other_out = sink(0x61)
amp = hello(uid(0x62), 0x2F, DeviceFeature.AUDIO_AMPLIFIER, model='PROAMP8')
assert not amp.is_oneip, 'fixture: the amplifier is no OneIP unit'
bay = out.first_output

mx.sent.clear()
assert call(out.set_oneip_mirroring(other_out)) is True
f = mx.sent[-1]
assert opcode(f) == 0x32 and f[24:] == uid(0x60) + uid(0x61), f[24:].hex()
assert bay.mirroring.is_mirroring and bay.mirroring.target.device == U(0x61), 'not held once sent'
assert call(out.set_oneip_mirroring(None)) is True
assert mx.sent[-1][24:] == uid(0x60) + bytes(16)
assert not bay.mirroring.is_mirroring, 'stopping was not held'
replay(f, MANAGER)
assert bay.mirroring.is_mirroring and bay.mirroring.target.device == U(0x61), 'the sent mirror did not decode'

filtered = [U(0x61), U(0x63)]
mx.sent.clear()
assert call(out.set_oneip_source_filter(filtered)) is True
f = mx.sent[-1]
assert opcode(f) == 0x38 and f[24:] == uid(0x60) + uid(0x61) + uid(0x63), f[24:].hex()
assert list(bay.filtered) == filtered, 'not held once sent'
assert call(out.set_oneip_source_filter([])) is True
assert mx.sent[-1][24:] == uid(0x60) and len(bay.filtered) == 0
replay(f, MANAGER)
assert list(bay.filtered) == filtered, 'the sent filter did not decode'
mx.sent.clear()
assert call(out.set_oneip_source_filter([U(0x61)] * ONEIP_SOURCE_FILTER_MAX)) is True
assert len(mx.sent[-1]) - 24 == (1 + ONEIP_SOURCE_FILTER_MAX) * 16, 'the longest filter was not sent'

mx.sent.clear()
assert call(out.set_oneip_tiling(960, 540, 1920, 1080)) is True
f = mx.sent[-1]
assert opcode(f) == 0x40 and f[24:] == uid(0x60) + struct.pack('<4H', 960, 540, 1920, 1080), f[24:].hex()
t = process_mxr_frame(mx, 0.0, f, ADDR)
assert (t.target_uid, t.position_x, t.position_y, t.width, t.height) == (U(0x60), 960, 540, 1920, 1080), str(t)
print('outputs     : mirroring, filter and tiling go out, are held, and decode back')

# Remote control settings: the unit's 48-byte struct with every switch
# alternating, so a bit moved or a field dropped shows.
mx.sent.clear()
assert call(out.set_rc_settings(rc_target=7, ip='192.168.7.21', cec_enabled=True, cec_auto_on=False,
                                forward_rc=True, forward_ir=False, rc_status=3, status_name='Connected')) is True
f = mx.sent[-1]
assert opcode(f) == 0x45 and f[2] == 0x1D
expected = uid(0x60) + bytes([7, 0, 0, 0]) + bytes([192, 168, 7, 21]) + bytes([0b0011_0101, 0, 0, 0]) \
    + b'Connected' + bytes(7) + bytes(4)
assert f[24:] == expected, f[24:].hex()
r = process_mxr_frame(mx, 0.0, f, ADDR)
assert (r.target_uid, r.ip, r.cec_enabled, r.cec_auto_on, r.rc_forward, r.ir_forward, int(r.rc_status), r.status_name) \
    == (U(0x60), '192.168.7.21', True, False, True, False, 3, 'Connected'), str(r)
mx.sent.clear()
assert call(out.set_rc_settings(rc_target=RCType(1), ip=None,
                                cec_enabled=False, cec_auto_on=True, forward_rc=False, forward_ir=True,
                                rc_status=MXR_RC_STATUS_MAX, status_name='N' * MXR_RC_STATUS_NAME_LEN)) is True
p = mx.sent[-1][24:]
assert p[20:24] == bytes(4) and p[24:28] == bytes([0b1111_1010, 0, 0, 0]), p[20:28].hex()
assert p[28:44] == b'N' * 15 + b'\0', 'the longest text was not sent with its terminator'
print('rc settings : the unit\'s 48-byte struct, the longest text with its NUL')

# Setup and installer go to every unit, read back as the sender's own.
mx.sent.clear()
assert call(mx.set_mesh_setup_completed(True)) is True
assert opcode(mx.sent[-1]) == 0x35 and mx.sent[-1][24:] == bytes([1])
assert call(mx.set_mesh_setup_completed(False)) is True
assert mx.sent[-1][24:] == bytes([0])
assert call(mx.set_mesh_installer(0x1234)) is True
assert opcode(mx.sent[-1]) == 0x37 and mx.sent[-1][24:] == bytes([0x34, 0x12])
mx.sent.clear()
assert call(mx.set_mesh_installer(0x10000)) is False and not mx.sent
print('mesh        : setup completed and installer id to every unit')

# Refusals, none of which sends anything.
mx.sent.clear()
assert call(out.set_oneip_mirroring(out)) is False, 'an output mirroring itself'
assert call(amp.set_oneip_mirroring(None)) is False, 'mirroring on a device that is no OneIP output'
assert call(out.set_oneip_mirroring(amp)) is False, 'mirroring a device that is no OneIP output'
assert call(out.set_oneip_source_filter([U(0x61)] * (ONEIP_SOURCE_FILTER_MAX + 1))) is False
assert call(amp.set_oneip_source_filter([])) is False
assert call(amp.set_oneip_tiling(0, 0, 0, 0)) is False
assert call(out.set_oneip_tiling(0x10000, 0, 0, 0)) is False
rc = dict(rc_target=7, ip='192.168.7.21', cec_enabled=True, cec_auto_on=False, forward_rc=True, forward_ir=False)
assert call(out.set_rc_settings(**rc, rc_status=MXR_RC_STATUS_MAX + 1)) is False
assert call(out.set_rc_settings(**rc, status_name='N' * (MXR_RC_STATUS_NAME_LEN + 1))) is False
assert call(out.set_rc_settings(**rc, status_name='a\0b')) is False
assert call(out.set_rc_settings(**{**rc, 'ip': '192.168.7'})) is False
assert call(amp.set_rc_settings(**rc)) is False
bare = hello(uid(0x64), 0x2F, DeviceFeature.ONEIP_SINK)
assert bare.first_output is None, 'fixture: an output whose bay was never reported'
assert call(bare.set_oneip_mirroring(None)) is False
assert call(bare.set_oneip_source_filter([])) is False
# A matrix has an output bay, so only its not being a OneIP output refuses it.
matrix = hello(uid(0x65), 0x2F, DeviceFeature.VIDEO_ROUTING, model='FF88')
rx(uid(0x65), 0x02, bay_rec(8, 1, 0, 'Matrix out', 0))
assert matrix.first_output is not None and not matrix.is_oneip_sink, 'fixture: a matrix output'
assert call(matrix.set_oneip_mirroring(None)) is False
assert call(matrix.set_oneip_source_filter([])) is False
assert call(out.set_oneip_mirroring(matrix)) is False
assert not mx.sent, f'a refused write was sent: {[s.hex() for s in mx.sent]}'
print('refused     : nothing a unit would drop is sent')

print('ALL OK')
