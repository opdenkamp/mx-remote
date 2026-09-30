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
