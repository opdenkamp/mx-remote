######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''What a mesh controller announces for the whole mesh, and the broadcasts that
set it: the time zone (0x4B), the time (0x4D), and settings for every V2IP
device (0x4C).

Each broadcast is asserted in both directions: the frame that goes out, and a
refusal of what every device would ignore, which sends nothing.
'''

import asyncio, os, struct, sys, time, logging
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import MxrDeviceUid, V2IPDeviceSetting as S, V2IPDeviceSettings, V2IPPowerSaveSchedule
from mx_remote.proto.Constants import (V2IP_IR_PROFILE_MAX, V2IP_IR_PROFILE_NOT_SET,
                                       V2IP_MINUTES_PER_DAY)
from mx_remote.proto.Factory import create_mxr_frame

ADDR = ('192.0.2.9', 8812)
CTRL = bytes(range(1, 17))

def name(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

mx = mx_remote.Remote(open_connection=False)
mx._uid = bytes(range(0x20, 0x30))
sent = []
mx.transmit = lambda data: (sent.append(data), len(data))[1]

def rx(opcode, payload, protocol=0x2A):
    frame = bytearray(create_mxr_frame(CTRL, opcode, payload))
    frame[2] = protocol
    mx.process_frame(time.time(), bytes(frame), ADDR)

rx(0x00, struct.pack('<H', 0x2A) + name('ONEIP') + name('TZ0001') + name('5.0.0')
         + struct.pack('<I', int(mx_remote.DeviceFeature.V2IP_SINK)))
ctrl = mx.get_by_uid(MxrDeviceUid(CTRL))

def call(coro):
    return asyncio.run(coro)

def refused(coro, why):
    n = len(sent)
    assert call(coro) is False, why
    assert len(sent) == n, f'{why}: refused, but transmitted anyway'

def opcode(frame):
    return int.from_bytes(frame[20:22], 'little')

# ------------------------------------------------------------------ time zone

# A 0x4B a mesh controller sent: the IANA name in a 48-byte field, then the
# POSIX rule in a 64-byte one.
CAPTURED_TIME_ZONE = bytes.fromhex(
    '4575726f70652f416d7374657264616d' + '00' * 32
    + '3c2b30313e2d313c2b30323e2c4d332e352e302c4d31302e352e302f33' + '00' * 35)
assert len(CAPTURED_TIME_ZONE) == 112
changes = []
ctrl.register_callback(lambda dev: changes.append(dev.time_zone))
rx(0x4B, CAPTURED_TIME_ZONE)
rx(0x4B, CAPTURED_TIME_ZONE)
tz = ctrl.time_zone
assert tz.zone == 'Europe/Amsterdam', tz
assert tz.rule == '<+01>-1<+02>,M3.5.0,M10.5.0/3', tz
assert changes == [tz], f'a repeat was reported as a change: {changes}'
# One byte short of a different zone, so a frame read anyway would show.
rx(0x4B, (b'UTC'.ljust(48, b'\0') + b'UTC0'.ljust(64, b'\0'))[:111])
assert ctrl.time_zone == tz, 'a short frame was read'
print('tz read     :', tz)

sent.clear()
assert call(mx.set_mesh_time_zone('Europe/Amsterdam', 'CET-1CEST,M3.5.0,M10.5.0/3')) is True
frame = sent.pop()
assert opcode(frame) == 0x4B and frame[2] == 0x2A, (opcode(frame), frame[2])
p = frame[24:]
assert len(p) == 112, len(p)
assert p[:16] == b'Europe/Amsterdam' and p[16:48] == bytes(32)
assert p[48:74] == b'CET-1CEST,M3.5.0,M10.5.0/3' and p[74:] == bytes(38)
for zone, rule in (('', 'UTC0'), ('UTC', ''), ('Z' * 48, 'UTC0'), ('UTC', 'R' * 64), ('UT\0C', 'UTC0')):
    refused(mx.set_mesh_time_zone(zone, rule), f'{zone!r} {rule!r}')
assert call(mx.set_mesh_time_zone('Z' * 47, 'R' * 63)) is True, 'the longest names that fit'
print('tz write    : two NUL-padded fields; what a device could not hold is refused')

# ----------------------------------------------------------------------- time

# A 0x4D a mesh controller sent: seconds since 1970 as a little-endian u32.
rx(0x4D, bytes([0xC6, 0x8F, 0xBB, 0x6A]))
announced = datetime.fromtimestamp(0x6ABB8FC6, timezone.utc)
ahead = ctrl.clock - announced
assert timedelta(0) <= ahead < timedelta(seconds=5), ahead
# Have that frame arrive a minute ago: the clock moves on from it.
ctrl._clock = mx_remote.DeviceClock(utc=ctrl._clock.utc, received=ctrl._clock.received - 60)
ahead = ctrl.clock - announced
assert timedelta(seconds=60) <= ahead < timedelta(seconds=65), ahead
rx(0x4D, bytes([0xFF, 0x8F, 0xBB]))
assert ctrl._clock.utc == 0x6ABB8FC6, 'a short frame was read'
print('time read   :', announced.isoformat(), 'moved on by', ahead)

sent.clear()
assert call(mx.set_mesh_time(announced)) is True
frame = sent.pop()
assert opcode(frame) == 0x4D and frame[2] == 0x2A
assert frame[24:] == bytes([0xC6, 0x8F, 0xBB, 0x6A]), frame[24:].hex()
epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
for when in (epoch - timedelta(seconds=1), epoch + timedelta(seconds=1 << 32)):
    refused(mx.set_mesh_time(when), f'{when}')
assert call(mx.set_mesh_time()) is True, 'now'
assert abs(int.from_bytes(sent.pop()[24:], 'little') - time.time()) < 5, 'now is not now'
print('time write  : seconds since 1970 in a u32; outside that is refused')

# ---------------------------------------------------- settings for every device

# The bare settings block, to everyone, and nothing cached until a device
# reports it.
sink = mx.get_by_uid(MxrDeviceUid(CTRL))
sent.clear()
assert call(mx.set_all_v2ip_device_settings(V2IPDeviceSettings(
    valid=S.STATUS_LED | S.AUTO_POWER_SAVE, flags=S.STATUS_LED, auto_power_save=0x0304))) is True
frame = sent.pop()
assert opcode(frame) == 0x4C and frame[2] == 0x2A
p = frame[24:]
assert len(p) == 48, len(p)
assert struct.unpack('<II', p[:8]) == ((1 << 11) | (1 << 3), 1 << 3), p[:8].hex()
assert p[14:16] == bytes([0x04, 0x03]), 'the idle minutes'
assert sink.v2ip_settings is None, 'a write for everyone was cached before any device took it'
print('all write   : the block alone, to everyone, nothing cached')

for why, settings in (
        ('nothing carried', V2IPDeviceSettings()),
        ('the clock bit', V2IPDeviceSettings(valid=S.CLOCK_SET)),
        ('the stored profiles', V2IPDeviceSettings(valid=S.IR_PROFILES)),
        ('a profile out of range', V2IPDeviceSettings(valid=S.IR_PROFILE, ir_profile=V2IP_IR_PROFILE_MAX)),
        ('an output profile out of range', V2IPDeviceSettings(valid=S.IR_PROFILE_SINK,
                                                              ir_profile_sink=V2IP_IR_PROFILE_NOT_SET - 1)),
        ('minutes past the field', V2IPDeviceSettings(valid=S.AUTO_POWER_SAVE, auto_power_save=0x10000)),
        ('a time past midnight', V2IPDeviceSettings(valid=S.POWER_SAVE_SCHEDULE, power_save=V2IPPowerSaveSchedule(
            start=(V2IP_MINUTES_PER_DAY,) * 7)))):
    refused(mx.set_all_v2ip_device_settings(settings), why)
for ok in (V2IPDeviceSettings(valid=S.IR_PROFILE, ir_profile=V2IP_IR_PROFILE_MAX - 1),
           V2IPDeviceSettings(valid=S.IR_PROFILE_SINK, ir_profile_sink=V2IP_IR_PROFILE_NOT_SET),
           V2IPDeviceSettings(valid=S.POWER_SAVE_SCHEDULE, power_save=V2IPPowerSaveSchedule(
               start=(V2IP_MINUTES_PER_DAY - 1,) * 7))):
    assert call(mx.set_all_v2ip_device_settings(ok)) is True, f'{ok} was refused'
print('all refused : what every device would ignore is not sent')

print('ALL OK')
