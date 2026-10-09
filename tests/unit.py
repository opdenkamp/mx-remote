######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''A unit's status report (0x4F), and the commands sent to one unit (0x50).

The report is composed from its declaration, not captured: counters above
0xFFFF so a narrowed read shows, addresses whose four bytes differ so a reversed
one shows, nine temperatures claimed where six fit, and a message that fills its
48 bytes with no terminator.

Commands are asserted in both directions: every refusal sits next to a command
that goes out.
'''

import asyncio, os, struct, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import DeviceFeature, MxrDeviceUid, UnitNetConfig
from mx_remote.proto.Constants import UnitCommandFlag, UnitCommandKind, UnitFlag
from mx_remote.proto.Factory import create_mxr_frame, process_mxr_frame

ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False)
mx._uid = bytes(range(0x20, 0x30))

def uid(n):
    return bytes([n]) * 16

def name(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def frame(sender, opcode, payload, protocol=0x2C):
    out = bytearray(create_mxr_frame(sender, opcode, payload))
    out[2] = protocol
    return bytes(out)

def rx(sender, opcode, payload=b'', protocol=0x2C):
    mx.process_frame(0.0, frame(sender, opcode, payload, protocol), ADDR)

def hello(sender, protocol, features, model='ONEIP'):
    rx(sender, 0x00, struct.pack('<H', protocol) + name(model) + name('P8SN12345678')
                   + name('5.0.0') + struct.pack('<I', int(features)), protocol=protocol)
    return mx.get_by_uid(MxrDeviceUid(sender))

ADDRESSES = bytes([10, 1, 2, 3, 255, 255, 254, 0, 10, 1, 2, 254, 8, 8, 4, 4, 9, 9, 9, 10])
NETWORK = UnitNetConfig('10.1.2.3', '255.255.254.0', '10.1.2.254', '8.8.4.4', '9.9.9.10')

def report():
    flags = UnitFlag.DHCP | UnitFlag.BOOT_COUNT | UnitFlag.FAN_SPEED
    out = (struct.pack('<6I', int(flags), 0x00010203, 0x00020304, 0x00030405, 0x00040506, 0x00050607)
           + ADDRESSES + struct.pack('<H', 0x0A0B) + bytes([55, 3, 17, 9])
           + struct.pack('<6b', 41, -5, 60, 61, 62, 63) + b'm' * 48)
    assert len(out) == 104, len(out)
    return out

UNIT = int(DeviceFeature.ONEIP_SINK)

# ------------------------------------------------------------- status report

# Every field at its own offset.
dev = hello(uid(0x10), 0x2C, UNIT)
rx(uid(0x10), 0x4F, report())
s = dev.unit_status
assert s is not None, 'no unit status was read'
assert UnitFlag.DHCP in s.flags
assert s.uptime == 0x00010203, hex(s.uptime)
assert s.boot_count == 0x00020304, s.boot_count
assert s.reboot_count == 0x00030405
assert (s.encoder_health, s.decoder_health) == (0x00040506, 0x00050607)
assert s.network == NETWORK, s.network
assert s.fan_rpm == 0x0A0B, s.fan_rpm
assert (s.fan_duty, s.status, s.net_revert_s) == (55, 3, 17)
assert s.temperatures == (41, -5, 60, 61, 62, 63), f'nine claimed, six fit: {s.temperatures}'
assert s.status_message == 'm' * 48, s.status_message
print('decode      :', s)

# A count or fan speed the flags do not claim is not reported.
unflagged = bytearray(report())
unflagged[0:4] = struct.pack('<I', int(UnitFlag.DHCP))
rx(uid(0x10), 0x4F, bytes(unflagged))
assert (dev.unit_status.boot_count, dev.unit_status.fan_rpm) == (None, None), dev.unit_status
print('flags       : boot count and fan speed only behind their bits')

# The report grows at the back, so a short one is read as far as it goes and
# what it does not reach reads as zero.
short = hello(uid(0x11), 0x2C, UNIT)
rx(uid(0x11), 0x4F, report()[:44])
s = short.unit_status
assert s.network.dns2 == '9.9.9.10', s.network
assert s.fan_rpm == 0, s.fan_rpm
assert s.temperatures == () and s.status_message == '', s
print('short       : read as far as it goes')

# ------------------------------------------------------------------ commands

sent = []
def call(coro):
    return asyncio.new_event_loop().run_until_complete(coro)

def wire():
    def tx(data):
        sent.append(data)
        return len(data)
    mx.transmit = tx

def command():
    out = sent.pop()
    assert int.from_bytes(out[20:22], 'little') == 0x50, out[20:22].hex()
    assert out[2] == 0x2C, f'stamped {out[2]:#x}'
    return out[24:]

def refused(coro, why):
    n = len(sent)
    assert call(coro) is False, why
    assert len(sent) == n, f'{why}: refused, but transmitted anyway'

wire()
unit = hello(uid(0x20), 0x2C, UNIT)
assert call(unit.clear_unit_status()) is True
p = command()
assert len(p) == 20, len(p)
assert p[:16] == uid(0x20), 'the frame names another unit'
assert p[16:20] == bytes(4), 'clear status, no flags'

assert call(unit.upgrade_unit_video_processor(force=True)) is True
assert command()[16:18] == bytes([1, 1]), 'upgrade, forced'
assert call(unit.upgrade_unit_video_processor()) is True
assert command()[16:18] == bytes([1, 0]), 'upgrade, not forced'
assert call(unit.confirm_unit_network()) is True
assert command()[16:18] == bytes([3, 0]), 'confirm'

assert call(unit.set_unit_network(NETWORK)) is True
p = command()
assert len(p) == 40, len(p)
assert p[16:18] == bytes([2, 0]), 'a static network'
assert p[20:40] == ADDRESSES, p[20:40].hex()

assert call(unit.set_unit_dhcp()) is True
p = command()
assert len(p) == 40, 'a network change carries its addresses'
assert p[16:18] == bytes([2, 2]), 'DHCP'
assert p[20:40] == bytes(20)
print('send        : each command names its unit, stamped 0x2C')

# A command goes only to a OneIP unit new enough to take it, and a network a
# unit cannot hold is refused before anything is sent.
old = hello(uid(0x21), 0x2B, UNIT)
refused(old.clear_unit_status(), 'a unit below 0x2C')
matrix = hello(uid(0x22), 0x2C, DeviceFeature.VIDEO_ROUTING, model='FF88')
refused(matrix.clear_unit_status(), 'a device that is not a OneIP unit')
good = UnitNetConfig('10.1.2.3', '255.255.255.0')
assert good.is_valid()
for bad in (UnitNetConfig('0.0.0.0', '255.255.255.0'), UnitNetConfig('239.1.2.3', '255.255.255.0'),
            UnitNetConfig('255.255.255.255', '255.255.255.0'), UnitNetConfig('10.1.2.3', '255.0.255.0'),
            UnitNetConfig('10.1.2.3', '0.0.0.0'), UnitNetConfig('10.1.2', '255.255.255.0'),
            UnitNetConfig('10.1.2.3', '255.255.255.0', dns1='dns')):
    assert not bad.is_valid(), bad
    refused(unit.set_unit_network(bad), f'network [{bad}]')
print('refusals    : old units, non-units and networks a unit cannot hold')

# -------------------------------------------------- a command seen on the wire

# Decoded for the log; a command too short to hold its fields carries none.
p = uid(0x30) + bytes([2, int(UnitCommandFlag.DHCP), 0xA5, 0x5A])
f = process_mxr_frame(mx, 0.0, frame(uid(0x20), 0x50, p[:19]), ADDR)
assert f.command is None and f.flags is None, f
f = process_mxr_frame(mx, 0.0, frame(uid(0x20), 0x50, p), ADDR)
assert f.target_uid == MxrDeviceUid(uid(0x30))
assert f.command is UnitCommandKind.NET_CONFIG, f.command
assert f.flags == UnitCommandFlag.DHCP, f.flags
assert f.network is None, 'a command without addresses'
f = process_mxr_frame(mx, 0.0, frame(uid(0x20), 0x50, p + ADDRESSES), ADDR)
assert f.network == NETWORK, f.network
print('decode cmd  :', f)

print('ALL OK')
