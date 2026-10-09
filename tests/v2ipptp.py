######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Reading a V2IP device's PTP state, the block at 192..216 behind its VLAN block.

The block is composed from its declaration, not captured. Each field differs
from the rest, so a read at a neighbour's offset shows, and the three reserved
bytes behind the lock are poisoned.
'''

import os, struct, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import DeviceFeature, MxrDeviceUid
from mx_remote.proto.Constants import OneIPPtpFlag as F, OneIPPtpLock, OneIPPtpMode
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

def cfg(subject, flags):
    '''A whole configuration with an invalid VLAN block, then a PTP state:
    flags, mode 2, domain 0x15, portState 9 and lock 1 at 192..197, three
    poisoned reserved bytes, then the clock identity 0x11..0x18 and the
    grandmaster's 0x21..0x28.'''
    out = (subject + bytes(24) + bytes([0xFF, 0, 0, 0]) + bytes(4)   # 0..48
           + bytes(80) + bytes(48) + bytes(16)                       # ..128, settings, VLAN
           + bytes([int(flags), 2, 0x15, 9, 1]) + bytes([0xA5] * 3)
           + bytes(range(0x11, 0x19)) + bytes(range(0x21, 0x29)))
    assert len(out) == 216, len(out)
    return out

SINK = int(DeviceFeature.ONEIP_SINK)

# Field by field from behind the VLAN block.
dev = hello(uid(0x10), SINK)
rx(uid(0x10), 0x3C, cfg(uid(0x10), F.VALID | F.FOLLOWED))
p = dev.oneip_ptp
assert p is not None, 'no PTP state was read'
assert p.followed
assert p.mode is OneIPPtpMode.AUTO, p.mode
assert p.domain == 0x15, p.domain
assert p.port_state == 9, p.port_state
assert p.lock is OneIPPtpLock.LOCKING, p.lock
assert p.clock_identity == bytes(range(0x11, 0x19)), p.clock_identity.hex()
assert p.grandmaster == bytes(range(0x21, 0x29)), p.grandmaster
print('decode      :', p)

# A block without the valid bit says the device has no state now, replacing
# what it reported before; a frame too short to hold the block says nothing.
dev = hello(uid(0x11), SINK)
whole = cfg(uid(0x11), F.VALID)
rx(uid(0x11), 0x3C, whole)
assert dev.oneip_ptp is not None
rx(uid(0x11), 0x3C, whole[:-1])
assert dev.oneip_ptp is not None, 'a short frame cleared it'
rx(uid(0x11), 0x3C, cfg(uid(0x11), F.FOLLOWED))
assert dev.oneip_ptp is None, 'a block without its valid bit left the old state'
print('cleared     : by a block without its valid bit, not by a short frame')

# Only the device can read its own video processor, so a controller's frame
# about it carries no PTP state, whatever its bytes hold.
subject = hello(uid(0x12), SINK)
rx(uid(0x12), 0x3C, cfg(uid(0x12), F.VALID))
ctrl = hello(uid(0x13), int(DeviceFeature.MANAGER), model='Ctrl')
rx(uid(0x13), 0x3C, cfg(uid(0x12), 0))
assert subject.oneip_ptp is not None, 'a controller\'s frame cleared it'
assert ctrl.oneip_ptp is None, 'the frame was taken as the controller\'s own'
print('ctrl write  : carries no PTP state')

print('ALL OK')
