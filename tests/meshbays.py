######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Mesh bays: the OneIP bays a unit lists for other units' inputs and outputs,
built from its bay mappings (0x44) and described by the bays they stand for.

What a unit's bay records say about another unit's bay is its cached copy and
never refreshed, so those records are dropped: the receivers below send them
poisoned ("Stale", signal detected) and nothing may read them back.
'''

import os, struct, sys, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import BayFeaturesMask as F, DeviceFeature, MxrDeviceUid
from mx_remote.proto.Constants import BayStatusMask as S
from mx_remote.proto.Factory import create_mxr_frame

ADDR = ('192.0.2.9', 8812)

class Watching(mx_remote.MxrCallbacks):
    def __init__(self):
        self.seen = []
    def on_bay_registered(self, bay):
        self.seen.append(('registered', bay))
    def on_name_changed(self, bay, user_name):
        self.seen.append(('name', bay, user_name))
    def on_key_pressed(self, bay, key):
        self.seen.append(('key', bay))
    def on_power_changed(self, bay, power):
        self.seen.append(('power', bay))

seen = Watching()
mx = mx_remote.Remote(open_connection=False, callbacks=seen)
mx._uid = bytes(range(0x20, 0x30))

def uid(n):
    return bytes([n]) * 16

def nm(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def rx(sender, opcode, payload=b'', protocol=0x28):
    frame = bytearray(create_mxr_frame(sender, opcode, payload))
    frame[2] = protocol
    mx.process_frame(time.time(), bytes(frame), ADDR)

def hello(sender, protocol, features, serial):
    rx(sender, 0x00, struct.pack('<H', protocol) + nm('ONEIP') + nm(serial) + nm('4.8.0')
                   + struct.pack('<I', int(features)), protocol=0x01)
    return mx.get_by_uid(MxrDeviceUid(sender))

def rec(port, mode, num, name, user, status, features, video=None, audio=None):
    '''A bay record. An output's route bytes default to 0xFF, unrouted; an
    input carries its EDID profile and remote-control type there instead.'''
    unset = 0xFF if (mode == 1) else 0
    video = unset if (video is None) else video
    audio = unset if (audio is None) else audio
    return (bytes([port, mode, num, video, audio]) + nm(name) + nm(user) + nm('1080p')
            + struct.pack('<II', int(status), int(features)))

def page(is_input, first_port, uids):
    '''A 0x44 page as a unit sends it: the count above the direction bit, the
    first port, four poisoned bytes, then one uid per port.'''
    return (struct.pack('<HH', (len(uids) << 1) | int(is_input), first_port) + bytes([0xA5] * 4)
            + b''.join(uids))

def receiver(n):
    '''Its own output on port 127, and the stale records it sends for two mesh
    inputs on ports 1 and 2 and a mesh output on 128.'''
    dev = hello(uid(n), 0x2F, DeviceFeature.ONEIP_SINK, f'RX{n:04}')
    rx(uid(n), 0x02, rec(128, 1, 1, 'Output 2', 'Stale', 0, F.ONEIP_SINK_REMOTE)
                     + rec(1, 0, 1, 'Input 2', 'Stale', S.SIGNAL_DETECTED, F.ONEIP_SOURCE_REMOTE)
                     + rec(2, 0, 2, 'Input 3', 'Stale', S.SIGNAL_DETECTED, F.ONEIP_SOURCE_REMOTE)
                     + rec(127, 1, 0, 'Output 1', 'Lounge', 0, F.HDMI_OUT | F.ONEIP_SINK_LOCAL))
    return dev

def transmitter(owner, name, status=0):
    hello(owner, 0x2F, DeviceFeature.ONEIP_SOURCE, f'TX{owner[0]:04}')
    rx(owner, 0x02, rec(0, 0, 0, 'Input 1', name, status, F.HDMI_IN | F.ONEIP_SOURCE_LOCAL))
    return mx.get_by_uid(MxrDeviceUid(owner)).get_by_portnum(0)

# ---------------------------------------------- the mappings create mesh bays
r = receiver(0x01)
assert r.get_by_portnum(1) is None and r.get_by_portnum(128) is None, 'a mesh bay\'s record was taken'
assert r.get_by_portnum(127) is not None, 'the unit\'s own bay was dropped'
seen.seen.clear()
rx(uid(0x01), 0x44, page(True, 1, [uid(0x02), uid(0x03)]))
for port, owner in ((1, uid(0x02)), (2, uid(0x03))):
    bay = r.get_by_portnum(port)
    assert bay.oneip_uid == MxrDeviceUid(owner)
    assert bay.is_input and not bay.is_local
    assert (bay.bay, bay.bay_name) == (port, f'Input {port + 1}')
    assert ('registered', bay) in seen.seen
rx(uid(0x01), 0x44, page(False, 127, [uid(0x01), uid(0x04)]))
out = r.get_by_portnum(128)
assert out.is_output and not out.is_local
assert (out.bay, out.oneip_uid, out.bay_name) == (1, MxrDeviceUid(uid(0x04)), 'Output 2')
own = r.get_by_portnum(127)
assert own.is_local and own.oneip_uid == MxrDeviceUid(uid(0x01)), 'the unit\'s own bay became a mesh bay'
rx(uid(0x01), 0x44, page(False, 253, [uid(0x06), uid(0x07)]))
assert r.get_by_portnum(253).oneip_uid == MxrDeviceUid(uid(0x06))
assert r.get_by_portnum(254) is None, 'a port past the last bay'
print('mappings    : mesh bays come from the pages, the unit\'s own entry and records do not')

# A unit whose mappings arrive ahead of its bay configuration.
early = hello(uid(0x21), 0x2F, DeviceFeature.ONEIP_SOURCE, 'TX0002')
rx(uid(0x21), 0x44, page(True, 126, [uid(0x21), uid(0x06)]))
assert early.get_by_portnum(126) is None, 'the unit stood for itself'
assert early.get_by_portnum(127) is None, 'an input ran into the outputs'

# ----------------------------------------- released firmware numbers its ports split
rel = hello(uid(0x24), 0x27, DeviceFeature.ONEIP_SINK, 'RX0003')
rx(uid(0x24), 0x44, page(True, 1, [uid(100 + i) for i in range(17)]))
for port, number in ((1, 1), (15, 15), (32, 16), (33, 17)):
    bay = rel.get_by_portnum(port)
    assert bay.is_input and bay.bay == number, port
assert rel.get_by_portnum(16) is None, 'an input on an output\'s port'
rx(uid(0x24), 0x44, page(False, 16, [uid(0x24), uid(130), uid(131)]))
for port, number in ((17, 1), (18, 2)):
    bay = rel.get_by_portnum(port)
    assert bay.is_output and bay.bay == number, port
rx(uid(0x24), 0x44, page(False, 143, [uid(140), uid(141)]))
assert rel.get_by_portnum(143).bay == 16 and rel.get_by_portnum(144).is_output
rx(uid(0x24), 0x44, page(True, 142, [uid(140), uid(141)]))
assert rel.get_by_portnum(142).bay == 126 and rel.get_by_portnum(143).is_output
fixed = hello(uid(0x29), 0x2B, DeviceFeature.ONEIP_SINK, 'RX0005')
rx(uid(0x29), 0x44, page(True, 16, [uid(0x30)]))
assert fixed.get_by_portnum(16).is_input, 'from 0x2B a unit numbers its ports fixed'
print('ports       : split below 0x2B, across the split by bay number; fixed from it')

# A released unit's output names its source in the same split numbering, before
# the mapping that creates that source's bay.
rr = hello(uid(0x31), 0x27, DeviceFeature.ONEIP_SINK, 'RX0006')
for port, is_input in ((15, True), (17, False), (31, False), (32, True), (142, True), (143, False)):
    rx(uid(0x31), 0x02, rec(16, 1, 0, 'Output 1', 'Lounge', 0, F.HDMI_OUT | F.ONEIP_SINK_LOCAL, port, port))
    rx(uid(0x31), 0x44, page(True, port, [uid(0x60)]))
    routed = rr.get_by_portnum(16).video_source
    if is_input:
        assert routed is rr.get_by_portnum(port), f'port {port}: {routed}'
    else:
        assert routed is None, f'port {port} is no input: {routed}'
print('routes      : a route names its source in the unit\'s own numbering, before its bay exists')

# ------------------------------------------- whole pages, and zero uids skipped
r = receiver(0x08)
short = page(True, 1, [uid(0x09), uid(0x0A)])[:8 + 16 + 15]
rx(uid(0x08), 0x44, short)
assert r.get_by_portnum(1) is None, 'a short page was taken'
rx(uid(0x08), 0x44, page(True, 1, [uid(0x09), bytes(16), uid(0x0A)]))
assert r.get_by_portnum(1).oneip_uid == MxrDeviceUid(uid(0x09))
assert r.get_by_portnum(2) is None, 'a zero uid was mapped'
assert r.get_by_portnum(3).oneip_uid == MxrDeviceUid(uid(0x0A)), 'the entry after a zero uid'
rx(uid(0x08), 0x44, page(True, 1, [bytes(16)]))
assert r.get_by_portnum(1).oneip_uid == MxrDeviceUid(uid(0x09)), 'a zero uid took a mapping away'
print('pages       : taken whole; a zero uid maps nothing and takes nothing away')

# ---------------------------------------------- described by the bay it stands for
r = receiver(0x0B)
rx(uid(0x0B), 0x44, page(True, 1, [uid(0x0C)]))
mesh = r.get_by_portnum(1)
assert mesh.user_name == 'Input 2', 'named before its unit is known: %s' % mesh.user_name
assert not mesh.signal_detected, 'the stale record\'s signal'
# What the receiver says about the bay is its own copy, and changes nothing,
# even while the bay it stands for is unknown.
seen.seen.clear()
rx(uid(0x0B), 0x05, bytes([1, 1]))
assert seen.seen == [] and mesh.power_status != mx_remote.PowerStatus.ON, \
    'a status frame about a mesh bay moved it: %s' % seen.seen
owner = transmitter(uid(0x0C), 'Apple TV', S.SIGNAL_DETECTED)
assert (mesh.port, mesh.bay_name, mesh.bay, mesh.is_local) == (1, 'Input 2', 1, False)
assert F.ONEIP_SOURCE_REMOTE in mesh.features
assert mesh.oneip_uid == MxrDeviceUid(uid(0x0C))
assert mesh.user_name == 'Apple TV' and mesh.signal_detected, (mesh.user_name, mesh.signal_detected)
print('described   : a mesh bay reads the bay it stands for, keeping only its identity')

# A change to that bay is reported for the mesh bay too; a request on it is not.
seen.seen.clear()
transmitter(uid(0x0C), 'Kodi')
assert seen.seen.count(('name', mesh, 'Kodi')) == 1, seen.seen
assert seen.seen.count(('name', owner, 'Kodi')) == 1, seen.seen
seen.seen.clear()
rx(uid(0x0C), 0x0B, struct.pack('<HH', 0, int(mx_remote.RCKey.KEY_1)))
assert seen.seen == [('key', owner)], 'a key press was repeated for the mesh bay: %s' % seen.seen
print('mirrored    : a change to the owner is reported for its mesh bays, a request is not')

# A page pointing a mesh bay at another unit reports it under that unit's name.
r = receiver(0x0F)
transmitter(uid(0x11), 'Kodi')
rx(uid(0x0F), 0x44, page(True, 1, [uid(0x10)]))
mesh = r.get_by_portnum(1)
seen.seen.clear()
rx(uid(0x0F), 0x44, page(True, 1, [uid(0x11)]))
assert ('name', mesh, 'Kodi') in seen.seen and not any(e[0] == 'registered' for e in seen.seen), seen.seen
seen.seen.clear()
rx(uid(0x0F), 0x44, page(True, 1, [uid(0x11)]))
assert seen.seen == [], 'an unchanged page: %s' % seen.seen
print('remapped    : reported under the name of the unit it now stands for')

# A unit with no input of its own describes none of the mesh bays standing for
# its inputs, and what happens to its own mesh bays is not theirs.
r = receiver(0x19)
other = receiver(0x1A)
rx(uid(0x1A), 0x44, page(True, 1, [uid(0x1B)]))
rx(uid(0x19), 0x44, page(True, 1, [uid(0x1A)]))
mesh = r.get_by_portnum(1)
seen.seen.clear()
rx(uid(0x1A), 0x44, page(True, 1, [uid(0x1C)]))
assert not any(e[1] is mesh for e in seen.seen), seen.seen
print('no input    : a unit without an input of its own describes no mesh input')

# --------------------------------------- a route before its mapping, and names
rt = hello(uid(0x12), 0x2F, DeviceFeature.ONEIP_SINK, 'RX0002')
rx(uid(0x12), 0x02, rec(127, 1, 0, 'Output 1', 'Lounge', 0, F.HDMI_OUT | F.ONEIP_SINK_LOCAL, 2, 2))
sink = rt.get_by_portnum(127)
assert sink.video_source is None
rx(uid(0x12), 0x44, page(True, 2, [uid(0x13)]))
assert sink.video_source is rt.get_by_portnum(2), 'a route named before its mapping was lost'
print('early route : a route names a mesh input before its mapping creates it')

r = receiver(0x14)
transmitter(uid(0x15), 'Apple TV')
rx(uid(0x14), 0x44, page(True, 1, [uid(0x15)]))
out = r.get_by_portnum(127)
assert out.bay_by_user_name('Apple TV') is r.get_by_portnum(1)
assert out.bay_by_user_name('Stale') is None
transmitter(uid(0x15), 'Apple TV', S.HIDDEN)
assert out.bay_by_user_name('Apple TV') is None, 'a hidden source was offered'
print('by name     : a mesh input is found by its owner\'s name, and not while it is hidden')

print('ALL OK')
