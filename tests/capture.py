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

# --- 0x08 mxr_routing_change, off the wire from 10.8.83.254 on 10.12.32-6, a
# local sink switched to source 8 through the unit's own HTTP API. The expected
# values are the firmware's own report of what it sent rather than this decoder's
# reading of it, which is what makes it a fixture instead of a restatement.
#
# The same switch also produced an all-zero frame, 10 00 00 00 00 00 00 00 00.
# It is not here: every field reads 0 under the old layout too, so a test built
# on it passes whatever the offsets say.
ROUTE = bytes.fromhex('100008000800000800')
assert len(ROUTE) == 9, 'sizeof(mxr_routing_change)'

# The bays have to exist before the frame can name them, so announce the sender
# and give it the two ports this frame refers to: 8 as an input, 16 as an output.
def _nm(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))
def _bay(port, mode, num, name):
    return bytes([port, mode, num, 0, 0]) + _nm(name) + _nm(name) + b'1080p60' + bytes(7) \
         + bytes(2) + bytes(4) + ((1 << 1) if mode == 0 else (1 << 0)).to_bytes(4, 'little')
mx.process_frame(time.time(), create_mxr_frame(
    SENDER, 0x00, (0x28).to_bytes(2, 'little') + _nm('V2IP') + _nm('P8SN00000001')
    + _nm('10.12.32-6') + ((1 << 5) | (1 << 17)).to_bytes(4, 'little')), ('192.0.2.1', 8812))
mx.process_frame(time.time(), create_mxr_frame(
    SENDER, 0x02, _bay(6, 0, 6, 'In 6') + _bay(8, 0, 8, 'In 8')
    + _bay(16, 1, 16, 'Out 16')), ('192.0.2.1', 8812))

# The second frame is a split route - video from 6, audio from 8 - which is the
# only one of the two where audio can be read from the wrong offset and noticed.
ROUTE_SPLIT = bytes.fromhex('100006000600000800')
print()
for label, raw, expect in [('straight', ROUTE, (16, 8, 8, False, 8)),
                           ('split   ', ROUTE_SPLIT, (16, 6, 6, False, 8))]:
    assert len(raw) == 9, 'sizeof(mxr_routing_change)'
    rf = process_mxr_frame(mx, time.time(), create_mxr_frame(SENDER, 0x08, raw), ('192.0.2.1', 8812))
    # read through the frame's own accessors: a fixture that reads the payload
    # directly tests payload_u16 and would survive any change to these offsets
    decoded = (rf.sink_bay.port, rf.selected_bay.port, rf.video_bay.port,
               rf.scrambled, rf.audio_bay.port)
    assert decoded == expect, (label, decoded, expect)
    print(f'0x08 {label}  : sink/selected/video/scrambled/audio = {decoded}')

# What the pair settles, and what it does not.
#
# Between them they pin where selected and audio are read. Video, scrambled and
# sink survive being moved: selected equals video in both captures, so video
# reads the same at 2 or 4; scrambled is 0 at both 3 and 6; sink is 16 at either
# width. Nor is any width pinned - every bay here is under 256, so a u8 read of
# audio at 7 gives the same 8. Those rest on the synthetic frame in structs.py,
# which picks a different value per field but can only confirm this decoder
# against itself.
#
# Separating video from selected needs a source whose selected input resolves to
# a different video bay - a mirrored or linked input rather than an ordinary
# switch - and scrambled needs an HDCP-protected source at switch time. Neither
# is worth reconfiguring live hardware for.
#
# The split frame is also the only one that pins behaviour rather than layout.
# process() feeds video and audio to SelectedBays and never reads selected_bay,
# so on the straight frame the u8 layout routes identically and only a field
# nothing consumes differs. On the split frame it routes audio to 6 instead of 8.
for raw, field, want in [(ROUTE, 1, 'selected'), (ROUTE_SPLIT, 4, 'audio')]:
    pre_fix = (raw[0], raw[1], raw[2], bool(raw[3]), raw[4])
    cur = (raw[0], int.from_bytes(raw[2:4], 'little'), int.from_bytes(raw[4:6], 'little'),
           bool(raw[6]), int.from_bytes(raw[7:9], 'little'))
    assert pre_fix[field] != cur[field], f'this fixture no longer pins {want}'
    print(f'the u8 layout   : would read {pre_fix} - {want} differs')

print()
print('ALL OK')
