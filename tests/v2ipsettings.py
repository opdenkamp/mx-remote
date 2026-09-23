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
from mx_remote import DeviceFeature, MxrDeviceUid, V2IPDeviceSetting as S
from mx_remote.proto.Constants import (V2IPFpgaFeature, V2IP_IR_PROFILE_MAX,
                                       V2IP_IR_PROFILE_NOT_SET)
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

SINK = int(DeviceFeature.V2IP_SINK) | int(DeviceFeature.VIDEO_ROUTING)
ALL = 0x7FF
FPGA = int(V2IPFpgaFeature.SOURCE_DSCP | V2IPFpgaFeature.SINK_STATE)

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

# ------------------------------------------------------------------- reading

# Every field carries a distinct value, so one read at a neighbour's offset
# shows, and the reserved bytes behind them are poisoned.
dev = hello(uid(0x01), SINK)
ON = int(S.SINK_CHECK_POWER | S.STATUS_LED | S.CEC_COMBO_INPUT)
rx(uid(0x01), 0x3C, cfg(uid(0x01), ALL, ON, profiles=0b101, profile=3, profile_sink=-1, fpga=FPGA))
s = dev.v2ip_settings
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
assert int(dev.v2ip_features) == FPGA, 'the block moved the processor word'
print('decode      :', s)

# The settings were appended, so a sender that predates them stops short, and
# one byte short of the block is not the block.
older = hello(uid(0x02), SINK)
rx(uid(0x02), 0x3C, cfg(uid(0x02), ALL)[:143])
assert older.v2ip_details is not None, 'the frame was dropped'
assert older.v2ip_settings is None, 'a block one byte short was read'
rx(uid(0x02), 0x3C, cfg(uid(0x02), ALL))
assert older.v2ip_settings is not None, 'the whole block was not read'
print('length      : 143 bytes carries none, 144 carries the block')

# A frame carrying some settings leaves the others as they were.
rx(uid(0x01), 0x3C, cfg(uid(0x01), int(S.STATUS_LED | S.IR_PROFILE), 0, profile=2))
s = dev.v2ip_settings
assert s.get(S.STATUS_LED) is False
assert s.get(S.SINK_CHECK_POWER) is True, 'a setting the frame did not carry was changed'
assert s.ir_profile == 2, s.ir_profile
assert s.ir_profile_sink == -1, 'a profile the frame did not carry was changed'
assert s.stored_ir_profiles == 0b101, 'the stored profiles the frame did not carry were changed'
assert int(s.valid) == ALL, hex(s.valid)
print('partial     : one setting moved, the rest kept')

# ------------------------------------------------- a controller's write, read
# The device applies a setting only if it has it and a profile only within its
# range, and the list of stored profiles is its own. Caching more would report a
# change the device never made.
HAS = int(S.FAN_QUIET | S.IR_PROFILE | S.IR_PROFILE_SINK | S.IR_PROFILES)
subject = hello(uid(0x03), SINK)
ctrl = hello(uid(0x04), int(DeviceFeature.MANAGER), model='Ctrl')
rx(uid(0x03), 0x3C, cfg(uid(0x03), HAS, 0, profiles=0b11, profile=1, profile_sink=1))

rx(uid(0x04), 0x3C, cfg(uid(0x03), int(S.FAN_QUIET | S.STATUS_LED | S.IR_PROFILE | S.IR_PROFILES),
                        int(S.FAN_QUIET | S.STATUS_LED), profiles=0xFFFF, profile=V2IP_IR_PROFILE_MAX))
s = subject.v2ip_settings
assert s.get(S.FAN_QUIET) is True, 'the write itself did not land'
assert s.ir_profile == 1, 'an out-of-range profile was cached'
assert s.get(S.STATUS_LED) is None, 'a setting the device does not have was cached'
assert s.stored_ir_profiles == 0b11, 'a third party rewrote the profiles only the device knows'
assert ctrl.v2ip_settings is None, 'the settings landed on the sender instead'

# The output port follows the global one at NOT_SET, which is in range there.
for profile, taken in ((V2IP_IR_PROFILE_NOT_SET, True), (V2IP_IR_PROFILE_NOT_SET - 1, False),
                       (V2IP_IR_PROFILE_MAX - 1, True), (V2IP_IR_PROFILE_MAX, False)):
    rx(uid(0x03), 0x3C, cfg(uid(0x03), HAS, 0, profiles=0b11, profile=1, profile_sink=5))
    rx(uid(0x04), 0x3C, cfg(uid(0x03), int(S.IR_PROFILE_SINK), profile_sink=profile))
    got = subject.v2ip_settings.ir_profile_sink
    assert got == (profile if taken else 5), f'a write of {profile} to the output port read back {got}'

