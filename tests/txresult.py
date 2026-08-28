######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''A command reports success only when its frame was actually sent.

Every one of these methods hands a frame to transmit() and returns a bool. The
bool must follow the send: transmit() returns the number of bytes written, so a
closed or failing socket returns 0 and the command must report False and leave
local state alone.

The comparison is against len(frame.frame), the whole datagram. len(frame) is
the *payload* length, which is always 24 bytes short of what transmit() returns
and can therefore never equal it.
'''

import asyncio, os, struct, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.proto.Factory import create_mxr_frame

UID = bytes(range(1, 17))
ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False)
# construct() needs our own uid; start_async() would load it from disk, and a
# frame builder returns None without one.
mx._uid = bytes(range(0x20, 0x30))

def rx(opcode, payload=b''):
    mx.process_frame(0.0, create_mxr_frame(UID, opcode, payload), ADDR)

def name(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

feat = (1 << 5) | (1 << 6) | int(mx_remote.DeviceFeature.V2IP_SOURCE) \
     | int(mx_remote.DeviceFeature.V2IP_SINK) | int(mx_remote.DeviceFeature.MULTIVIEWER)
rx(0x00, struct.pack('<H', 0x28) + name('MX-1') + name('P8SN12345678')
        + name('5.0.0') + struct.pack('<I', feat))
dev = mx.get_by_uid(mx_remote.MxrDeviceUid(UID))

def bay(port, mode, num, nm, feat=None):
    if feat is None:
        feat = (1 << 1) if mode == 0 else (1 << 0)
    return bytes([port, mode, num, 0, 0]) + name(nm) + name(nm) + name('1080p') \
         + struct.pack('<I', 0) + struct.pack('<I', feat)
rx(0x02, bay(0, 0, 0, 'In 1') + bay(1, 1, 0, 'Out 1')
        + bay(2, 1, 1, 'Sink 1', feat=int(mx_remote.BayFeaturesMask.V2IP_SINK_LOCAL))
        + bay(3, 0, 1, 'V2IP In', feat=int(mx_remote.BayFeaturesMask.V2IP_SOURCE_LOCAL)))
out = dev.get_by_portnum(1)
sink = dev.get_by_portnum(2)
v2src = dev.get_by_portnum(3)

# 0x26 gives the source bay its stream addresses, which the switch builder requires.
# Entries are positional and Device.v2ip_source() indexes by bay number, so send
# two identical good ones rather than depend on which offset applies here.
def entry(ips):
    out = bytes(range(1, 17))
    for ip, port in ips:
        out += bytes(int(x) for x in ip.split('.')) + struct.pack('<H', port) + bytes(2)
    return out
good = entry([('239.1.1.1', 50020), ('239.1.1.2', 50022), ('239.1.1.3', 50021)])
rx(0x26, good + good)
assert v2src.v2ip_source is not None, 'source bay must have v2ip addresses'
print('v2ip source :', v2src.v2ip_source.video)
print('output bay  :', out)
assert out is not None and out.is_output

sent = []
def wire(ok):
    '''Stand in for the socket: full write when ok, nothing written when not.'''
    def tx(data):
        sent.append(data)
        return len(data) if ok else 0
    mx.transmit = tx

# a frame's own length must be what a successful send returns
f = create_mxr_frame(UID, 0x0E, b'\x01\x02\x03')
print('frame bytes :', len(f), 'payload len field:', int.from_bytes(f[22:24], 'little'))
assert len(f) != int.from_bytes(f[22:24], 'little'), 'payload len must not equal frame len'

# State is asserted through hidden and user_name, which mirror what the setter
# wrote. power_status is derived from availability and signal detection as well,
# so it is not a witness for whether a command was applied.

# ---- success path: the command reports success and the state advances
wire(True)
assert asyncio.run(out.power_on()) is True, 'power_on must report success on a full write'
print('power_on    : True on a full write')

wire(True)
assert asyncio.run(out.set_hidden(True)) is True
assert out.hidden is True
print('set_hidden  : True, state applied')

wire(True)
assert asyncio.run(out.set_name('Renamed')) is True
assert out.user_name == 'Renamed'
print('set_name    : True, state applied')

# ---- failure path: nothing written, so nothing may be claimed or cached
wire(False)
assert asyncio.run(out.set_hidden(False)) is False, 'a failed send must report False'
assert out.hidden is True, 'a failed send must not update local state'
print('set_hidden  : False on a failed send, state untouched')

wire(False)
assert asyncio.run(out.set_name('Nope')) is False, 'a failed send must report False'
assert out.user_name == 'Renamed', 'a failed send must not update local state'
print('set_name    : False on a failed send, state untouched')

wire(False)
assert asyncio.run(out.power_off()) is False, 'a failed send must report False'
print('power_off   : False on a failed send')

wire(False)
assert asyncio.run(out.tx_action(mx_remote.RCAction.ACTION_POWER_ON)) is False
print('tx_action   : False on a failed send')

# ---- Device-level commands take the same path, and hold most of the call sites
# (19 of the 25), so a Bay-only suite would leave them unguarded.
assert dev.rebooting is False, 'device must not start out rebooting'
wire(False)
assert asyncio.run(dev.reboot()) is False, 'a failed send must report False'
assert dev.rebooting is False, 'a failed send must not mark the device rebooting'
print('reboot      : False on a failed send, state untouched')

wire(True)
assert asyncio.run(dev.reboot()) is True, 'reboot must report success on a full write'
assert dev.rebooting is True, 'a sent reboot must mark the device rebooting'
print('reboot      : True, state applied')

# ---- every remaining command that guards its send, driven BOTH ways.
# The success direction is what makes the failure direction mean something: a
# method that returns False for an unrelated reason would satisfy the failure
# assertion with its guard deleted, and look covered.
def amp_settings():
    s = mx_remote.AmpZoneSettings()
    for n, t in mx_remote.AmpZoneSettings.__annotations__.items():
        setattr(s, n, [0, 0, 0, 0, 0] if 'list' in str(t) else (False if t is bool else 0))
    return s

def other(enum, current):
    '''A member the setter will actually act on.

    Every multiviewer getter reads UNKNOWN until a config frame arrives, and each
    setter returns True without transmitting when the value already matches. The
    first enum member IS UNKNOWN, so a table built from it never reaches a send
    and passes with the guard deleted.
    '''
    for m in enum:
        if m != current:
            return m
    raise AssertionError('no alternative member in %s' % enum)

mv = dev.multiviewer
COMMANDS = [
    ('Bay.select_edid_profile',   lambda: out.select_edid_profile(list(mx_remote.EdidProfile)[0])),
    ('Bay.set_zone_settings',     lambda: out.set_zone_settings(amp_settings())),
    ('Bay.select_video_source',   lambda: sink.select_video_source(3)),
    ('Bay.select_audio_source',   lambda: sink.select_audio_source('239.1.1.2:50022')),
    ('Device.mesh_promote',       lambda: dev.mesh_promote()),
    ('Device.mesh_remove',        lambda: dev.mesh_remove()),
    ('Device.read_stats',         lambda: dev.read_stats(True)),
    ('MV.set_view_mode',          lambda: mv.set_view_mode(other(mx_remote.MultiviewerViewMode, mv.view_mode))),
    ('MV.set_video_source',       lambda: mv.set_video_source(0, other(mx_remote.MultiviewerSource, mv.video_source(0)))),
    ('MV.set_audio_source',       lambda: mv.set_audio_source(other(mx_remote.MultiviewerSource, mv.audio_source))),
    ('MV.set_audio_volume',       lambda: mv.set_audio_volume(10, False)),
    ('MV.set_edid_template',      lambda: mv.set_edid_template(other(mx_remote.MultiviewerEDIDTemplate, mv.edid_template))),
    ('MV.set_remote_control',     lambda: mv.set_remote_control(other(mx_remote.MultiviewerSource, mv.remote_control))),
    ('MV.set_pip_size',           lambda: mv.set_pip_size(other(mx_remote.MultiviewerPipSize, mv.pip_size))),
    ('MV.set_pip_position',       lambda: mv.set_pip_position(other(mx_remote.MultiviewerPipPosition, mv.pip_position))),
    ('MV.set_screen_aspect',      lambda: mv.set_screen_aspect(other(mx_remote.MultiviewerAspectRatio, mv.screen_aspect))),
    ('MV.set_auto_switch',        lambda: mv.set_auto_switch(True)),
    ('MV.set_output_mode',        lambda: mv.set_output_mode(other(mx_remote.MultiviewerOutputMode, mv.output_mode))),
    ('MV.set_output_itc_mode',    lambda: mv.set_output_itc_mode(other(mx_remote.MultiviewerITCMode, mv.output_itc_mode))),
    ('MV.set_hdcp_mode',          lambda: mv.set_hdcp_mode(other(mx_remote.MultiviewerHDCPMode, mv.hdcp_mode))),
    ('MV.set_connected_source',   lambda: mv.set_connected_source(0, mx_remote.MxrDeviceUid(UID))),
    ('MV.auto_route',             lambda: mv.auto_route()),
]
def invoke(call):
    '''Some of these are coroutines and some are not; the guard is the same.'''
    r = call()
    return asyncio.run(r) if asyncio.iscoroutine(r) else r

for label, call in COMMANDS:
    wire(True)
    assert invoke(call) is True,  label + ' must report success on a full write'
    wire(False)
    assert invoke(call) is False, label + ' must report failure when nothing was written'
print('guarded commands checked both ways:', len(COMMANDS))

print('frames handed to the wire:', len(sent))
assert len(sent) >= 9 + 2 * len(COMMANDS)
print('ALL OK')
