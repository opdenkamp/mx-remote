######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''The group a OneIP device sends its live preview to: the last four bytes of its
settings block, read only from the device's own report.

Reserved bytes ahead of the group are poisoned, so a group read from a
neighbour's offset shows.
'''

import os, struct, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import DeviceFeature as D, MxrDeviceUid, OneIPDeviceSetting as S
from mx_remote.proto.Constants import ONEIP_PREVIEW_PORT
from mx_remote.proto.Factory import create_mxr_frame

ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False)
mx._uid = bytes(range(0x20, 0x30))
mx.transmit = lambda data, to=None: len(data)

def uid(n):
    return bytes([n]) * 16

def name(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def rx(sender, opcode, payload=b'', protocol=0x30):
    frame = bytearray(create_mxr_frame(sender, opcode, payload))
    frame[2] = protocol
    mx.process_frame(0.0, bytes(frame), ADDR)

def hello(sender, features, protocol=0x30, model='ONEIP'):
    rx(sender, 0x00, struct.pack('<H', protocol) + name(model) + name('P8SN%08d' % sender[0]) + name('5.0.0')
                   + struct.pack('<I', int(features)), protocol=0x01)
    return mx.get_by_uid(MxrDeviceUid(sender))

def preview_cfg(subject, group, size=256):
    '''A configuration about subject whose settings block, with a downmix, the
    preview group and locale NL_NL behind it, is cut to size.'''
    out = bytearray(subject + bytes(24) + bytes([0xFF]) + bytes(87))
    out += struct.pack('<II', int(S.STATUS_LED), int(S.STATUS_LED)) + bytes(40)  # 128..176 settings
    out += bytes(16) + bytes(24) + bytes(16)                                     # VLAN, PTP state, own block
    out += struct.pack('<IBBBBB', 0b11, 2, 1, 77, 9, 6) + bytes([0xA5] * 3)      # 232..244
    out += bytes(int(b) for b in group.split('.')) + b'NL_NL\0\0\0'
    assert len(out) == 256, len(out)
    return bytes(out[:size])

SINK = D.ONEIP_SINK | D.CONFIG_INITIALISED
GROUP = '239.7.8.9'
assert ONEIP_PREVIEW_PORT == 50024

dev = hello(uid(0x10), SINK)
ctrl = hello(uid(0x11), D.MANAGER, model='Ctrl')
assert dev.oneip_preview is None, 'a preview before any report'

# Every configuration fires the device's callbacks while it applies the details,
# ahead of the preview, so what a callback reads is what shows the change.
seen = []
watch = lambda d: seen.append(d.oneip_preview)
dev.register_callback(watch)
rx(uid(0x10), 0x3C, preview_cfg(uid(0x10), GROUP))
assert dev.oneip_preview == GROUP, dev.oneip_preview
assert seen[-1] == GROUP, 'a new preview group was not announced'
assert dev.oneip_locale == 'NL_NL', 'the locale behind it was not read'
print('own report  : names the group, announced')

rx(uid(0x11), 0x3C, preview_cfg(uid(0x10), '239.1.1.1'))
rx(uid(0x11), 0x3C, preview_cfg(uid(0x10), '0.0.0.0'))
assert dev.oneip_preview == GROUP, "another sender's frame changed the group"
assert ctrl.oneip_preview is None, "another sender's frame was taken as its own"
print('others      : leave it alone')

rx(uid(0x10), 0x3C, preview_cfg(uid(0x10), GROUP, size=255))
assert dev.oneip_preview == GROUP, 'a block too short for the locale lost the group'
assert dev.oneip_locale == 'NL_NL', 'a block too short to say changed the locale'
rx(uid(0x10), 0x3C, preview_cfg(uid(0x10), GROUP, size=247))
assert dev.oneip_preview is None, 'a block too short kept the group'
rx(uid(0x10), 0x3C, preview_cfg(uid(0x10), GROUP))
assert dev.oneip_preview == GROUP, dev.oneip_preview
rx(uid(0x10), 0x3C, preview_cfg(uid(0x10), '0.0.0.0'))
assert dev.oneip_preview is None, 'a group of 0 kept the group'
assert seen[-1] is None, 'a dropped preview group was not announced'
dev.unregister_callback(watch)
print('none        : from a group of 0 or a block too short')

print('ALL OK')