# A device that has reported no settings has none a write could land on, so
# the write leaves nothing behind - not even an empty record, which would read
# as a device that has reported.
silent = hello(uid(0x05), SINK)
rx(uid(0x04), 0x3C, cfg(uid(0x05), int(S.FAN_QUIET), int(S.FAN_QUIET)))
assert silent.v2ip_details is not None, 'the write itself was dropped'
assert silent.v2ip_settings is None, 'a write about a silent device invented its settings'
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
refused(target.set_v2ip_setting(S.FAN_QUIET, True), 'a device that has reported no settings')
rx(uid(0x10), 0x3C, cfg(uid(0x10), int(S.FAN_QUIET | S.SINK_OFF_NO_SIGNAL | S.CEC_COMBO_KEYS
                                       | S.IR_PROFILE | S.IR_PROFILE_SINK), 0))

# The success case first, which gives every refusal below its meaning. The
# bytes ahead of the block are the assertion: a source address repoints the
# encoder, a rate in range replaces the device's, a scaling validity bit
# rewrites its scaling.
assert call(target.set_v2ip_setting(S.FAN_QUIET, True)) is True
p = sent[-1][24:]
assert len(p) == 144, 'the payload stops short of the settings'
assert p[0:16] == uid(0x10), 'the frame names another device'
assert p[16:40] == bytes(24), 'a source address would repoint the encoder'
assert p[40] == 0xFF, 'the rate is inside the valid range, so it would replace the device\'s'
assert p[41:128] == bytes(87), 'a field between the rate and the settings block is set'
assert struct.unpack('<IIIbb', p[128:142]) == (int(S.FAN_QUIET), int(S.FAN_QUIET), 0, 0, 0), \
    struct.unpack('<IIIbb', p[128:142])
assert target.v2ip_settings.get(S.FAN_QUIET) is True, \
    'reading back before the device reports shows the old value'
assert call(target.set_v2ip_setting(S.FAN_QUIET, False)) is True
assert struct.unpack('<II', sent[-1][24 + 128:24 + 136]) == (int(S.FAN_QUIET), 0)
assert target.v2ip_settings.get(S.FAN_QUIET) is False
print('write       :', len(p), 'bytes, nothing but the settings block')

refused(target.set_v2ip_setting(S.STATUS_LED, True), 'a setting the device does not have')
for setting in (S(0), S.IR_PROFILE, S.IR_PROFILES, S.FAN_QUIET | S.IR_PROFILE):
    refused(target.set_v2ip_setting(setting, True), f'{setting!r} is not a set of on/off settings')
for profile in (-1, V2IP_IR_PROFILE_MAX):
    refused(target.set_v2ip_ir_profile(profile), f'global profile {profile}')
for profile in (-2, V2IP_IR_PROFILE_MAX):
    refused(target.set_v2ip_sink_ir_profile(profile), f'output profile {profile}')
assert call(target.set_v2ip_ir_profile(V2IP_IR_PROFILE_MAX - 1)) is True
assert call(target.set_v2ip_sink_ir_profile(V2IP_IR_PROFILE_NOT_SET)) is True
nosink = hello(uid(0x11), SINK)
rx(uid(0x11), 0x3C, cfg(uid(0x11), int(S.IR_PROFILE), 0))
refused(nosink.set_v2ip_sink_ir_profile(0), 'a port the device does not have')
print('refusals    : nothing a device ignores is sent')

# A write the socket dropped reports failure and leaves the cache alone.
before = target.v2ip_settings
wire(False)
assert call(target.set_v2ip_setting(S.FAN_QUIET, True)) is False, 'a failed send reported success'
assert target.v2ip_settings == before, 'a failed send moved the cache'
wire(True)
print('send failed : False, cache unmoved')

# What the builder writes, the decoder reads back as the same settings.
assert call(target.set_v2ip_ir_profile(7)) is True
rx(uid(0x10), 0x3C, sent[-1][24:])
assert call(target.set_v2ip_setting(S.SINK_OFF_NO_SIGNAL | S.CEC_COMBO_KEYS, True)) is True
rx(uid(0x10), 0x3C, sent[-1][24:])
s = target.v2ip_settings
assert s.ir_profile == 7, s.ir_profile
assert s.ir_profile_sink == V2IP_IR_PROFILE_NOT_SET, s.ir_profile_sink
assert s.get(S.SINK_OFF_NO_SIGNAL) is True
assert s.get(S.CEC_COMBO_KEYS) is True
assert s.get(S.FAN_QUIET) is False
assert int(s.valid) == int(S.FAN_QUIET | S.SINK_OFF_NO_SIGNAL | S.CEC_COMBO_KEYS
                           | S.IR_PROFILE | S.IR_PROFILE_SINK), 'the round trip changed what the device has'
print('round trip  :', s)

print('ALL OK')
