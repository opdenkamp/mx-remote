######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Pin the wire details that no protocol version signals.

Every case here covers something the frame's own header cannot describe: an
opcode whose payload widened without its protocol floor moving, a struct whose
tail padding is part of its size, a field whose sentinel is not a value, or an
index numbered from a different base than the enum that holds it. A decoder can
be wrong about any of them and still parse every frame it is given, so each case
asserts the decoded meaning rather than that decoding succeeded.

The sizes come from the firmware C structs, measured with a compiler. That
matters for provenance: a vector generated from another client of this same
protocol pins whatever that client does, so two implementations agreeing is
worth nothing wherever both took their expectations from the same place.
'''

import os, socket, struct, sys, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.Uid import MxrDeviceUid
from mx_remote.proto.Factory import create_mxr_frame, process_mxr_frame
from mx_remote.proto.Data import VolumeMuteStatus, MXR_AUDIO_DONT_CHANGE
from mx_remote.proto.Constants import MXR_OPCODE_VERSIONS
from mx_remote.Interface import BayFeaturesMask

UID = bytes(range(1, 17))
ADDR = ('192.0.2.9', 8812)

mx = mx_remote.Remote(open_connection=False)
mx._uid = bytes(range(100, 116))

def nm(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def decode(opcode, payload=b'', uid=UID):
    return process_mxr_frame(mx, time.time(), create_mxr_frame(uid, opcode, payload), ADDR)

def rx(opcode, payload=b'', uid=UID):
    mx.process_frame(time.time(), create_mxr_frame(uid, opcode, payload), ADDR)

FEAT = (1 << 5) | (1 << 6) | (1 << 7) | (1 << 9)
rx(0x00, struct.pack('<H', 0x28) + nm('MX-1') + nm('P8SN12345678') + nm('5.2.0')
        + struct.pack('<I', FEAT))
dev = mx.get_by_uid(MxrDeviceUid(UID))
assert dev is not None, 'a hello must register its sender, or nothing below can run'

AUDIO_OUT = int(BayFeaturesMask.AUDIO_ANA_OUT)
def bay_rec(port, mode, num, name, feat=None):
    if feat is None:
        feat = (1 << 1) if mode == 0 else (1 << 0)
    return (bytes([port, mode, num, 0, 0]) + nm(name) + nm(name) + nm('1080p')
            + struct.pack('<I', 0) + struct.pack('<I', feat))

# A bay at port 254, the low byte of MBAY_PORT_ID_NOT_ROUTED. Truncating the
# sentinel to one byte lands on it, so this bay is what a narrow read of an
# unrouted bay id resolves to. Without it in the fixture, a narrow read and a
# wide read both return None and the two are indistinguishable.
TRUNCATES_TO = 0xFFFE & 0xFF
rx(0x02, bay_rec(0, 0, 0, 'In 1') + bay_rec(1, 1, 0, 'Out 1', feat=AUDIO_OUT))
rx(0x02, bay_rec(TRUNCATES_TO, 1, 1, 'Out 254', feat=AUDIO_OUT))
out = dev.get_by_portnum(1)
assert out is not None
assert dev.get_by_portnum(TRUNCATES_TO) is not None, 'fixture needs a bay at port 254'

# ---------------------------------------------------------------- RC_KEY 0x0B
# The bay id widened to two bytes without RC_KEY's protocol floor moving, so a
# current unit stamps 0x01 on the wide form and only the payload length tells
# the two apart.
assert MXR_OPCODE_VERSIONS[0x0B] == 0x01, 'floor moved; the stamp may now be usable'
assert MXR_OPCODE_VERSIONS[0x0D] == 0x01, 'floor moved; the stamp may now be usable'

f = decode(0x0B, struct.pack('<HH', 1, 20))            # wide: u16 bay, u16 key
assert f.bay is not None and f.bay.port == 1, f.bay
assert f.key is not None and int(f.key) == 20, f.key

f = decode(0x0B, bytes([1]) + struct.pack('<H', 20))   # legacy: u8 bay, u16 key
assert f.bay is not None and f.bay.port == 1, f.bay
assert f.key is not None and int(f.key) == 20, f.key
print('0x0B rckey  : wide and legacy both decode to port 1 key 20')

# MBAY_PORT_ID_NOT_ROUTED read one byte wide is 0xFE, a port a bay can have.
# Truncating it does not merely lose the value, it names a different real bay.
for op in (0x0B, 0x0D):
    f = decode(op, struct.pack('<HH', 0xFFFE, 20))
    assert f.bay is None, 'unrouted bay on 0x%02X resolved to %s' % (op, f.bay)
print('0x0B/0x0D   : unrouted bay 0xFFFE stays unresolved, not the bay at port 254')

# -------------------------------------------------------------- RC_ACTION 0x0D
f = decode(0x0D, struct.pack('<HH', 1, 2))
assert f.bay is not None and f.bay.port == 1, f.bay
assert f.action is not None and int(f.action) == 2, f.action

f = decode(0x0D, bytes([1]) + struct.pack('<H', 2))
assert f.bay is not None and f.bay.port == 1, f.bay
assert f.action is not None and int(f.action) == 2, f.action
print('0x0D action : wide and legacy both decode to port 1 action 2')

# ------------------------------------------------- every command clears its length gate
# Each receiver refuses a payload shorter than its own sizeof before it reads a
# field, so a command short of that is dropped without a reply - which looks
# exactly like one accepted and ignored. The sizes are the C structs', measured
# with a compiler rather than by adding up field widths: mxr_uid is a uint32_t
# array so it aligns to 4, an 8-aligned struct is as wide as its alignment
# rounds it to, and uint_fast16_t is 4 bytes on the target against 8 on a
# 64-bit host, so a host-measured sizeof is wrong for anything holding one.
from mx_remote.proto.FrameSetName import FrameSetName
from mx_remote.proto.FrameMeshOperation import FrameMeshOperation, MeshOperation
from mx_remote.proto.FrameVolumeSet import FrameVolumeSet
from mx_remote.proto.FrameBayHide import FrameBayHide
from mx_remote.proto.FrameEDIDProfile import FrameEDIDProfile
from mx_remote.proto.FrameTXRCKey import FrameTXRCKey
from mx_remote.proto.FrameTXRCAction import FrameTXRCAction
from mx_remote.proto.FrameV2IPSourceSwitch import FrameV2IPSourceSwitch
from mx_remote.proto.FrameV2IPManualSourceSwitch import FrameV2IPManualSourceSwitch
from mx_remote.proto.FrameAmpZoneSettings import FrameAmpZoneSettings
from mx_remote.proto.Constants import RCKey, RCAction
from mx_remote.Interface import EdidProfile, AmpZoneSettings

HDR = 24

def amp_settings():
    s = AmpZoneSettings()
    for n in ('gain_left', 'gain_right', 'volume_min', 'volume_max', 'delay_left',
              'delay_right', 'bass', 'treble', 'bridged', 'power_mode', 'power_level',
              'power_timeout'):
        setattr(s, n, 0)
    s.eq_left = [0] * 5
    s.eq_right = [0] * 5
    return s

# opcode, the struct its receiver sizes against, that sizeof, and how to build one
GATES = [
    (0x0C, 'mxr_tx_key_data',           20, lambda: FrameTXRCKey.construct(mxr=mx, target=out, key=RCKey(10))),
    (0x0E, 'mxr_tx_action_data',        20, lambda: FrameTXRCAction.construct(mxr=mx, target=out, action=RCAction(1))),
    (0x14, 'mxr_set_volume_request',    24, lambda: FrameVolumeSet.construct(mxr=mx, target=out, volume=VolumeMuteStatus(50, 50, False, False))),
    (0x1F, 'mxr_v2ip_switch_data',      24, lambda: FrameV2IPSourceSwitch.construct(mxr=mx, target=out, video='239.1.1.1:5000', audio='239.1.1.2:5000')),
    (0x22, 'mxr_bay_name_data',         40, lambda: FrameSetName.construct(mxr=mx, target=out, name='Kitchen')),
    (0x24, 'mxr_v2ip_full_switch_data', 40, lambda: FrameV2IPManualSourceSwitch.construct(mxr=mx, target=dev,
                video_ip='239.1.1.1', video_port=5000, audio_ip='239.1.1.2', audio_port=5000,
                anc_ip='239.1.1.3', anc_port=5000)),
    (0x27, 'mxr_bay_hidden_data',       24, lambda: FrameBayHide.construct(mxr=mx, target=out, hidden=True)),
    (0x34, 'mxr_bay_edid_profile_data', 24, lambda: FrameEDIDProfile.construct(mxr=mx, target=dev, profile=EdidProfile(1))),
    (0x3B, 'mxr_mesh_operation',        40, lambda: FrameMeshOperation.construct(mxr=mx, operation=MeshOperation.REGISTER, target=dev)),
    (0x3D, 'mxr_amp_zone_settings',     56, lambda: FrameAmpZoneSettings.construct(mxr=mx, target=out, settings=amp_settings())),
]
for opcode, struct_name, size, build in GATES:
    p = build()
    assert p is not None, '0x%02X built nothing' % opcode
    got = len(p.frame) - HDR
    assert got >= size, '0x%02X is %d bytes, the %s gate is %d' % (opcode, got, struct_name, size)
print('length gate : all %d commands clear their receiver sizeof' % len(GATES))

# ------------------------------------------------------- 0x14 mute sentinel and layout
# 0xFF asks the receiver to leave the setting alone. Read as a bitmask it sets
# both channel bits, so a request declining to touch the mute reads as one
# muting the bay.
f = decode(0x14, UID + struct.pack('<H', 1) + bytes([50, 50, MXR_AUDIO_DONT_CHANGE]) + bytes(3))
assert f.muted is None, 'a request leaving the mute alone decoded as %s' % f.muted
assert f.volume_left == 50 and f.volume_right == 50, f
print('0x14 setvol : mute 0xFF decodes as no mute reported')

# The legacy form addresses the target by serial and carries a one-byte bay,
# which moves all three settings down one and makes the payload 20 bytes.
f = decode(0x14, UID + bytes([1, 60, 61, 0]))
assert f.volume_left == 60 and f.volume_right == 61, f
assert f.bay is not None and f.bay.port == 1, f.bay
print('0x14 setvol : legacy 20-byte form decodes to port 1 volume 60/61')

# The port belongs to the device the payload addresses, not to the sender.
f = decode(0x14, UID + struct.pack('<H', 1) + bytes([50, 50, 0]) + bytes(3),
           uid=bytes(range(60, 76)))
assert f.bay is not None and f.bay.port == 1, 'bay resolved against the sender: %s' % f.bay
print('0x14 setvol : bay resolves on the addressed device, not the sender')

# The encoder must be able to say "leave this alone" too, or a mute-only change
# silences the bay and a volume-only change unmutes it.
assert VolumeMuteStatus(None, None, True, True).value[0] == MXR_AUDIO_DONT_CHANGE
assert VolumeMuteStatus(50, 50, None, None).value[2] == MXR_AUDIO_DONT_CHANGE
print('0x14 setvol : unset volume and unset mute both encode as 0xFF')

# ------------------------------------------------------------- multiviewer stamp 0x42
# The stamp is the opcode's floor. Stamping higher than the floor buys nothing -
# the module dispatches on payload length and never reads it - and costs every
# receiver whose own cap falls between the two.
from mx_remote.proto.FrameV2IPMultiviewer import FrameV2IPMultiviewer
from mx_remote.proto.Multiviewer import MultiviewerViewMode
FLOOR = MXR_OPCODE_VERSIONS[0x42]
assert FLOOR == 0x16, FLOOR
p = FrameV2IPMultiviewer.construct_set_view_mode(mxr=mx, target=dev, view_mode=MultiviewerViewMode.SINGLE)
assert p is not None and p.frame[2] == FLOOR, 'stamped 0x%02X, floor is 0x%02X' % (p.frame[2], FLOOR)
print('0x42 mview  : stamped at the opcode floor 0x16')

# ------------------------------------------------- multiviewer sources are zero-based
# The status report and the source command both number sources from zero, the
# same as the audio source beside them. Reading them one-based loses source 1 to
# UNKNOWN and reports every other one as its predecessor.
from mx_remote.proto.Multiviewer import MultiviewerSource, MULTIVIEWER_MAX_SCREENS

def mv_status(sources):
    '''A STATUS payload carrying one wire source byte per screen.'''
    pl = bytearray(UID + bytes([0]) + bytes(7))            # envelope: target, sub-opcode, pad
    pl += bytes(190 - len(pl))
    for i, v in enumerate(sources):
        pl[182 + i] = v
    return bytes(pl)

f = decode(0x42, mv_status([0, 1, 2, 3]))
from mx_remote.proto.FrameV2IPMultiviewer import V2IPMultiviewerConfig
cfg = V2IPMultiviewerConfig(header=f.header)
got = [cfg.video_source(i) for i in range(4)]
assert got == [MultiviewerSource.SOURCE_1, MultiviewerSource.SOURCE_2,
               MultiviewerSource.SOURCE_3, MultiviewerSource.SOURCE_4], got
print('0x42 mview  : wire sources 0..3 decode to SOURCE_1..SOURCE_4')

p = FrameV2IPMultiviewer.construct_set_video_source(mxr=mx, target=dev, screen=0,
                                                    source=MultiviewerSource.SOURCE_4)
assert p is not None and p.frame[24 + 24 + 1] == 3, p.frame[24 + 24 + 1]
print('0x42 mview  : SOURCE_4 is sent as wire index 3, so source 4 is reachable')

# A screen index at the layout's screen count is one past the last window.
assert FrameV2IPMultiviewer.construct_set_video_source(
    mxr=mx, target=dev, screen=2, source=MultiviewerSource.SOURCE_1, screens=2) is None
# A caller that does not know the layout still gets the array width as a bound.
assert FrameV2IPMultiviewer.construct_set_video_source(
    mxr=mx, target=dev, screen=1, source=MultiviewerSource.SOURCE_1, screens=0) is not None
assert FrameV2IPMultiviewer.construct_set_video_source(
    mxr=mx, target=dev, screen=MULTIVIEWER_MAX_SCREENS, source=MultiviewerSource.SOURCE_1) is None
print('0x42 mview  : a screen index past the layout is refused, unknown layout still sends')

# ------------------------------------------------------- 0x3B admission gates
# A mesh operation names the mesh master. Acting on one no device would have
# acted on invents mesh state, and the short case is the dangerous one: the
# operation byte survives a truncated payload and the uid behind it does not.
from mx_remote.proto.FrameMeshOperation import _ACCEPT_PROTOCOL, _INSTALLER_PROTOCOL

def stamped(opcode, payload, protocol):
    '''A frame carrying an arbitrary protocol stamp, as a peer would send it.'''
    f = bytearray(create_mxr_frame(UID, opcode, payload))
    f[2] = protocol
    return process_mxr_frame(mx, time.time(), bytes(f), ADDR)

# Name a second device as the master, so a frame that lands is visible as a
# change rather than as the value the field already held.
PEER = bytes(range(60, 76))
rx(0x00, struct.pack('<H', 0x28) + nm('MX-2') + nm('P8SN87654321') + nm('5.2.0')
        + struct.pack('<I', FEAT), uid=PEER)
peer = mx.get_by_uid(MxrDeviceUid(PEER))
assert peer is not None and peer is not dev

MEMBERSHIP = bytes([MeshOperation.REPORT_MEMBERSHIP.value, 0, 0, 0]) + PEER + bytes(20)
assert len(MEMBERSHIP) == 40

# The gate that admits the frame is below this opcode's own table entry, because
# the entry was raised when a later field was added. Gating on the entry would
# ignore every device between the two versions.
assert _ACCEPT_PROTOCOL < MXR_OPCODE_VERSIONS[0x3B], 'admission gate is not below the table entry'
assert _INSTALLER_PROTOCOL == MXR_OPCODE_VERSIONS[0x3B]

f = stamped(0x3B, MEMBERSHIP, _ACCEPT_PROTOCOL)
assert f.operation == MeshOperation.REPORT_MEMBERSHIP, f.operation
assert f.target_uid == MxrDeviceUid(PEER), f.target_uid

f = stamped(0x3B, MEMBERSHIP, _ACCEPT_PROTOCOL - 1)
assert f.operation is None, 'a frame below the admission gate named %s' % f.operation

f = stamped(0x3B, MEMBERSHIP[:20], MXR_OPCODE_VERSIONS[0x3B])
assert f.operation is None, 'a frame short of the struct named %s' % f.operation
print('0x3B mesh   : admitted at 0x%02X, refused below it and when short' % _ACCEPT_PROTOCOL)

# The consumer is what makes it matter: the mesh master is taken from this
# frame. Read the stored uid rather than the property, which falls back to the
# device itself when no master is set and would hide the write.
assert dev._mesh_master_uid is None, 'fixture already has a mesh master'
stamped(0x3B, MEMBERSHIP[:20], MXR_OPCODE_VERSIONS[0x3B]).process()
assert dev._mesh_master_uid is None, 'a short frame named a master'
stamped(0x3B, MEMBERSHIP, _ACCEPT_PROTOCOL - 1).process()
assert dev._mesh_master_uid is None, 'a frame below the admission gate named a master'
stamped(0x3B, MEMBERSHIP, _ACCEPT_PROTOCOL).process()
assert dev._mesh_master_uid == MxrDeviceUid(PEER), dev._mesh_master_uid
print('0x3B mesh   : only an admitted frame names the mesh master')

# ------------------------------------------------------- 0x0A admission gates
# A receiver requires one timing beyond the struct, not just the struct. The
# extra two bytes read like an off-by-one and are not: a capture carrying no
# timing decodes perfectly as a burst nothing blasted, with nothing to replay.
from mx_remote.proto.FrameRCIr import _MIN_SIZE as IR_MIN, _ACCEPT_PROTOCOL as IR_ACCEPT

def ir_struct(nb_timings=4):
    '''mxr_ir_data with a declared timing count.

    The count is what a receiver acts on, not the number of timings that
    actually arrived, so it is set per case rather than fixed.
    '''
    p = (struct.pack('<H', 1) + bytes(2) + struct.pack('<II', 1, 2)
         + struct.pack('<HHHHB', 2, 38000, nb_timings, 0, 0) + bytes(1) + bytes(2))
    assert len(p) == 24, len(p)
    return p

IR_STRUCT = ir_struct(nb_timings=2)
assert IR_MIN == 26 and IR_ACCEPT == MXR_OPCODE_VERSIONS[0x0A]

f = stamped(0x0A, IR_STRUCT + struct.pack('<2H', 100, 200), IR_ACCEPT)
assert f.acceptable and f.bay is not None and f.bay.port == 1, f.bay
assert f.frequency == 38000, f.frequency

# the struct alone: every field still reads, and the capture holds nothing
f = stamped(0x0A, ir_struct(nb_timings=0), IR_ACCEPT)
assert not f.acceptable, 'a capture with no timing was accepted'
assert f.frequency is None and f.timings == bytes(), f.frequency

f = stamped(0x0A, IR_STRUCT + struct.pack('<2H', 100, 200), IR_ACCEPT - 1)
assert not f.acceptable, 'a frame below the admission gate was accepted'
print('0x0A ir     : needs a timing past the struct and protocol 0x%02X' % IR_ACCEPT)

# Admission and replay are two thresholds, not one: one timing gets the frame
# read, more than one gets something blasted, because the first is dropped.
f = stamped(0x0A, ir_struct(nb_timings=1) + struct.pack('<H', 100), IR_ACCEPT)
assert f.acceptable and not f.replayable, 'one timing is not enough to blast'
f = stamped(0x0A, ir_struct(nb_timings=2) + struct.pack('<2H', 100, 200), IR_ACCEPT)
assert f.replayable, f.nb_timings
print('0x0A ir     : one timing is read, two are replayed')

# The count is a declaration. Nothing ties it to what arrived, and a receiver
# reads that many entries from the payload without checking, so a frame
# claiming more than it carries would walk a device off the end of its buffer.
f = stamped(0x0A, ir_struct(nb_timings=64) + struct.pack('<2H', 100, 200), IR_ACCEPT)
assert not f.acceptable, 'a capture claiming 64 timings while carrying 2 was accepted'
f = stamped(0x0A, ir_struct(nb_timings=2) + struct.pack('<2H', 100, 200), IR_ACCEPT)
assert f.acceptable, 'a capture whose count matches its payload was refused'
print('0x0A ir     : a declared count larger than the payload is refused')

# ---------------------------------------------------- 0x48 targeted IR request
# The same "+one timing" floor, and no protocol gate at all - the handler
# ignores the stamp, so length is the whole test.
from mx_remote.proto.FrameTxIR import FrameTxIR, _MIN_SIZE as TXIR_MIN

def txir_struct(nb_timings=2):
    p = (UID + bytes([1, 0]) + bytes(2) + struct.pack('<I', 1)
         + struct.pack('<HHHHB', 2, 38000, nb_timings, 0, 0) + bytes(1) + bytes(2))
    assert len(p) == 36, len(p)
    return p

TXIR_STRUCT = txir_struct()
assert TXIR_MIN == 38

f = decode(0x48, TXIR_STRUCT + struct.pack('<2H', 100, 200))
assert f.acceptable and f.replayable, f
assert f.carrier_frequency == 38000 and f.local_mode == 1, f
assert f.timings_raw == struct.pack('<2H', 100, 200), f.timings_raw

f = decode(0x48, TXIR_STRUCT)
assert not f.acceptable, 'a request with no timing was accepted'
assert f.carrier_frequency is None and f.timings_raw is None, f.carrier_frequency
f = decode(0x48, txir_struct(nb_timings=64) + struct.pack('<2H', 100, 200))
assert not f.acceptable, 'a request claiming 64 timings while carrying 2 was accepted'
print('0x48 tx ir  : needs a timing past the struct, refuses an inflated count, any stamp')

# ------------------------------------------------ 0x29 one layout per version
# Four layouts have shipped, and the stamp is the only thing that selects them:
# 0x12 and 0x22 are both 144 bytes. Devices still send the older forms, because
# a unit stamps from its own table, and current firmware ignores everything
# below 0x22 - so these paths serve units that no device on the mesh answers.
from mx_remote.proto.FrameNetworkStatus import (NetworkPortStatusImplPre12,
                                                NetworkPortStatusImplPre22,
                                                NetworkPortStatusImpl)

def net_0x06(port=1, name=b'sgmii'):
    d = bytearray(136)                       # the 0x12 layout without its addresses
    d[0] = port
    d[112:112 + len(name)] = name
    return bytes(d)

def net_0x12(port=1, name=b'sgmii', mac=True):
    d = bytearray(152 if mac else 144)       # name at 112, ip at 132, mac at 140
    d[0] = port
    d[112:112 + len(name)] = name
    d[132:136] = bytes([192, 0, 2, 7])
    if mac:
        d[140:146] = bytes(range(0xA0, 0xA6))
    return bytes(d)

def net_0x22(port=1, name=b'sgmii', feat=0x4F):
    d = bytearray(144)                       # name at 4, mac at 21, ip at 28
    d[0:2] = struct.pack('<H', port)
    d[2:4] = struct.pack('<H', feat)
    d[4:4 + len(name)] = name
    d[21:27] = bytes(range(0xA0, 0xA6))
    d[28:32] = bytes([192, 0, 2, 7])
    return bytes(d)

# Each stamp picks its own class, and the name lands in all four.
for stamp, payload, cls in ((0x06, net_0x06(), NetworkPortStatusImplPre12),
                            (0x12, net_0x12(mac=False), NetworkPortStatusImplPre22),
                            (0x21, net_0x12(), NetworkPortStatusImplPre22),
                            (0x22, net_0x22(), NetworkPortStatusImpl)):
    st = stamped(0x29, payload, stamp).status
    assert isinstance(st, cls), (hex(stamp), type(st).__name__)
    assert st.name == 'sgmii', (hex(stamp), st.name)
    assert st.port == 1, (hex(stamp), st.port)
print('0x29 net    : 0x06, 0x12, 0x21 and 0x22 each decode by their own layout')

# The oldest form carries no address at all. Reporting one means reading bytes
# the frame does not have; the later class would find them past its end.
st = stamped(0x29, net_0x06(), 0x06).status
assert st.ip is None and st.mac_address is None, (st.ip, st.mac_address)
# The MAC arrived at 0x21, so a 0x12 report has none even though the class is shared.
assert stamped(0x29, net_0x12(mac=False), 0x12).status.mac_address is None
assert stamped(0x29, net_0x12(), 0x21).status.mac_address == 'A0:A1:A2:A3:A4:A5'
print('0x29 net    : addresses appear at 0x12 and the MAC at 0x21, not before')

# Reading an old frame at the current offsets is not a near miss: the name moves
# and stays printable, so a field-by-field eyeball of the wrong layout passes.
wrong = NetworkPortStatusImpl(data=net_0x12(), protocol=0x22)
assert wrong.name != 'sgmii', wrong.name
print('0x29 net    : the 0x12 form read as 0x22 renames the port')

# ------------------------------------------- 0x42 refusals the module makes silently
# A multiviewer answers no 0x42 set at all. A value it refuses is dropped with
# nothing on the wire to say so, and the only confirmation of any set is the
# next periodic status report - so a value the module would refuse is refused
# here, where the caller can see it.
from mx_remote.proto.Multiviewer import MultiviewerHDCPMode

assert int(MultiviewerHDCPMode.OFF) == 3, 'HDCP OFF is a mode, not the absence of one'
assert FrameV2IPMultiviewer.construct_set_hdcp_mode(
    mxr=mx, target=dev, mode=MultiviewerHDCPMode.OFF) is not None
assert FrameV2IPMultiviewer.construct_set_hdcp_mode(
    mxr=mx, target=dev, mode=MultiviewerHDCPMode.UNKNOWN) is None
assert FrameV2IPMultiviewer.construct_set_audio_volume(
    mxr=mx, target=dev, volume=100, muted=False) is not None
assert FrameV2IPMultiviewer.construct_set_audio_volume(
    mxr=mx, target=dev, volume=101, muted=False) is None
print('0x42 mview  : HDCP OFF is sendable, an unknown mode and volume 101 are not')

# A truncated status report decodes field by field into "the device reported
# nothing", which would replace a good cached status with that. Length is the
# only thing separating the two, and the module refuses the same frame.
from mx_remote.proto.FrameV2IPMultiviewer import _STATUS_MIN_SIZE

def mv_report(size):
    pl = bytearray(UID + bytes([0]) + bytes(7))     # target, STATUS sub-opcode, pad
    pl += bytes(max(0, size - len(pl)))
    pl[169] = 1                                     # a view mode, so a decode would show something
    return bytes(pl[:size])

# Record what reaches the cache, because the fixture device is not a
# multiviewer and would absorb either report without visible effect.
folded = []
real_update = type(dev).on_mxr_update
type(dev).on_mxr_update = lambda self, data: folded.append(type(data).__name__)
try:
    decode(0x42, mv_report(_STATUS_MIN_SIZE - 1)).process()
    assert folded == [], 'a short status report reached the cache: %s' % folded
    decode(0x42, mv_report(_STATUS_MIN_SIZE)).process()
    assert folded == ['V2IPMultiviewerConfig'], folded
finally:
    type(dev).on_mxr_update = real_update
print('0x42 mview  : a report short of the settings block never reaches the cache')

# -------------------------------------------------- a stamp above our own is refused
# The stamp is the version at which that opcode's payload last changed, not the
# sender's version. So a stamp above ours means one opcode's layout is newer
# than we know, which is the set of frames we would decode into wrong state -
# and devices drop them before dispatch, so nothing on the mesh acted on them
# either. A firmware release raises the stamp only of opcodes whose layout
# moved, which is why this silences those rather than the whole mesh.
from mx_remote.proto.Constants import MXR_PROTOCOL_VERSION

seen = []
real = type(dev).on_mxr_update
type(dev).on_mxr_update = lambda self, data: seen.append(type(data).__name__)
try:
    hello = struct.pack('<H', 0x28) + nm('MX-1') + nm('P8SN12345678') + nm('5.2.0') \
            + struct.pack('<I', FEAT)
    f = bytearray(create_mxr_frame(UID, 0x00, hello))
    f[2] = MXR_PROTOCOL_VERSION + 1
    mx.process_frame(time.time(), bytes(f), ADDR)
    assert seen == [], 'a frame stamped past our version was processed: %s' % seen
    f[2] = MXR_PROTOCOL_VERSION
    mx.process_frame(time.time(), bytes(f), ADDR)
    assert seen != [], 'a frame stamped at our version was dropped'
finally:
    type(dev).on_mxr_update = real
print('stamp cap   : a frame needing a newer build is dropped, one at our version is not')

# ------------------------------------------------------- the hello is size-checked
# A receiver tests the hello length for equality, not for a minimum, and creates
# no device record at all when it differs. Every other frame this client sends
# is then dropped for coming from a uid nobody has a record of - which looks
# like a client that never announced, rather than one whose hello was refused.
from mx_remote.proto.FrameHello import FrameHello

hello_frame = FrameHello.construct(mxr=mx)
assert hello_frame is not None
assert (len(hello_frame.frame) - 24) == 54, len(hello_frame.frame) - 24
assert (hello_frame.frame[22] | (hello_frame.frame[23] << 8)) == 54, 'declared length must match'

# The stamp on a hello is the opcode floor, because the hello layout has never
# moved. The sender's own version travels in the payload instead, and it is the
# only place it appears.
assert hello_frame.frame[2] == MXR_OPCODE_VERSIONS[0x00] == 0x01, hello_frame.frame[2]

# Peers read that payload version to decide how long to hold this client online:
# at 0x20 and above the timeout is 15s, below it three minutes. Reporting the
# higher one is only safe while this client re-announces well inside 15s, which
# is what the probe loop's 2.5s + jitter does.
reported = hello_frame.frame[24] | (hello_frame.frame[25] << 8)
assert reported == MXR_PROTOCOL_VERSION, (reported, MXR_PROTOCOL_VERSION)
assert reported >= 0x20, 'the short offline timeout is what the announce interval is paced for'
print('hello       : 54 bytes, stamped 0x01, reporting 0x%02X in the payload' % reported)

# ------------------------------------------- a stranger's frame is not acted on
# A device announces itself before it sends anything else. A frame from a uid
# that has not announced is one that should not exist, so it is decoded and
# reported but never applied - which is what every device on the mesh does with
# it. Hello and discover are the exceptions, because the hello is what makes a
# sender known at all.
#
# The frame has to be one keyed on a target rather than on its sender, or the
# handler does nothing for want of a device record and the gate is untested.
# A manual source switch names its sink in the payload, so it applies to a
# device we know however little we know about the sender.
STRANGER = bytes(range(0x70, 0x80))
SWITCH = (UID + socket.inet_aton('239.1.2.3') + struct.pack('<HH', 5000, 0)
          + socket.inet_aton('239.1.2.4') + struct.pack('<HH', 5001, 0)
          + socket.inet_aton('239.1.2.5') + struct.pack('<HH', 5002, 0))
assert len(SWITCH) == 40

applied = []
real_u = type(dev).on_mxr_update
type(dev).on_mxr_update = lambda self, data: applied.append(type(data).__name__)
try:
    mx.process_frame(time.time(), create_mxr_frame(STRANGER, 0x24, SWITCH), ADDR)
    assert applied == [], "a stranger's route request was applied: %s" % applied

    # the hello is what admits the sender; without that exemption it never can
    mx.process_frame(time.time(), create_mxr_frame(STRANGER, 0x00,
            struct.pack('<H', 0x28) + nm('MX-3') + nm('P8SN00000003') + nm('5.2.0')
            + struct.pack('<I', FEAT)), ADDR)
    assert mx.get_by_uid(MxrDeviceUid(STRANGER)) is not None, \
        'the hello exemption is what makes a sender known'

    mx.process_frame(time.time(), create_mxr_frame(STRANGER, 0x24, SWITCH), ADDR)
    assert applied != [], 'an announced sender must be acted on'
finally:
    type(dev).on_mxr_update = real_u
print("sender gate : a stranger's frame is not applied; its hello admits it")

# The frame is still decoded and reported, because this library is used to
# watch the bus as well as to track it.
import logging as _logging
lines = []
class _Catch(_logging.Handler):
    def emit(self, rec):
        lines.append(rec.getMessage())
_logging.disable(_logging.NOTSET)
_log = _logging.getLogger('mx_remote.remote.Remote')
_lvl, _prop = _log.level, _log.propagate
_log.propagate = False
_log.addHandler(_Catch()); _log.setLevel(_logging.DEBUG)
try:
    quiet = mx_remote.Remote(open_connection=False)
    quiet._uid = bytes(range(100, 116))
    quiet.process_frame(time.time(), create_mxr_frame(STRANGER, 0x24, SWITCH), ADDR)
finally:
    _log.handlers.clear()
    _log.setLevel(_lvl); _log.propagate = _prop
    _logging.disable(_logging.CRITICAL)
assert any('24(' in m for m in lines), 'a stranger frame must still be reported: %s' % lines
print('sender gate : the frame is still decoded and reported for a bus monitor')

# --------------------------------------------------------------- payload length clamp
# A padded datagram declares less than it carries. Length is a layout
# discriminator here, so it has to mean the declared length, not the arrived one.
frame = create_mxr_frame(UID, 0x0B, struct.pack('<HH', 1, 20)) + bytes(8)
f = process_mxr_frame(mx, time.time(), frame, ADDR)
assert len(f.payload) == 4, 'padding past the declared length reached the decoder: %s' % len(f.payload)
assert f.bay is not None and f.bay.port == 1, f.bay
print('clamp       : trailing padding does not reach the payload')

# ------------------------------------------------ factory reset target forms
# 0x3A carries three forms and nothing but the length separates them. Each
# length is a minimum, tested longest first: an update that appends a field
# leaves the uid at 0 where it is, so an exact 16 would read a grown request as
# naming no target - which is the sender resetting itself, a different request.
TARGET = bytes(range(0x50, 0x60))
def reset(pl):
    return process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x3A, pl), ADDR)

f = reset(b'')
assert not f.is_broadcast_all and f.target_uid is None, 'an empty payload names no target'
f = reset(bytes([0xFF]))
assert f.is_broadcast_all and f.target_uid is None
f = reset(TARGET)
assert not f.is_broadcast_all and f.target_uid == MxrDeviceUid(TARGET), f.target_uid
f = reset(TARGET + bytes(8))
assert f.target_uid == MxrDeviceUid(TARGET), 'a grown request still names its target'
assert not f.is_broadcast_all
f = reset(bytes([0xFF]) + bytes(3))
assert f.is_broadcast_all, 'a broadcast that grew a field is still a broadcast'
assert f.target_uid is None, 'four bytes are short of a uid'
# the uid form is tested first, so a uid whose first byte is 0xFF is not a broadcast
FF_FIRST = bytes([0xFF]) + bytes(range(0x51, 0x60))
f = reset(FF_FIRST)
assert f.target_uid == MxrDeviceUid(FF_FIRST), f.target_uid
assert not f.is_broadcast_all, 'a uid starting 0xFF was swallowed by the broadcast form'
print('reset forms : lengths read as minimums, longest first')

print('ALL OK')
