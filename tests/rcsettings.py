import os, sys, struct, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.Uid import MxrDeviceUid
from mx_remote.proto.Factory import create_mxr_frame, process_mxr_frame
from mx_remote.proto.Constants import RCStatus, RCType

UID = bytes(range(1, 17)); ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False); mx._uid = bytes(range(100, 116))

def poison(n, seed=0):
    '''Padding bytes that are not zero.

    A zero-filled fixture cannot catch a field read at the right offset with the
    wrong width: the padding beside the field is zero, so the widened read
    returns the same answer and every assertion still passes. That is how
    rc_target survived as a u32 read here for as long as it did, and it is the
    default anyone reaches for - bytes(n) - so it is the default that is wrong
    for any struct with padding in it. Fill padding with something recognisable
    instead, so straying past a field's width produces a wrong value.
    '''
    return bytes((0xA5 ^ (seed + i)) & 0xFF for i in range(n))

def rc(rc_target=2, ip='192.0.2.40', flags=0b1101, status=3, name='Sky'):
    ipb = bytes(int(x) for x in ip.split('.')) if ip else bytes(4)
    nb = name.encode('ascii')[:16]; nb = nb + bytes(16 - len(nb))
    p = (UID
         + bytes([rc_target]) + poison(3, 1)     # 16..20  ONE byte + 3 padding
         + ipb                                   # 20..24  network order
         + bytes([flags | (status << 4)])        # 24..25
         + poison(3, 8)                          # 25..28  dead byte + reserved
         + nb                                    # 28..44
         + poison(4, 20))                        # 44..48  tail padding
    assert len(p) == 48, len(p)
    return p

f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x45, rc()), ADDR)
print('0x45 :', f)
assert f.target_uid == MxrDeviceUid(UID)
assert f.rc_target == RCType.SKY_UK, f.rc_target
assert f.ip == '192.0.2.40', f.ip
assert f.rc_status == RCStatus.CONNECTED, f.rc_status
assert f.status_name == 'Sky', repr(f.status_name)
assert (f.cec_enabled, f.cec_auto_on, f.rc_forward, f.ir_forward) == (True, False, True, True)

# a full-length 15-char name still carries its NUL inside the 16-byte field
f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x45, rc(name='ABCDEFGHIJKLMNO')), ADDR)
assert f.status_name == 'ABCDEFGHIJKLMNO', repr(f.status_name)

# an unset ip reads as None, not 0.0.0.0
f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x45, rc(ip=None, name='')), ADDR)
assert f.ip is None and f.status_name is None
print('0x45 : unset ip and empty name both None')

# status 0 is "not reported", not a state
f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x45, rc(status=0)), ADDR)
assert f.rc_status == RCStatus.UNKNOWN

# an unknown future status comes back raw, not clamped
f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x45, rc(status=9)), ADDR)
assert f.rc_status == 9 and not isinstance(f.rc_status, RCStatus), f.rc_status
print('0x45 : unknown status', f.rc_status, 'passed through, not clamped')

# an unknown rc_target does not raise
f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x45, rc(rc_target=8)), ADDR)
assert f.rc_target is None
print('0x45 : RC_TARGET_INTERNAL decoded as unknown, not an error')

# reading the block as one LE u16 and shifting would give a different answer,
# which is the trap MCU warned about - assert we do not
f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x45, rc(status=3, flags=0)), ADDR)
assert f.rc_status == RCStatus.CONNECTED
# byte 25 is poisoned, so a u16-and-shift decoder reads a different value here.
# With a zero-filled fixture both approaches agree and this proves nothing.
assert f.payload_u16(24) != 0x0030, 'poison must make the wide read differ'
assert (f.payload_u16(24) & 0xFF) == 0x30
print()
print('ALL OK')
