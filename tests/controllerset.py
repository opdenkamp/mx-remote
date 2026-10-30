######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''What a mesh controller sets on a OneIP unit: a VLAN confirmation, the locale,
the 4:2:0 check, a power save request, the stream markings, and a video
processor upgrade of every unit.

Reserved bytes in the fixtures are poisoned, so a field read or echoed from a
neighbour's offset shows. Every refusal sits next to a write that goes out.
'''

import asyncio, os, struct, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import DeviceFeature as D, MxrDeviceUid, OneIPDscpConfig, OneIPDeviceSetting as S
from mx_remote.proto.Constants import (ONEIP_LOCALE_UNKNOWN, OneIPVlanFlag as F, MXR_ONEIP_DSCP_SET,
                                       MXR_SCALING_FLAG_OPTIONS2_VALID as OPTIONS2,
                                       MXR_SCALING_FLAG_MATCH_SOURCE as MATCH, MXR_SCALING_FLAG_SKIP_420 as SKIP,
                                       ONEIP_SOURCE_RATE_MIN, ONEIP_SOURCE_RATE_MAX)
from mx_remote.proto.Factory import create_mxr_frame
from mx_remote.remote.Remote import _for_every_unit

ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False)
mx._uid = bytes(range(0x20, 0x30))
sent = []
mx.transmit = lambda data, to=None: (sent.append(bytes(data)), len(data))[1]

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

def call(coro):
    return asyncio.run(coro)

def refused(coro, why):
    n = len(sent)
    assert call(coro) is False, why
    assert len(sent) == n, f'{why}: refused, but transmitted anyway'

def last(opcode):
    f = sent[-1]
    assert int.from_bytes(f[20:22], 'little') == opcode, f[:24].hex()
    return f[24:]

def settings_cfg(subject, ext=None, locale=0xA5, size=248, valid=S.STATUS_LED):
    '''A configuration about subject reporting the settings of valid, with the
    second valid word ext at 232, a downmix behind it and locale at 241, cut to
    size.'''
    out = bytearray(subject + bytes(24) + bytes([0xFF]) + bytes(87))
    out += struct.pack('<II', int(valid), int(valid)) + bytes(40)    # 128..176 settings
    out += bytes(16) + bytes(24) + bytes(16)                         # VLAN, PTP state, own block
    assert len(out) == 232, len(out)
    if ext is not None:
        out += struct.pack('<IBBBBBB', ext, 2, 1, 77, 9, 6, locale) + bytes([0xA5] * 6)
    return bytes(out[:size])

EXT_DOWNMIX, EXT_LOCALE = 1 << 0, 1 << 1
SINK = D.ONEIP_SINK | D.CONFIG_INITIALISED

# --------------------------------------------------------------- locale: read
dev = hello(uid(0x10), SINK)
rx(uid(0x10), 0x3C, settings_cfg(uid(0x10), EXT_LOCALE, 1, size=241))
assert dev.oneip_locale is None, 'a block too short for the locale'
rx(uid(0x10), 0x3C, settings_cfg(uid(0x10), EXT_LOCALE, 1, size=242))
assert dev.oneip_locale == 1, dev.oneip_locale
rx(uid(0x10), 0x3C, settings_cfg(uid(0x10), EXT_LOCALE, 0, size=241))
assert dev.oneip_locale == 1, 'a block too short to say changed it'
rx(uid(0x10), 0x3C, settings_cfg(uid(0x10), EXT_LOCALE, ONEIP_LOCALE_UNKNOWN))
assert dev.oneip_locale == ONEIP_LOCALE_UNKNOWN, dev.oneip_locale
rx(uid(0x10), 0x3C, settings_cfg(uid(0x10), EXT_DOWNMIX, 1))
assert dev.oneip_locale is None, 'a report without the bit kept the locale'
assert dev.oneip_downmix is not None, 'the downmix beside it was not read'
print('read        : behind its bit, from a block that holds it')

# Another sender's frame is a write, which a device without locales ignores.
ctrl = hello(uid(0x11), D.MANAGER, model='Ctrl')
rx(uid(0x10), 0x3C, settings_cfg(uid(0x10), 0, 0))
rx(uid(0x11), 0x3C, settings_cfg(uid(0x10), EXT_LOCALE, 1))
assert dev.oneip_locale is None, 'a write gave a locale to a device with none'
rx(uid(0x10), 0x3C, settings_cfg(uid(0x10), EXT_LOCALE, 0))
rx(uid(0x11), 0x3C, settings_cfg(uid(0x10), 0, 1))
assert dev.oneip_locale == 0, 'a write without the bit was applied'
rx(uid(0x11), 0x3C, settings_cfg(uid(0x10), EXT_LOCALE, 1))
assert dev.oneip_locale == 1, 'a write to a device with locales was not applied'
assert ctrl.oneip_locale is None, 'the write was taken as the controller\'s own'
print('writes      : reach only a device that has a locale')

# -------------------------------------------------------------- locale: write
# A device takes a locale before it reports its settings, so one that has not
# is written too.
reported = hello(uid(0x12), SINK)
rx(uid(0x12), 0x3C, settings_cfg(uid(0x12), EXT_LOCALE | EXT_DOWNMIX, 0))
pending = hello(uid(0x13), SINK)
for d, u in ((reported, uid(0x12)), (pending, uid(0x13))):
    sent.clear()
    assert call(d.set_oneip_locale(1)) is True, u.hex()
    p = last(0x3C)
    assert len(p) == 248, len(p)
    assert p[:16] == u and p[40] == 0xFF, p[:41].hex()
    assert p[128:132] == bytes(4), 'a setting of the first valid word'
    assert p[232:] == bytes([2, 0, 0, 0, 0, 0, 0, 0, 0, 1]) + bytes(6), p[232:].hex()
    assert d.oneip_locale == 1, d.oneip_locale
print('write       : the locale alone, cached once sent')

lacks = hello(uid(0x14), SINK)
rx(uid(0x14), 0x3C, settings_cfg(uid(0x14), 0, 0))
assert lacks.oneip_settings is not None and lacks.oneip_locale is None
refused(lacks.set_oneip_locale(0), 'a device whose firmware has no locales')
refused(reported.set_oneip_locale(ONEIP_LOCALE_UNKNOWN), 'the unknown locale')
refused(reported.set_oneip_locale(-1), 'a negative locale')
refused(reported.set_oneip_locale(0x100), 'a locale wider than a byte')
assert call(reported.set_oneip_locale(0)) is True, 'locale 0 is a locale'
print('refusals    : nothing a unit would ignore is sent')

# ----------------------------------------------------------------- skip 4:2:0
def scaling_cfg(subject, flags):
    '''A sink's own configuration with no mode and the scaling flags at 60.'''
    return subject + bytes(24) + bytes([0xFF]) + bytes(15) + struct.pack('<HHB', 0, 0, flags) \
        + bytes([0xA5] * 3) + bytes(24)

