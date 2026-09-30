######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Reading and writing a V2IP device's VLAN configuration, the block at 176..192.

The block is composed from its declaration, not captured: no unit on hand
reports one yet. Each id has both bytes set and differs from the rest, so a read
at a neighbour's offset or a byte short shows, and the reserved bytes behind
them are poisoned.

Commands are asserted in both directions: every refusal sits next to a write
that goes out, to a device that has reported a block so a send is reachable.
'''

import asyncio, os, struct, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import DeviceFeature, MxrDeviceUid, OneIPDeviceSetting as S, OneIPVlan
from mx_remote.proto.Constants import OneIPVlanFlag as F, ONEIP_VLAN_ID_MAX
from mx_remote.proto.Factory import create_mxr_frame

ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False)
mx._uid = bytes(range(0x20, 0x30))

def uid(n):
    return bytes([n]) * 16

def name(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def rx(sender, opcode, payload=b'', protocol=0x2A):
    frame = bytearray(create_mxr_frame(sender, opcode, payload))
    frame[2] = protocol
    mx.process_frame(0.0, bytes(frame), ADDR)

def hello(sender, features, model='ONEIP'):
    rx(sender, 0x00, struct.pack('<H', 0x2A) + name(model) + name('P8SN12345678')
                   + name('5.0.0') + struct.pack('<I', int(features)))
    return mx.get_by_uid(MxrDeviceUid(sender))

def vlan_block(flags, device, port, uplink, active, revert):
    return struct.pack('<HH3HBBB', int(flags), device, *port, uplink, active, revert) + bytes([0xA5] * 3)

def cfg(subject, block, valid=0, minutes=0):
    '''A whole configuration, a settings block carrying valid, then block.'''
    out = (subject + bytes(24) + bytes([0xFF, 0, 0, 0]) + bytes(4)   # 0..48
           + bytes(80)                                               # arc, scaling, tiling, sink, fpga
           + struct.pack('<IIIbbH', valid, 0, 0, 0, 0, minutes) + bytes(32)
           + block)
    return out

SINK = int(DeviceFeature.ONEIP_SINK) | int(DeviceFeature.VLAN)

# ------------------------------------------------------------------- reading

dev = hello(uid(0x10), SINK)
flags = F.VALID | F.TRUNK | F.PENDING | F.HAS_SFP
frame = cfg(uid(0x10), vlan_block(flags, 0x0123, (0x0456, 0x0789, 0x0ABC), 2, 3, 0x2D))
assert len(frame) == 192, len(frame)
rx(uid(0x10), 0x3C, frame)
v = dev.oneip_vlan
assert v == OneIPVlan(flags=flags, device=0x0123, port=(0x0456, 0x0789, 0x0ABC), uplink=2,
                     active_uplink=3, revert_s=0x2D), v
assert v.trunk and v.is_pending and v.has_sfp
assert (v.pinned_uplink_port, v.active_uplink_port) == (1, 2)
print('decode      :', v)

# A block without its valid bit carries nothing, whatever its other bytes, and
# neither does a frame too short to hold the whole block.
dev = hello(uid(0x11), SINK)
rx(uid(0x11), 0x3C, cfg(uid(0x11), bytes([0xFE]) + bytes([0xA5] * 15)))
assert dev.oneip_vlan is None, 'a block without its valid bit'
rx(uid(0x11), 0x3C, cfg(uid(0x11), vlan_block(F.VALID, 10, (20, 30, 40), 0, 1, 0))[:191])
assert dev.oneip_vlan is None, 'a block cut short'
rx(uid(0x11), 0x3C, cfg(uid(0x11), vlan_block(F.VALID, 10, (20, 30, 40), 0, 1, 0)))
assert dev.oneip_vlan is not None, 'a whole valid block'
print('ignored     : no valid bit, or cut short')

# What a device runs is only the device's to say: a controller's write about
# it, or the confirmation of one, changes nothing here. The write also carries
# a setting, which shows the frame itself was taken.
subject = hello(uid(0x12), SINK)
rx(uid(0x12), 0x3C, cfg(uid(0x12), vlan_block(F.VALID, 10, (20, 30, 40), 0, 1, 0),
                        valid=int(S.AUTO_POWER_SAVE), minutes=10))
ctrl = hello(uid(0x13), int(DeviceFeature.MANAGER), model='Ctrl')
write = bytearray(cfg(uid(0x12), vlan_block(F.VALID | F.CONFIRM, 11, (21, 31, 41), 1, 0, 0),
                      valid=int(S.AUTO_POWER_SAVE), minutes=20))
rx(uid(0x13), 0x3C, bytes(write))
assert subject.oneip_settings.auto_power_save == 20, 'the write itself did not land'
assert subject.oneip_vlan.device == 10, 'a controller\'s write was taken as what the device runs'
assert ctrl.oneip_vlan is None, 'the write was taken as the controller\'s own'
print('ctrl write  : not what the device runs')

# --------------------------------------------------------------------- writing

sent = []
mx.transmit = lambda data: (sent.append(data), len(data))[1]

def call(coro):
    return asyncio.new_event_loop().run_until_complete(coro)

def refused(coro, why):
    n = len(sent)
    assert call(coro) is False, why
    assert len(sent) == n, f'{why}: refused, but transmitted anyway'

# A write carries nothing but the VLAN block, and of that only what a writer
# sets: the flags the device reports or the controller confirms with, the
# uplink in use and the revert seconds go out cleared.
sfp = hello(uid(0x20), SINK)
rx(uid(0x20), 0x3C, cfg(uid(0x20), vlan_block(F.VALID | F.HAS_SFP, 5, (6, 7, 8), 0, 2, 0)))
assert call(sfp.set_oneip_vlan(OneIPVlan(flags=F(0xFFFF), device=0x0123, port=(0x0456, 0x0789, 0x0ABC),
                                       uplink=1, active_uplink=3, revert_s=9))) is True
p = sent[-1][24:]
assert len(p) == 192, 'the payload stops short of the VLAN block'
assert p[:16] == uid(0x20), 'the frame names another device'
assert p[16:40] == bytes(24), 'a source address would repoint the encoder'
assert p[40] == 0xFF, 'the rate is inside the valid range, so it would replace the device\'s'
assert p[41:176] == bytes(135), 'a field between the rate and the VLAN block is set'
assert p[176:] == bytes([0x03, 0x00, 0x23, 0x01, 0x56, 0x04, 0x89, 0x07, 0xBC, 0x0A, 1, 0, 0, 0, 0, 0]), \
    p[176:].hex()
assert sfp.oneip_vlan.device == 5, 'a write was cached before the device ran it'
print('write       :', len(p), 'bytes, nothing but the VLAN block')

# A write the device would not take is refused before it is sent.
no_sfp = hello(uid(0x21), SINK)
rx(uid(0x21), 0x3C, cfg(uid(0x21), vlan_block(F.VALID, 0, (0, 0, 0), 0, 2, 0)))
unreported = hello(uid(0x22), SINK)
without = hello(uid(0x23), int(DeviceFeature.ONEIP_SINK))
rx(uid(0x23), 0x3C, cfg(uid(0x23), vlan_block(F.VALID, 0, (0, 0, 0), 0, 2, 0)))
refused(no_sfp.set_oneip_vlan(OneIPVlan(device=ONEIP_VLAN_ID_MAX + 1)), 'an id above the highest')
refused(no_sfp.set_oneip_vlan(OneIPVlan(port=(0, ONEIP_VLAN_ID_MAX + 1, 0))), 'a port id above the highest')
refused(no_sfp.set_oneip_vlan(OneIPVlan(device=1, uplink=4)), 'an uplink that names no port')
refused(no_sfp.set_oneip_vlan(OneIPVlan(device=1, uplink=1)), 'an SFP uplink on a device without one')
refused(unreported.set_oneip_vlan(OneIPVlan(device=1)), 'a device that has reported no block')
refused(without.set_oneip_vlan(OneIPVlan(device=1)), 'a device without the VLAN feature')
assert call(no_sfp.set_oneip_vlan(OneIPVlan(device=ONEIP_VLAN_ID_MAX, uplink=3))) is True, \
    'the highest id and the last port are taken'
print('refusals    : nothing a device ignores is sent')

# What the builder writes, the decoder reads back as the same block.
rx(uid(0x21), 0x3C, sent[-1][24:])
assert no_sfp.oneip_vlan == OneIPVlan(flags=F.VALID, device=ONEIP_VLAN_ID_MAX, uplink=3), no_sfp.oneip_vlan
print('round trip  :', no_sfp.oneip_vlan)

print('ALL OK')
