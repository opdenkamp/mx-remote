######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''How a OneIP output mixes down to stereo: the end of the 0x3C settings block,
behind a second valid word at 232, read and written.

Every field is distinct and the reserved bytes behind them are poisoned, so a
field read at a neighbour's offset shows. Every refusal sits next to a write
that goes out.
'''

import asyncio, os, struct, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import DeviceFeature, MxrDeviceUid, OneIPDownmix, OneIPDeviceSetting as S
from mx_remote.proto.Constants import ONEIP_DOWNMIX_LFE_MAX, OneIPDownmixLevel as L, OneIPDownmixMode as M
from mx_remote.proto.Factory import create_mxr_frame

ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False)
mx._uid = bytes(range(0x20, 0x30))
sent = []
mx.transmit = lambda data: (sent.append(bytes(data)), len(data))[1]

def uid(n):
    return bytes([n]) * 16

def name(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def rx(sender, opcode, payload=b'', protocol=0x30):
    frame = bytearray(create_mxr_frame(sender, opcode, payload))
    frame[2] = protocol
    mx.process_frame(0.0, bytes(frame), ADDR)

def hello(sender, features=DeviceFeature.ONEIP_SINK):
    rx(sender, 0x00, struct.pack('<H', 0x30) + name('ONEIP') + name('P8SN%08d' % sender[0]) + name('5.0.0')
                   + struct.pack('<I', int(features)), protocol=0x01)
    return mx.get_by_uid(MxrDeviceUid(sender))

def cfg(subject, ext=None, mode=2, level=1, lfe=77, state=9, channels=6, size=248, valid=S.STATUS_LED):
    '''A configuration about subject reporting the settings of valid, cut to
    size, with the downmix behind ext at 232 when ext is given.'''
    out = bytearray(subject + bytes(24) + bytes([0xFF]) + bytes(87))
    out += struct.pack('<II', int(valid), int(valid)) + bytes(40)    # 128..176 settings
    out += bytes(16) + bytes(24) + bytes(16)                                       # VLAN, PTP state, own block
    assert len(out) == 232, len(out)
    if ext is not None:
        out += struct.pack('<IBBBBB', ext, mode, level, lfe, state, channels) + bytes([0xA5] * 7)
    return bytes(out[:size])

def call(coro):
    return asyncio.run(coro)

# ------------------------------------------------------------------- reading
out = hello(uid(0x10))
rx(uid(0x10), 0x3C, cfg(uid(0x10), ext=0))
assert out.oneip_settings is not None and out.oneip_downmix is None, 'a downmix without its bit'
rx(uid(0x10), 0x3C, cfg(uid(0x10), ext=1))
dm = OneIPDownmix(mode=M.ALWAYS, level=L.UNSCALED, lfe=77, state=9, channels=6)
assert out.oneip_downmix == dm, out.oneip_downmix
assert isinstance(out.oneip_downmix.mode, M) and isinstance(out.oneip_downmix.level, L)
print('decode      :', out.oneip_downmix)

# A frame too short to hold the channels carries no bit of the word, so it says
# nothing about the downmix; a report without the bit says there is none.
for size in (232, 240):
    rx(uid(0x10), 0x3C, cfg(uid(0x10), ext=1, mode=0, size=size))
    assert out.oneip_downmix == dm, f'a frame of {size} bytes changed the downmix'
rx(uid(0x10), 0x3C, cfg(uid(0x10), ext=0))
assert out.oneip_downmix is None, 'a report without the bit kept the downmix'
rx(uid(0x10), 0x3C, cfg(uid(0x10), ext=1, mode=7))
assert out.oneip_downmix.mode == 7, 'a mode this library does not name was not kept raw'
print('length      : only a frame that holds it says whether there is one')

# Another sender's frame is a write: it changes the mode, level and LFE of a
# device that reports a downmix, and nothing else.
rx(uid(0x10), 0x3C, cfg(uid(0x10), ext=1))
hello(uid(0x11), DeviceFeature.MANAGER)       # a unit takes a write from a manager
rx(uid(0x11), 0x3C, cfg(uid(0x10), ext=1, mode=1, level=0, lfe=33, state=4, channels=8))
assert out.oneip_downmix == OneIPDownmix(mode=M.AUTO, level=L.NORMALISED, lfe=33, state=9, channels=6), out.oneip_downmix
rx(uid(0x11), 0x3C, cfg(uid(0x10), ext=0, mode=0))
assert out.oneip_downmix.mode == M.AUTO, 'a write without the bit was applied'
none = hello(uid(0x12))
rx(uid(0x12), 0x3C, cfg(uid(0x12), ext=0))
rx(uid(0x11), 0x3C, cfg(uid(0x12), ext=1))
assert none.oneip_downmix is None, 'a write gave a downmix to a device with none'
print('writes      : applied as the device applies them')

# ------------------------------------------------------------------- writing
rx(uid(0x10), 0x3C, cfg(uid(0x10), ext=1))
sent.clear()
assert call(out.set_oneip_downmix(OneIPDownmix(mode=M.AUTO, level=L.NORMALISED, lfe=ONEIP_DOWNMIX_LFE_MAX,
                                               state=0xEE, channels=0xEE))) is True
f = sent[-1]
assert int.from_bytes(f[20:22], 'little') == 0x3C, f[:24].hex()
p = f[24:]
assert len(p) == 248, len(p)
assert p[:16] == uid(0x10) and p[40] == 0xFF and p[128:132] == bytes(4), p[:132].hex()
assert p[232:] == struct.pack('<IBBB', 1, 1, 0, 100) + bytes(9), p[232:].hex()
assert out.oneip_downmix == OneIPDownmix(mode=M.AUTO, level=L.NORMALISED, lfe=100, state=9, channels=6), \
    out.oneip_downmix
print('write       : mode, level and LFE behind the bit, the cache keeping the state')

def refused(coro, why):
    n = len(sent)
    assert call(coro) is False, why
    assert len(sent) == n, f'{why}: refused, but transmitted anyway'
refused(out.set_oneip_downmix(OneIPDownmix(mode=3)), 'a mode past ALWAYS')
refused(out.set_oneip_downmix(OneIPDownmix(level=2)), 'a level past UNSCALED')
refused(out.set_oneip_downmix(OneIPDownmix(lfe=ONEIP_DOWNMIX_LFE_MAX + 1)), 'an LFE above 100')
refused(none.set_oneip_downmix(OneIPDownmix()), 'a device that reports no downmix')
bare = hello(uid(0x13))
rx(uid(0x13), 0x3C, cfg(uid(0x13), ext=1, valid=0))
assert bare.oneip_downmix is not None and bare.oneip_settings is None
refused(bare.set_oneip_downmix(OneIPDownmix()), 'a device that reported no settings')
print('refusals    : nothing a unit would ignore is sent')

print('ALL OK')
