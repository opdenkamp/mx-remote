# Real 0x45 frames captured off a live mesh. Every unit on that mesh was
# CEC-configured, so the sender leaves status_name empty and returns - the string must be empty in all three. That is
# what makes them a usable fixture: the expected value is known from firmware
# behaviour rather than from our own decoder.
import os, sys, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.proto.Factory import create_mxr_frame, process_mxr_frame
from mx_remote.proto.Constants import RCType, RCStatus

CAPTURED = [
 "01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01  01 73 20 28  00 00 00 00  0f 00 00 00  00 00 00 00 dc 1b 00 10 00 00 00 00 df ff",
 "02 02 02 02 02 02 02 02 02 02 02 02 02 02 02 02  01 6e 1e 28  00 00 00 00  0f 6f 05 28  00 70 05 28 dc 1b 00 10 00 00 00 00 df ff",
 "03 03 03 03 03 03 03 03 03 03 03 03 03 03 03 03  01 b5 1b 28  00 00 00 00  0f 6f 05 28  00 70 05 28 dc 1b 00 10 00 00 00 00 df ff",
]
SENDER = bytes(range(200, 216))
mx = mx_remote.Remote(open_connection=False); mx._uid = bytes(range(100, 116))

for i, hx in enumerate(CAPTURED, 1):
    pl = bytes.fromhex(hx.replace(' ', ''))
    f = process_mxr_frame(mx, time.time(), create_mxr_frame(SENDER, 0x45, pl), ('192.0.2.1', 8812))
    print(f'frame {i}: {f}')

    # rc is ONE byte. A u32 read here gives 673215233 and friends, because the
    # three bytes after it are stack content the sender never cleared.
    assert f.rc_target == RCType.CEC, f.rc_target
    assert pl[17:20] != bytes(3) or i == 1, 'padding is not zero on the wire'

    # every unit here is CEC-configured, so the driver status string must be empty
    assert f.status_name is None, f'status_name must be empty, got {f.status_name!r}'

    # all four flags set, rc_status not reported
    assert (f.cec_enabled, f.cec_auto_on, f.rc_forward, f.ir_forward) == (True, True, True, True)
    assert f.rc_status == RCStatus.UNKNOWN, f.rc_status
    assert f.ip is None, f.ip

# the padding really does vary between frames - so a decoder that widens a field
# to swallow it produces a different answer per frame for a constant setting
raw = [bytes.fromhex(h.replace(' ', '')) for h in CAPTURED]
u32s = {int.from_bytes(r[16:20], 'little') for r in raw}
assert len(u32s) == 3, 'expected three different u32 reads from one constant setting'
print(f'\nwidening rc to u32 would give {sorted(u32s)} for three units all set to CEC')

# and reading the name two bytes early finds garbage a CEC unit cannot report
early = [r[26:42].split(b'\x00', 1)[0] for r in raw]
assert early[1] and early[2], 'offset 26 should read non-empty garbage here'
print(f'reading status_name at 26 instead of 28 gives {early!r}')
print()
print('ALL OK')