matching = hello(uid(0x20), SINK, protocol=0x2F)
rx(uid(0x20), 0x3C, scaling_cfg(uid(0x20), OPTIONS2 | MATCH), protocol=0x2F)
plain = hello(uid(0x21), SINK, protocol=0x2F)
rx(uid(0x21), 0x3C, scaling_cfg(uid(0x21), OPTIONS2 | SKIP), protocol=0x2F)
assert matching.oneip_details.scaling.match_source is True, 'the fixture reports match-source'
for d, u, skip, written in ((matching, uid(0x20), True, OPTIONS2 | SKIP | MATCH),
                            (plain, uid(0x21), False, OPTIONS2)):
    sent.clear()
    assert call(d.set_oneip_skip_420(skip)) is True, u.hex()
    p = last(0x3C)
    assert len(p) == 88, len(p)
    assert p[60] == written, f'{u.hex()}: {p[60]:#x}'
    assert p[56:58] == bytes(2), 'a mode'
    scaling = d.oneip_details.scaling
    assert (scaling.skip_420, scaling.match_source) == (skip, d is matching), \
        (scaling.skip_420, scaling.match_source)
fresh = hello(uid(0x22), SINK, protocol=0x2F)
assert call(fresh.set_oneip_skip_420(True)) is True
assert last(0x3C)[60] == OPTIONS2 | SKIP, 'match-source was turned on for a sink that never reported it'
old = hello(uid(0x23), SINK, protocol=0x2E)
refused(old.set_oneip_skip_420(True), 'a sink below 0x2F')
print('skip 4:2:0  : match-source restated as the sink reported it')

# ------------------------------------------------------------------- markings
marking = OneIPDscpConfig(video=46, audio=34, anc=26)
source = hello(uid(0x30), D.ONEIP_SOURCE, protocol=0x2F)
sent.clear()
assert call(source.set_oneip_dscp(marking)) is True
p = last(0x3C)
assert len(p) == 88, len(p)
assert p[:16] == uid(0x30)
assert p[16:40] == bytes(24), 'a source address would repoint the encoder'
assert p[40] == 0xFF and not (ONEIP_SOURCE_RATE_MIN <= p[40] <= ONEIP_SOURCE_RATE_MAX), \
    f'rate {p[40]:#x}: 0 asks for a rate of zero, and one in range replaces the encoder\'s'
