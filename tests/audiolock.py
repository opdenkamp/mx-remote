######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''An audio endpoint's status word, and locking its audio source (0x43 sub 6).

The tree is composed from the module's declaration: endpoint 0 an output,
endpoint 1 a V2IP input that can lock its source. Each entry's status word
follows its features and every other byte is poisoned, so a status read at the
features' offset, or features read at the status', shows.

The lock is asserted in both directions: every refusal sits next to a lock that
goes out, to an endpoint that reports it can lock.
'''

import asyncio, os, struct, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import AudioFeatures, DeviceFeature, MxrDeviceUid
from mx_remote.proto.Factory import create_mxr_frame, process_mxr_frame

ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False)
mx._uid = bytes(range(0x20, 0x30))

# The module's MXR_AUDIO_FEATURE_AUDIO_LOCK, written out so a wrong constant in
# the library cannot agree with itself here.
LOCK = 1 << 15

def uid(n):
    return bytes([n]) * 16

def name(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def rx(sender, opcode, payload=b'', protocol=0x2B):
    frame = bytearray(create_mxr_frame(sender, opcode, payload))
    frame[2] = protocol
    mx.process_frame(0.0, bytes(frame), ADDR)

def hello(n):
    rx(uid(n), 0x00, struct.pack('<H', 0x2B) + name('ONEIP') + name('P8SN12345678')
                   + name('5.0.0') + struct.pack('<I', int(DeviceFeature.ONEIP_SINK)))
    return mx.get_by_uid(MxrDeviceUid(uid(n)))

def lockable_tree(status0, status1):
    p = bytearray([0xA5] * 68)
    p[0:2] = struct.pack('<H', 0)              # the FEATURES sub-opcode
    p[28:30] = struct.pack('<H', 2)            # entries
    p[36], p[37] = 0, 1                        # endpoint 0
    p[44:48] = struct.pack('<I', AudioFeatures.FEATURE_OUTPUT)
    p[48:52] = struct.pack('<I', status0)
    p[52], p[53] = 1, 1                        # endpoint 1
    p[60:64] = struct.pack('<I', AudioFeatures.FEATURE_INPUT | AudioFeatures.FEATURE_ONEIP_RX | LOCK)
    p[64:68] = struct.pack('<I', status1)
    return bytes(p)

# ------------------------------------------------------------------- reading

dev = hello(0x10)
calls = []
dev.register_callback(lambda d: calls.append(d))
muted = AudioFeatures.FEATURE_MUTE
rx(uid(0x10), 0x43, lockable_tree(muted, 0))
ep0, ep1 = dev.audio_endpoint_by_id(0), dev.audio_endpoint_by_id(1)
assert ep0.status == AudioFeatures(muted), ep0.status
assert ep1.status == AudioFeatures(0), ep1.status
assert ep1.features.support_audio_lock and not ep0.features.support_audio_lock
assert ep1.audio_locked is False
assert len(calls) == 1, f'{len(calls)} callbacks for a new tree'
rx(uid(0x10), 0x43, lockable_tree(muted, 0))
assert len(calls) == 1, 'an unchanged report was reported as a change'
rx(uid(0x10), 0x43, lockable_tree(muted, LOCK))
assert len(calls) == 2, 'locking the source was not reported'
assert dev.audio_endpoint_by_id(1).audio_locked is True
print('status      : read behind the features; a changed status is a change')

# A lock another controller sends is decoded, and caches nothing: the device
# answers it by re-sending its tree.
body = struct.pack('<H', 6) + bytes(2) + uid(0x10) + struct.pack('<HHI', 5, 0, 1)
f = process_mxr_frame(mx, 0.0, create_mxr_frame(uid(0x11), 0x43, body), ADDR)
assert (f._frame.param.endpoint, f._frame.param.locked) == (5, True), str(f)
rx(uid(0x10), 0x43, body)
print('lock read   :', f._frame.param)

# --------------------------------------------------------------------- writing

sent = []
mx.transmit = lambda data: (sent.append(data), len(data))[1]

def call(coro):
    return asyncio.new_event_loop().run_until_complete(coro)

def refused(coro, why):
    n = len(sent)
    assert call(coro) is False, why
    assert len(sent) == n, f'{why}: refused, but transmitted anyway'

unreported = hello(0x12)
refused(dev.set_audio_endpoint_locked(0, True), 'an endpoint that cannot lock')
refused(dev.set_audio_endpoint_locked(7, True), 'an endpoint the device did not report')
refused(unreported.set_audio_endpoint_locked(1, True), 'a device that reported no endpoints')

assert call(dev.set_audio_endpoint_locked(1, True)) is True
p = sent[-1][24:]
assert int.from_bytes(sent[-1][20:22], 'little') == 0x43
assert len(p) == 28, len(p)
assert p[:2] == bytes([6, 0]), 'the LOCK sub-opcode'
assert p[4:20] == uid(0x10)
assert p[20:28] == bytes([1, 0, 0, 0, 1, 0, 0, 0]), p[20:28].hex()
assert call(dev.set_audio_endpoint_locked(1, False)) is True
assert sent[-1][24 + 24:] == bytes(4), 'unlock'
print('lock write  : sub-opcode 6, only to an endpoint that can lock')

print('ALL OK')
