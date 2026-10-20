######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Reading and writing a V2IP device's settings, the block behind the processor word.

Each setting sits behind its own bit in a valid mask, so a device reports only
the settings it has and a controller changes one without restating the rest.
What a controller's write leaves in the cache is asserted apart from what the
device's own report does, because the device takes only part of a write.

Commands are asserted in both directions: a refusal means something only next
to a send that goes out, and the fixture device reports its settings first so
that a send is reachable at all.
'''

import asyncio, os, struct, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import DeviceFeature, MxrDeviceUid, OneIPDeviceSetting as S
from mx_remote.proto.Constants import (OneIPVideoProcessorFeature, ONEIP_IR_PROFILE_MAX,
                                       ONEIP_IR_PROFILE_NOT_SET, ONEIP_MINUTES_PER_DAY)
from mx_remote.proto.Factory import create_mxr_frame

ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False)
# A builder returns None without our own uid, which start_async() would load
# from disk. Ours must differ from every peer below: process_frame() drops any
# frame carrying it.
mx._uid = bytes(range(0x20, 0x30))

def uid(n):
    return bytes([n]) * 16

def name(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def rx(sender, opcode, payload=b'', protocol=0x28):
    # create_mxr_frame() stamps protocol 1, which several receivers refuse; the
    # stamp is the third header byte.
    frame = bytearray(create_mxr_frame(sender, opcode, payload))
    frame[2] = protocol
    mx.process_frame(0.0, bytes(frame), ADDR)

def hello(sender, features, model='ONEIP'):
    rx(sender, 0x00, struct.pack('<H', 0x28) + name(model) + name('P8SN12345678')
                   + name('5.0.0') + struct.pack('<I', int(features)))
    return mx.get_by_uid(MxrDeviceUid(sender))

SINK = int(DeviceFeature.ONEIP_SINK) | int(DeviceFeature.VIDEO_ROUTING)
ALL = 0x7FF
FPGA = int(OneIPVideoProcessorFeature.SOURCE_DSCP | OneIPVideoProcessorFeature.SINK_STATE)

def cfg(subject, valid, flags=0, profiles=0, profile=0, profile_sink=0, fpga=0):
    '''A whole configuration, the settings block at 128 and two poisoned
    reserved bytes behind it.'''
    out = (subject + bytes(24)                                       # 0..40  uid, source
           + bytes([0xFF, 0, 0, 0]) + bytes(4)                       # 40..48 options
           + bytes(8) + bytes(8) + bytes(24)                         # arc, scaling, tiling
           + bytes(32) + struct.pack('<Q', fpga)                     # sink, processor word
           + struct.pack('<IIIbb', valid, flags, profiles, profile, profile_sink)
           + bytes([0xA5, 0xA5]))
    assert len(out) == 144, len(out)
    return out

def cfg_ps(subject, valid, flags=0, minutes=0, start=(0,) * 7, end=(0,) * 7):
    '''A whole configuration from a sender that has the power save schedule:
    the idle minutes at 142, the start times at 144, the end times at 158, and
    four poisoned reserved bytes.'''
    out = (cfg(subject, valid, flags)[:142] + struct.pack('<H', minutes)
           + struct.pack('<7H7H', *start, *end) + bytes([0xA5] * 4))
    assert len(out) == 176, len(out)
    return out

# ------------------------------------------------------------------- reading

# Every field carries a distinct value, so one read at a neighbour's offset
# shows, and the reserved bytes behind them are poisoned.
dev = hello(uid(0x01), SINK)
ON = int(S.SINK_CHECK_POWER | S.STATUS_LED | S.CEC_COMBO_INPUT)
rx(uid(0x01), 0x3C, cfg(uid(0x01), ALL, ON, profiles=0b101, profile=3, profile_sink=-1, fpga=FPGA))
s = dev.oneip_settings
assert s is not None, 'a device did not report its own settings'
assert int(s.valid) == ALL, hex(s.valid)
assert s.get(S.SINK_CHECK_POWER) is True
assert s.get(S.SINK_OFF_NO_SIGNAL) is False
assert s.get(S.STATUS_LED) is True
assert s.get(S.NETWORK_LED) is False
assert s.get(S.CEC_COMBO_INPUT) is True
assert s.stored_ir_profiles == 0b101, s.stored_ir_profiles
assert s.ir_profile == 3, s.ir_profile
assert s.ir_profile_sink == -1, 'the sign was lost'
assert int(dev.oneip_features) == FPGA, 'the block moved the processor word'
print('decode      :', s)

# The settings were appended, so a sender that predates them stops short, and
# one byte short of the block is not the block.
older = hello(uid(0x02), SINK)
rx(uid(0x02), 0x3C, cfg(uid(0x02), ALL)[:143])
assert older.oneip_details is not None, 'the frame was dropped'
assert older.oneip_settings is None, 'a block one byte short was read'
rx(uid(0x02), 0x3C, cfg(uid(0x02), ALL))
assert older.oneip_settings is not None, 'the whole block was not read'
print('length      : 143 bytes carries none, 144 carries the block')

# A frame carrying some settings leaves the others as they were.
rx(uid(0x01), 0x3C, cfg(uid(0x01), int(S.STATUS_LED | S.IR_PROFILE), 0, profile=2))
s = dev.oneip_settings
assert s.get(S.STATUS_LED) is False
assert s.get(S.SINK_CHECK_POWER) is True, 'a setting the frame did not carry was changed'
assert s.ir_profile == 2, s.ir_profile
assert s.ir_profile_sink == -1, 'a profile the frame did not carry was changed'
assert s.stored_ir_profiles == 0b101, 'the stored profiles the frame did not carry were changed'
assert int(s.valid) == ALL, hex(s.valid)
print('partial     : one setting moved, the rest kept')

# The settings block of a 0x3C a unit sent about itself: every setting up to the
# clock bit, the clock set, 15 idle minutes and no power save window. The zero
# schedule leaves the schedule's offsets unpinned; the synthetic frame below
# covers them.
CAPTURED_SETTINGS = bytes.fromhex(
    'ff3f0000' '1c200000' '07000000' '00ff0f00' + '00' * 32)
captured = hello(uid(0x06), SINK)
rx(uid(0x06), 0x3C, cfg(uid(0x06), 0)[:128] + CAPTURED_SETTINGS)
s = captured.oneip_settings
assert int(s.valid) == 0x3FFF, hex(s.valid)
assert s.get(S.CLOCK_SET) is True
assert s.get(S.STATUS_LED) is True
assert s.get(S.SINK_CHECK_POWER) is False
assert s.stored_ir_profiles == 7, s.stored_ir_profiles
assert s.ir_profile == 0, s.ir_profile
assert s.ir_profile_sink == ONEIP_IR_PROFILE_NOT_SET, s.ir_profile_sink
assert s.auto_power_save == 15, s.auto_power_save
assert all(s.power_save_schedule.window(d) is None for d in range(7)), s.power_save_schedule
print('captured    :', s)

# Each day's start and end time sit at their own offset. Every time is
# distinct, so one read from a neighbour's offset shows.
PS = int(S.AUTO_POWER_SAVE | S.POWER_SAVE_SCHEDULE)
START, END = (1320, 1321, 1322, 1323, 1324, 60, 0), (420, 421, 422, 423, 424, 600, 0)
sched = hello(uid(0x07), SINK)
rx(uid(0x07), 0x3C, cfg_ps(uid(0x07), PS, minutes=300, start=START, end=END))
s = sched.oneip_settings
assert s.auto_power_save == 300, s.auto_power_save
assert (s.power_save_schedule.start, s.power_save_schedule.end) == (START, END), s.power_save_schedule
assert s.power_save_schedule.window(0) == (1320, 420), 'past midnight'
assert s.power_save_schedule.window(6) is None, 'a day without a window'
assert s.power_save_schedule.window(7) is None, 'past Sunday'
print('schedule    :', s.power_save_schedule)

# A sender whose block ends at the idle minutes reports those, and a bit
# claiming a schedule its frame is too short to hold is not a schedule.
short = hello(uid(0x08), SINK)
rx(uid(0x08), 0x3C, cfg_ps(uid(0x08), PS, minutes=45, start=(60,) * 7, end=(120,) * 7)[:171])
s = short.oneip_settings
assert s.auto_power_save == 45, s.auto_power_save
assert s.power_save_schedule is None, 'a schedule was read from a frame too short to hold it'
print('short       : 171 bytes carries the idle minutes and no schedule')

# ------------------------------------------------- a controller's write, read
# The device applies a setting only if it has it and a profile only within its
# range, and the list of stored profiles is its own. Caching more would report a
# change the device never made.
HAS = int(S.FAN_QUIET | S.IR_PROFILE | S.IR_PROFILE_SINK | S.IR_PROFILES)
subject = hello(uid(0x03), SINK)
ctrl = hello(uid(0x04), int(DeviceFeature.MANAGER), model='Ctrl')
rx(uid(0x03), 0x3C, cfg(uid(0x03), HAS, 0, profiles=0b11, profile=1, profile_sink=1))

rx(uid(0x04), 0x3C, cfg(uid(0x03), int(S.FAN_QUIET | S.STATUS_LED | S.IR_PROFILE | S.IR_PROFILES),
                        int(S.FAN_QUIET | S.STATUS_LED), profiles=0xFFFF, profile=ONEIP_IR_PROFILE_MAX))
s = subject.oneip_settings
assert s.get(S.FAN_QUIET) is True, 'the write itself did not land'
assert s.ir_profile == 1, 'an out-of-range profile was cached'
assert s.get(S.STATUS_LED) is None, 'a setting the device does not have was cached'
assert s.stored_ir_profiles == 0b11, 'a third party rewrote the profiles only the device knows'
assert ctrl.oneip_settings is None, 'the settings landed on the sender instead'

# The output port follows the global one at NOT_SET, which is in range there.
for profile, taken in ((ONEIP_IR_PROFILE_NOT_SET, True), (ONEIP_IR_PROFILE_NOT_SET - 1, False),
                       (ONEIP_IR_PROFILE_MAX - 1, True), (ONEIP_IR_PROFILE_MAX, False)):
    rx(uid(0x03), 0x3C, cfg(uid(0x03), HAS, 0, profiles=0b11, profile=1, profile_sink=5))
    rx(uid(0x04), 0x3C, cfg(uid(0x03), int(S.IR_PROFILE_SINK), profile_sink=profile))
    got = subject.oneip_settings.ir_profile_sink
    assert got == (profile if taken else 5), f'a write of {profile} to the output port read back {got}'

# A device that has reported no settings has none a write could land on, so
# the write leaves nothing behind - not even an empty record, which would read
# as a device that has reported.
silent = hello(uid(0x05), SINK)
rx(uid(0x04), 0x3C, cfg(uid(0x05), int(S.FAN_QUIET), int(S.FAN_QUIET)))
assert silent.oneip_details is not None, 'the write itself was dropped'
assert silent.oneip_settings is None, 'a write about a silent device invented its settings'

# Whether a device's clock is set is only the device's to say.
CLOCKED = int(S.CLOCK_SET | S.AUTO_POWER_SAVE)
rx(uid(0x03), 0x3C, cfg_ps(uid(0x03), CLOCKED, 0, minutes=10))
rx(uid(0x04), 0x3C, cfg_ps(uid(0x03), CLOCKED, CLOCKED, minutes=20))
s = subject.oneip_settings
assert s.auto_power_save == 20, 'the write itself did not land'
assert s.get(S.CLOCK_SET) is False, 'a controller set the device\'s clock bit'
print('ctrl write  : cached as far as the device takes it')

# --------------------------------------------------------------------- writing

sent = []
def wire(ok):
    '''Stand in for the socket: full write when ok, nothing written when not.'''
    def tx(data):
        sent.append(data)
        return len(data) if ok else 0
    mx.transmit = tx

def call(coro):
    return asyncio.new_event_loop().run_until_complete(coro)

def refused(coro, why):
    n = len(sent)
    assert call(coro) is False, why
    assert len(sent) == n, f'{why}: refused, but transmitted anyway'

wire(True)
target = hello(uid(0x10), SINK)
refused(target.set_oneip_setting(S.FAN_QUIET, True), 'a device that has reported no settings')
rx(uid(0x10), 0x3C, cfg(uid(0x10), int(S.FAN_QUIET | S.SINK_OFF_NO_SIGNAL | S.CEC_COMBO_KEYS
                                       | S.IR_PROFILE | S.IR_PROFILE_SINK), 0))

# The success case first, which gives every refusal below its meaning. The
# bytes ahead of the block are the assertion: a source address repoints the
# encoder, a rate in range replaces the device's, a scaling validity bit
# rewrites its scaling.
assert call(target.set_oneip_setting(S.FAN_QUIET, True)) is True
p = sent[-1][24:]
assert len(p) == 176, 'the payload stops short of the settings'
assert p[0:16] == uid(0x10), 'the frame names another device'
assert p[16:40] == bytes(24), 'a source address would repoint the encoder'
assert p[40] == 0xFF, 'the rate is inside the valid range, so it would replace the device\'s'
assert p[41:128] == bytes(87), 'a field between the rate and the settings block is set'
assert struct.unpack('<IIIbb', p[128:142]) == (int(S.FAN_QUIET), int(S.FAN_QUIET), 0, 0, 0), \
    struct.unpack('<IIIbb', p[128:142])
assert p[142:] == bytes(34), 'the idle minutes, schedule and reserved bytes'
assert target.oneip_settings.get(S.FAN_QUIET) is True, \
    'reading back before the device reports shows the old value'
assert call(target.set_oneip_setting(S.FAN_QUIET, False)) is True
assert struct.unpack('<II', sent[-1][24 + 128:24 + 136]) == (int(S.FAN_QUIET), 0)
assert target.oneip_settings.get(S.FAN_QUIET) is False
print('write       :', len(p), 'bytes, nothing but the settings block')

refused(target.set_oneip_setting(S.STATUS_LED, True), 'a setting the device does not have')
for setting in (S(0), S.IR_PROFILE, S.IR_PROFILES, S.FAN_QUIET | S.IR_PROFILE):
    refused(target.set_oneip_setting(setting, True), f'{setting!r} is not a set of on/off settings')
for profile in (-1, ONEIP_IR_PROFILE_MAX):
    refused(target.set_oneip_ir_profile(profile), f'global profile {profile}')
for profile in (-2, ONEIP_IR_PROFILE_MAX):
    refused(target.set_oneip_sink_ir_profile(profile), f'output profile {profile}')
assert call(target.set_oneip_ir_profile(ONEIP_IR_PROFILE_MAX - 1)) is True
assert call(target.set_oneip_sink_ir_profile(ONEIP_IR_PROFILE_NOT_SET)) is True
print('refusals    : nothing a device ignores is sent')

# The power save writes put each value at its offset in the block, behind its
# own bit.
power = hello(uid(0x12), SINK)
rx(uid(0x12), 0x3C, cfg_ps(uid(0x12), PS))
assert call(power.set_oneip_auto_power_save(0x0102)) is True
block = sent[-1][24 + 128:]
assert struct.unpack('<I', block[:4])[0] == int(S.AUTO_POWER_SAVE), 'valid'
assert block[14:16] == bytes([0x02, 0x01]), 'the idle minutes'
schedule = mx_remote.OneIPPowerSaveSchedule(start=(1, 2, 3, 4, 5, 6, 7), end=(8, 9, 10, 11, 12, 13, 1439))
assert call(power.set_oneip_power_save_schedule(schedule)) is True
block = sent[-1][24 + 128:]
assert struct.unpack('<I', block[:4])[0] == int(S.POWER_SAVE_SCHEDULE), 'valid'
assert struct.unpack('<14H', block[16:44]) == tuple(range(1, 14)) + (1439,)
assert power.oneip_settings.auto_power_save == 0x0102
assert power.oneip_settings.power_save_schedule == schedule
print('power save  : each value behind its own bit')

late = mx_remote.OneIPPowerSaveSchedule(end=(0, 0, 0, ONEIP_MINUTES_PER_DAY, 0, 0, 0))
refused(power.set_oneip_power_save_schedule(late), 'a time that is not a time of day')
refused(power.set_oneip_auto_power_save(0x10000), 'more minutes than the field holds')
only_schedule = hello(uid(0x13), SINK)
rx(uid(0x13), 0x3C, cfg_ps(uid(0x13), int(S.POWER_SAVE_SCHEDULE)))
refused(only_schedule.set_oneip_auto_power_save(5), 'a setting the device does not have')

nosink = hello(uid(0x11), SINK)
rx(uid(0x11), 0x3C, cfg(uid(0x11), int(S.IR_PROFILE), 0))
refused(nosink.set_oneip_sink_ir_profile(0), 'a port the device does not have')

# A write the socket dropped reports failure and leaves the cache alone.
before = target.oneip_settings
wire(False)
assert call(target.set_oneip_setting(S.FAN_QUIET, True)) is False, 'a failed send reported success'
assert target.oneip_settings == before, 'a failed send moved the cache'
wire(True)
print('send failed : False, cache unmoved')

# ----------------------------------------------------------------------- PTP
PTP = int(S.PTP_MODE | S.PTP_DOMAIN | S.PTP_PRIORITY1)
def cfg_ptp(subject, valid, ptp, flags=0):
    '''As cfg_ps() with no power save, then the PTP mode, domain and priority1 at
    172, 173 and 174. The reserved byte behind them stays poisoned.'''
    out = bytearray(cfg_ps(subject, valid, flags))
    out[172:175] = bytes(ptp)
    return bytes(out)

# One byte each behind the schedule. Each value differs, so one read from a
# neighbour's offset shows, and priority1 has its top bit set, so a signed read
# shows too.
ptp = hello(uid(0x20), SINK)
rx(uid(0x20), 0x3C, cfg_ptp(uid(0x20), PTP, (2, 0x5A, 0x80)))
s = ptp.oneip_settings
assert s.ptp_mode is mx_remote.OneIPPtpMode.AUTO, s.ptp_mode
assert s.ptp_domain == 0x5A, s.ptp_domain
assert s.ptp_priority1 == 0x80, s.ptp_priority1
print('ptp         :', s)

# A bit claiming PTP settings its frame is too short to hold is not a setting.
ptp_short = hello(uid(0x21), SINK)
rx(uid(0x21), 0x3C, cfg_ptp(uid(0x21), PTP | int(S.AUTO_POWER_SAVE), (1, 3, 4))[:174])
s = ptp_short.oneip_settings
assert s.auto_power_save == 0, 'the settings it holds'
assert (s.ptp_mode, s.ptp_domain, s.ptp_priority1) == (None, None, None), s
print('ptp short   : 174 bytes carries no PTP settings')

# A controller's PTP write is cached only within the ranges a device takes.
rx(uid(0x20), 0x3C, cfg_ptp(uid(0x20), PTP, (1, 3, 4)))
rx(uid(0x04), 0x3C, cfg_ptp(uid(0x20), PTP, (3, 128, 9)))
s = ptp.oneip_settings
assert s.ptp_priority1 == 9, 'the write itself did not land'
assert s.ptp_mode is mx_remote.OneIPPtpMode.FOLLOWER, 'an unnamed mode was cached'
assert s.ptp_domain == 3, 'a domain past the last was cached'
print('ptp ctrl    : cached as far as the device takes it')

# Each write puts its byte at its offset in the block, behind its own bit.
for setter, value, bit, at in ((ptp.set_oneip_ptp_mode, mx_remote.OneIPPtpMode.FOLLOWER, S.PTP_MODE, 44),
                               (ptp.set_oneip_ptp_domain, 0x7F, S.PTP_DOMAIN, 45),
                               (ptp.set_oneip_ptp_priority1, 0x80, S.PTP_PRIORITY1, 46)):
    assert call(setter(value)) is True, bit
    block = sent[-1][24 + 128:]
    assert struct.unpack('<I', block[:4])[0] == int(bit), f'{bit!r}: valid'
    assert block[44:48] == bytes([int(value) if i == at else 0 for i in range(44, 48)]), block[44:48].hex()
s = ptp.oneip_settings
assert (s.ptp_mode, s.ptp_domain, s.ptp_priority1) == (mx_remote.OneIPPtpMode.FOLLOWER, 0x7F, 0x80), s
refused(ptp.set_oneip_ptp_mode(3), 'a PTP mode with no name')
refused(ptp.set_oneip_ptp_domain(mx_remote.ONEIP_PTP_DOMAIN_MAX + 1), 'a PTP domain past the last')
refused(ptp.set_oneip_ptp_priority1(0x100), 'a priority1 past the field')
refused(power.set_oneip_ptp_domain(1), 'a setting the device does not have')
print('ptp write   : each value behind its own bit, nothing out of range sent')

# ------------------------------------------------------------ power save level
# The last byte of the block, which a sender stopping at the PTP settings does
# not reach.
level = hello(uid(0x22), SINK)
LEVEL = int(S.POWER_SAVE_LEVEL | S.AES67)
def cfg_level(subject, valid, lvl, flags=0):
    out = bytearray(cfg_ptp(subject, valid, (0, 0, 0), flags))
    out[175] = lvl
    return bytes(out[:176])
rx(uid(0x22), 0x3C, cfg_level(uid(0x22), LEVEL, 2, flags=int(S.AES67)))
s = level.oneip_settings
assert s.power_save_level is mx_remote.OneIPPowerSaveLevel.LOW, s.power_save_level
assert s.get(S.AES67) is True, 'AES67 is an on/off setting'
rx(uid(0x22), 0x3C, cfg_level(uid(0x22), LEVEL, 2)[:175])
assert level.oneip_settings.power_save_level is mx_remote.OneIPPowerSaveLevel.LOW, \
    'a frame too short for the level moved it'
rx(uid(0x04), 0x3C, cfg_level(uid(0x22), LEVEL, 7))
assert level.oneip_settings.power_save_level is mx_remote.OneIPPowerSaveLevel.LOW, 'an unnamed level was cached'
print('level       :', level.oneip_settings)

assert call(level.set_oneip_power_save_level(mx_remote.OneIPPowerSaveLevel.OFF)) is True
block = sent[-1][24 + 128:]
assert struct.unpack('<I', block[:4])[0] == int(S.POWER_SAVE_LEVEL)
assert block[44:48] == bytes([0, 0, 0, 3]), block[44:48].hex()
assert level.oneip_settings.power_save_level is mx_remote.OneIPPowerSaveLevel.OFF
assert call(level.set_oneip_setting(S.AES67, False)) is True, 'AES67 is not switched'
assert level.oneip_settings.get(S.AES67) is False
refused(level.set_oneip_power_save_level(4), 'a power save level with no name')
refused(ptp.set_oneip_power_save_level(mx_remote.OneIPPowerSaveLevel.LOW), 'a setting the device does not have')
print('level write : the last byte of the block, nothing unnamed sent')

# Power save disabled is a switch, and a level, ours or another sender's,
# switches it off unless the same frame states it. A unit without the bit never
# reports it, so the switch is refused there like any setting it lacks.
DIS = int(S.POWER_SAVE_DISABLED)
rx(uid(0x22), 0x3C, cfg_level(uid(0x22), LEVEL | DIS, 1, flags=DIS))
assert level.oneip_settings.get(S.POWER_SAVE_DISABLED) is True
rx(uid(0x04), 0x3C, cfg_level(uid(0x22), int(S.POWER_SAVE_LEVEL), 2))
assert level.oneip_settings.get(S.POWER_SAVE_DISABLED) is False, "another sender's level left it on"
rx(uid(0x22), 0x3C, cfg_level(uid(0x22), LEVEL | DIS, 2, flags=DIS))
assert level.oneip_settings.get(S.POWER_SAVE_DISABLED) is True, 'a level stating the bit cleared it'
assert call(level.set_oneip_power_save_level(mx_remote.OneIPPowerSaveLevel.OFF)) is True
assert level.oneip_settings.get(S.POWER_SAVE_DISABLED) is False, 'our level left it on'
assert call(level.set_oneip_setting(S.POWER_SAVE_DISABLED, True)) is True
assert struct.unpack('<II', sent[-1][24 + 128:24 + 136]) == (DIS, DIS)
refused(ptp.set_oneip_setting(S.POWER_SAVE_DISABLED, True), 'a unit that never reported the bit')
print('ps disabled : a switch, and a level switches it off')

# The cloud connection is a switch too. A unit without the bit connects
# regardless, and never reports it, so the switch is refused there.
CLOUD = int(S.CLOUD)
rx(uid(0x22), 0x3C, cfg_level(uid(0x22), LEVEL | CLOUD, 2, flags=CLOUD))
assert level.oneip_settings.get(S.CLOUD) is True
assert call(level.set_oneip_setting(S.CLOUD, False)) is True
assert struct.unpack('<II', sent[-1][24 + 128:24 + 136]) == (CLOUD, 0)
refused(ptp.set_oneip_setting(S.CLOUD, True), 'a unit that never reported the cloud bit')
print('cloud       : a switch, refused where it was never reported')

# ---------------------------------------------------------- PTP message block
# The values travel behind the PTP state at 216, in a block of their own. Each
# differs and the intervals are negative, so an unsigned read or a neighbour's
# offset shows; the reserved bytes behind them are poisoned.
MSG = int(S.PTP_ANNOUNCE | S.PTP_SYNC | S.PTP_DELAY_REQ | S.PTP_ANNOUNCE_TIMEOUT | S.PTP_DSCP
          | S.SAP_EXPIRE | S.SAP_INTERVAL | S.SAP_LISTEN | S.SAP_ANNOUNCE)
def cfg_msg(subject, valid, block, flags=0):
    out = cfg_level(subject, valid, 0, flags) + bytes(16) + bytes(24) + bytes(block)
    assert len(out) >= 216
    return out
BLOCK = (0xFD, 0xFE, 0x01, 3, 46, 0xA5, 0x2C, 0x01)
msg = hello(uid(0x23), SINK)
rx(uid(0x23), 0x3C, cfg_msg(uid(0x23), MSG, BLOCK, flags=int(S.SAP_LISTEN)))
assert msg.oneip_settings.get(S.SAP_LISTEN) is True and msg.oneip_settings.get(S.SAP_ANNOUNCE) is False
m = msg.oneip_settings.ptp_messages
assert (m.sap_expire_min, m.sap_interval_s) == (0xA5, 300), m
assert (m.log_announce_interval, m.log_sync_interval, m.log_delay_req_interval) == (-3, -2, 1), m
assert (m.announce_timeout, m.dscp) == (3, 46), m
print('ptp msgs    :', msg.oneip_settings)

# A frame too short for the block carries none of its bits.
msg_short = hello(uid(0x24), SINK)
rx(uid(0x24), 0x3C, cfg_msg(uid(0x24), MSG | int(S.AES67), BLOCK)[:223])
s = msg_short.oneip_settings
assert s.ptp_messages is None and s.get(S.AES67) is False, s
print('msgs short  : 223 bytes carries none of the block')

# A controller's DSCP above 63 is not cached; the rest of its write is.
rx(uid(0x04), 0x3C, cfg_msg(uid(0x23), int(S.PTP_DSCP | S.PTP_SYNC), (0, 0x02, 0, 0, 64, 0, 0, 0)))
m = msg.oneip_settings.ptp_messages
assert m.log_sync_interval == 2, 'the write itself did not land'
assert m.dscp == 46, 'a DSCP above 63 was cached'
assert m.log_announce_interval == -3, 'a value the write did not carry moved'

# A write carrying one runs on to 224 bytes; any other keeps its 176.
assert call(msg.set_oneip_ptp_messages(S.PTP_ANNOUNCE | S.PTP_DSCP,
                                       mx_remote.OneIPPtpMessages(log_announce_interval=-1, dscp=63))) is True
p = sent[-1][24:]
assert len(p) == 224, len(p)
assert struct.unpack('<I', p[128:132])[0] == int(S.PTP_ANNOUNCE | S.PTP_DSCP)
assert p[176:216] == bytes(40), 'the VLAN block and PTP state carry something'
assert p[216:224] == bytes([0xFF, 0, 0, 0, 63, 0, 0, 0]), p[216:].hex()
assert call(msg.set_oneip_ptp_messages(S.SAP_INTERVAL, mx_remote.OneIPPtpMessages(sap_interval_s=0x1234))) is True
assert sent[-1][24 + 216:] == bytes([0, 0, 0, 0, 0, 0, 0x34, 0x12]), sent[-1][24 + 216:].hex()
assert call(msg.set_oneip_setting(S.SAP_ANNOUNCE, True)) is True, 'SAP announce is a switch'
assert len(sent[-1]) == 24 + 176, 'a switch carried the block'
m = msg.oneip_settings.ptp_messages
assert (m.log_announce_interval, m.dscp, m.log_sync_interval) == (-1, 63, 2), m
assert m.sap_expire_min == 0xA5, 'a SAP value the write did not carry moved'
assert call(msg.set_oneip_power_save_level(mx_remote.OneIPPowerSaveLevel.LOW)) is False, 'a setting it lacks'
assert call(level.set_oneip_power_save_level(mx_remote.OneIPPowerSaveLevel.LOW)) is True
assert len(sent[-1]) == 24 + 176, 'a write without the block grew'
refused(msg.set_oneip_ptp_messages(S.PTP_DSCP, mx_remote.OneIPPtpMessages(dscp=64)), 'a DSCP above 63')
refused(msg.set_oneip_ptp_messages(S.PTP_DSCP | S.STATUS_LED, mx_remote.OneIPPtpMessages()),
        'a setting outside the block')
refused(msg.set_oneip_ptp_messages(S(0), mx_remote.OneIPPtpMessages()), 'nothing carried')
refused(ptp.set_oneip_ptp_messages(S.PTP_SYNC, mx_remote.OneIPPtpMessages()), 'a setting the device does not have')
print('msgs write  : 224 bytes with the block at 216, nothing out of range sent')

# The stream TTL sits at 8 of the block, which is the last of its frame and read
# by its length: 8 bytes carry everything but the TTL.
TTL = int(S.STREAM_TTL | S.PTP_SYNC)
ttl = hello(uid(0x25), SINK)
rx(uid(0x25), 0x3C, cfg_msg(uid(0x25), TTL, BLOCK + (32,) + (0xA5,) * 7))
s = ttl.oneip_settings
assert s.ptp_messages.stream_ttl == 32 and s.ptp_messages.log_sync_interval == -2, s
ttl8 = hello(uid(0x26), SINK)
rx(uid(0x26), 0x3C, cfg_msg(uid(0x26), TTL, BLOCK))
s = ttl8.oneip_settings
assert (S.STREAM_TTL not in s.valid) and (S.PTP_SYNC in s.valid), 'an 8-byte block stripped more than the TTL'
rx(uid(0x04), 0x3C, cfg_msg(uid(0x25), int(S.STREAM_TTL), bytes(16)))
assert ttl.oneip_settings.ptp_messages.stream_ttl == 32, "another sender's TTL of 0 was cached"

assert call(ttl.set_oneip_ptp_messages(S.STREAM_TTL, mx_remote.OneIPPtpMessages(stream_ttl=255))) is True
p = sent[-1][24:]
assert len(p) == 232 and p[224:232] == bytes([255] + [0] * 7), p[216:].hex()
assert ttl.oneip_settings.ptp_messages.stream_ttl == 255
assert call(ttl.set_oneip_ptp_messages(S.PTP_SYNC, mx_remote.OneIPPtpMessages())) is True
assert len(sent[-1]) == 24 + 224, 'a write without the TTL grew the block'
refused(ttl.set_oneip_ptp_messages(S.STREAM_TTL, mx_remote.OneIPPtpMessages(stream_ttl=0)), 'a TTL of 0')
refused(ttl.set_oneip_ptp_messages(S.STREAM_TTL, mx_remote.OneIPPtpMessages(stream_ttl=256)), 'a TTL past the field')
refused(ttl8.set_oneip_ptp_messages(S.STREAM_TTL, mx_remote.OneIPPtpMessages(stream_ttl=64)), 'a unit without the TTL')
print('stream ttl  : at 8 of a 16-byte block, never 0')

# The output's rotation is a u16 at 10 of the same block and its step at 12, so
# a block ending before the step strips only the rotation. A unit takes 0 or a
# multiple of its own step up to 359.
ROT = int(S.SINK_ROTATION | S.STREAM_TTL)
def rot_block(angle, step):
    return bytes(BLOCK) + bytes([32, 0xA5]) + struct.pack('<HH', angle, step) + bytes([0xA5, 0xA5])
rot = hello(uid(0x27), SINK)
rx(uid(0x27), 0x3C, cfg_msg(uid(0x27), ROT, rot_block(90, 90)))
m = rot.oneip_settings.ptp_messages
assert (m.sink_rotation, m.sink_rotation_step, m.stream_ttl) == (90, 90, 32), m
rot12 = hello(uid(0x28), SINK)
rx(uid(0x28), 0x3C, cfg_msg(uid(0x28), ROT, rot_block(90, 90)[:12]))
s = rot12.oneip_settings
assert (S.SINK_ROTATION not in s.valid) and (S.STREAM_TTL in s.valid), 'a 12-byte block stripped more than the rotation'

# Another sender's write is cached only where the unit would take it, and never
# moves the unit's step.
rx(uid(0x04), 0x3C, cfg_msg(uid(0x27), int(S.SINK_ROTATION), rot_block(45, 0)))
assert rot.oneip_settings.ptp_messages.sink_rotation == 90, "another sender's angle off the step was cached"
rx(uid(0x04), 0x3C, cfg_msg(uid(0x27), int(S.SINK_ROTATION), rot_block(180, 0)))
m = rot.oneip_settings.ptp_messages
assert (m.sink_rotation, m.sink_rotation_step) == (180, 90), m

# A write carries the angle and leaves the step 0, which the unit applies alone.
assert call(rot.set_oneip_ptp_messages(S.SINK_ROTATION, mx_remote.OneIPPtpMessages(sink_rotation=270))) is True
p = sent[-1][24:]
assert len(p) == 232 and p[224:232] == bytes([0, 0]) + struct.pack('<H', 270) + bytes(4), p[216:].hex()
m = rot.oneip_settings.ptp_messages
assert (m.sink_rotation, m.sink_rotation_step) == (270, 90), m
assert call(rot.set_oneip_ptp_messages(S.SINK_ROTATION, mx_remote.OneIPPtpMessages(sink_rotation=0))) is True
refused(rot.set_oneip_ptp_messages(S.SINK_ROTATION, mx_remote.OneIPPtpMessages(sink_rotation=45)), 'an angle off the step')
refused(rot.set_oneip_ptp_messages(S.SINK_ROTATION, mx_remote.OneIPPtpMessages(sink_rotation=360)), 'an angle past 359')
fixed = hello(uid(0x29), SINK)
rx(uid(0x29), 0x3C, cfg_msg(uid(0x29), ROT, rot_block(0, 0)))
refused(fixed.set_oneip_ptp_messages(S.SINK_ROTATION, mx_remote.OneIPPtpMessages(sink_rotation=90)), 'a unit with no step')

# A mesh-wide write can only be checked for range; each unit judges the step.
everyone = lambda angle: mx.set_all_oneip_device_settings(mx_remote.OneIPDeviceSettings(
    valid=S.SINK_ROTATION, ptp_messages=mx_remote.OneIPPtpMessages(sink_rotation=angle)))
assert call(everyone(45)) is True
assert struct.unpack_from('<H', sent[-1], len(sent[-1]) - 6)[0] == 45, sent[-1][-16:].hex()
refused(everyone(360), 'a mesh-wide angle past 359')
# as_applied_to still takes only the bits a unit reported, which say nothing of
# its step, so a rotation other than 0 is left out.
write = mx_remote.OneIPDeviceSettings(valid=S.STATUS_LED | S.SINK_ROTATION,
                                      ptp_messages=mx_remote.OneIPPtpMessages(sink_rotation=90))
assert write.as_applied_to(S.STATUS_LED | S.SINK_ROTATION).valid == S.STATUS_LED
print('rotation    : a u16 at 10, by the unit\'s own step, which a write leaves 0')

# What the builder writes, the decoder reads back as the same settings.
assert call(target.set_oneip_ir_profile(7)) is True
rx(uid(0x10), 0x3C, sent[-1][24:])
assert call(target.set_oneip_setting(S.SINK_OFF_NO_SIGNAL | S.CEC_COMBO_KEYS, True)) is True
rx(uid(0x10), 0x3C, sent[-1][24:])
s = target.oneip_settings
assert s.ir_profile == 7, s.ir_profile
assert s.ir_profile_sink == ONEIP_IR_PROFILE_NOT_SET, s.ir_profile_sink
assert s.get(S.SINK_OFF_NO_SIGNAL) is True
assert s.get(S.CEC_COMBO_KEYS) is True
assert s.get(S.FAN_QUIET) is False
assert int(s.valid) == int(S.FAN_QUIET | S.SINK_OFF_NO_SIGNAL | S.CEC_COMBO_KEYS
                           | S.IR_PROFILE | S.IR_PROFILE_SINK), 'the round trip changed what the device has'
print('round trip  :', s)

print('ALL OK')