assert p[41:44] == bytes([MXR_ONEIP_DSCP_SET | 46, MXR_ONEIP_DSCP_SET | 34, MXR_ONEIP_DSCP_SET | 26]), p[41:44].hex()
assert p[44:] == bytes(44), 'a scaling or tiling write'
assert source.oneip_details.dscp == marking, 'the cache did not take the marking once sent'
refused(source.set_oneip_dscp(OneIPDscpConfig(video=64, audio=34, anc=26)), 'a DSCP above 63')
refused(source.set_oneip_dscp(OneIPDscpConfig(video=46, audio=34, anc=None)), 'a marking leaving a stream out')
refused(matching.set_oneip_dscp(marking), 'a device that announces no source')
print('markings    : all three behind their set bits, and nothing else')

# ------------------------------------------------------------- VLAN confirm
def vlan_cfg(subject, flags, device, port, uplink, active, revert):
    '''A configuration with a settings block carrying nothing, then the VLAN
    block, its reserved bytes poisoned.'''
    return (subject + bytes(24) + bytes([0xFF, 0, 0, 0]) + bytes(4) + bytes(80)
            + bytes(48) + struct.pack('<HH3HBBB', int(flags), device, *port, uplink, active, revert)
            + bytes([0xA5] * 3))

VLAN_SINK = D.ONEIP_SINK | D.VLAN
trunked = hello(uid(0x40), VLAN_SINK)
rx(uid(0x40), 0x3C, vlan_cfg(uid(0x40), F.VALID | F.TRUNK | F.PENDING | F.HAS_SFP,
                             0x0123, (0x0456, 0x0789, 0x0ABC), 2, 3, 41))
assert trunked.oneip_vlan is not None and trunked.oneip_vlan.is_pending
sent.clear()
assert call(trunked.confirm_oneip_vlan()) is True
p = last(0x3C)
assert len(p) == 192, len(p)
assert p[:16] == uid(0x40)
assert p[176:] == bytes([0x0B, 0x00, 0x23, 0x01, 0x56, 0x04, 0x89, 0x07, 0xBC, 0x0A, 2, 0, 0, 0, 0, 0]), p[176:].hex()
untrunked = hello(uid(0x41), VLAN_SINK)
rx(uid(0x41), 0x3C, vlan_cfg(uid(0x41), F.VALID | F.PENDING, 7, (0, 0, 0), 0, 1, 50))
assert call(untrunked.confirm_oneip_vlan()) is True
assert last(0x3C)[176:178] == bytes([0x09, 0x00]), 'a trunk the device does not run was confirmed'

settled = hello(uid(0x42), VLAN_SINK)
rx(uid(0x42), 0x3C, vlan_cfg(uid(0x42), F.VALID, 5, (0, 0, 0), 0, 1, 0))
assert settled.oneip_vlan is not None
refused(settled.confirm_oneip_vlan(), 'a configuration with no change pending')
unreported = hello(uid(0x43), VLAN_SINK)
refused(unreported.confirm_oneip_vlan(), 'a device that reported no VLAN configuration')
without = hello(uid(0x44), D.ONEIP_SINK)
rx(uid(0x44), 0x3C, vlan_cfg(uid(0x44), F.VALID | F.PENDING, 7, (0, 0, 0), 0, 1, 50))
assert without.oneip_vlan is not None and without.oneip_vlan.is_pending
refused(without.confirm_oneip_vlan(), 'a device that does not announce VLANs')
print('vlan        : the pending configuration echoed with CONFIRM')

# ----------------------------------------------------------------- power save
# A unit tells the two forms apart by their exact length.
unit = hello(uid(0x50), SINK)
for suspend, flag in ((True, 1), (False, 0)):
    sent.clear()
    assert call(unit.request_oneip_power_save(suspend)) is True
    p = last(0x41)
    assert p == uid(0x50) + bytes([flag]), f'one unit, suspend={suspend}: {p.hex()}'
    assert call(mx.request_all_oneip_power_save(suspend)) is True
    p = last(0x41)
    assert p == bytes([flag]), f'every unit, suspend={suspend}: {p.hex()}'
assert not _for_every_unit(0x41, bytes([1])), 'a power save request is not one every unit sends to both'
print('power save  : 17 bytes name the unit, the flag alone reaches every one')

# ------------------------------------------------------------------- upgrade
sent.clear()
assert call(mx.upgrade_all_video_processors()) is True
f = sent[-1]
assert int.from_bytes(f[20:22], 'little') == 0x2C, f[:24].hex()
assert f[2] == 0x06, f'stamped {f[2]:#x}'
assert len(f) == 24, 'a payload'
assert _for_every_unit(0x2C, b''), 'not sent to both endpoints'
print('upgrade     : 0x2C, empty, to every unit')

print('ALL OK')
