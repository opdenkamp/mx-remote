######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''A frame is not sent to a device that cannot receive it.

Each opcode has a minimum protocol version and a device below it drops the frame
without answering, at three layers and with no NAK, so an ungated send looks
exactly like a successful one.

Both directions are asserted, and at the boundary. A test that only checks the
refusal passes against a gate that refuses everything, and a test that picks one
plausible version exercises only the opcodes whose floors sit above it.
'''

import asyncio, os, struct, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.proto.Factory import create_mxr_frame
from mx_remote.proto.FrameBase import FrameBase

ADDR = ('192.0.2.9', 8812)

def name(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def device(mx, uid, protocol):
    feat = (1 << 5) | (1 << 6)
    mx.process_frame(0.0, create_mxr_frame(uid, 0x00,
        struct.pack('<H', protocol) + name('MX-1') + name('P8SN12345678')
        + name('5.0.0') + struct.pack('<I', feat)), ADDR)
    d = mx.get_by_uid(mx_remote.MxrDeviceUid(uid))
    rec = bytes([0, 1, 0, 0, 0]) + name('Out 1') + name('Out 1') + name('1080p') \
        + struct.pack('<I', 0) + struct.pack('<I', 1)
    mx.process_frame(0.0, create_mxr_frame(uid, 0x02, rec), ADDR)
    return d

def amp_settings():
    s = mx_remote.AmpZoneSettings()
    for n, t in mx_remote.AmpZoneSettings.__annotations__.items():
        setattr(s, n, [0, 0, 0, 0, 0] if 'list' in str(t) else (False if t is bool else 0))
    return s

# floors this suite pins, read from the table rather than restated
F_REBOOT = FrameBase.opcode_protocol(0x28)
F_ACTION = FrameBase.opcode_protocol(0x0E)
F_ZONE   = FrameBase.opcode_protocol(0x3D)
print('floors      : reboot 0x%02X, rc action 0x%02X, amp zone 0x%02X' % (F_REBOOT, F_ACTION, F_ZONE))
assert F_REBOOT < F_ACTION < F_ZONE, 'this suite needs three distinct floors'

def probes(dev, bay):
    return {
        'reboot':    lambda: asyncio.run(dev.reboot()),
        'tx_action': lambda: asyncio.run(bay.tx_action(mx_remote.RCAction.ACTION_POWER_ON)),
        'zone':      lambda: bay.set_zone_settings(amp_settings()),
    }

def check(protocol, expect, uid):
    mx = mx_remote.Remote(open_connection=False)
    mx._uid = bytes(range(0x20, 0x30))
    mx.transmit = lambda data: len(data)          # a wire that always writes fully
    dev = device(mx, uid, protocol)
    bay = dev.get_by_portnum(0)
    got = {k: fn() for k, fn in probes(dev, bay).items()}
    assert got == expect, 'protocol 0x%02X: expected %s, got %s' % (protocol, expect, got)
    print('proto 0x%02X : %s' % (protocol, ', '.join('%s=%s' % kv for kv in sorted(got.items()))))

U = lambda n: bytes([n]) + bytes(range(2, 17))

# below every floor here except reboot's
check(0x01, {'reboot': True, 'tx_action': False, 'zone': False}, U(1))
# exactly at the rc action floor: allowed there, still refused above it
check(F_ACTION, {'reboot': True, 'tx_action': True, 'zone': False}, U(2))
# one below that floor, to pin the boundary rather than straddle it
check(F_ACTION - 1, {'reboot': True, 'tx_action': False, 'zone': False}, U(3))
# current firmware: nothing is refused
check(0x28, {'reboot': True, 'tx_action': True, 'zone': True}, U(4))
# a device that has advertised no version is allowed, not refused
check(0x00, {'reboot': True, 'tx_action': True, 'zone': True}, U(5))

print('ALL OK')
