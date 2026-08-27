import os, sys, struct, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.Uid import MxrDeviceUid
from mx_remote.proto.Factory import create_mxr_frame, process_mxr_frame

SINK = bytes(range(1, 17))          # the device whose endpoint changes source
SRC  = bytes(range(50, 66))         # the device supplying audio
ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False); mx._uid = bytes(range(100, 116))

# --- 0x43 SELECT_INPUT: builder writes sink at 4 AND 20, source at 36
payload = struct.pack('<H', 3) + bytes(2) + SINK + SINK + SRC + struct.pack('<HH', 7, 9)
assert len(payload) == 56, len(payload)
f = process_mxr_frame(mx, time.time(), create_mxr_frame(SINK, 0x43, payload), ADDR)
sel = f._frame.select_input
print('0x43 :', sel)
assert sel.target_uid == MxrDeviceUid(SINK), 'target must be the sink, the frame header target'
assert sel.source_uid == MxrDeviceUid(SRC),  'source must be the device supplying audio'
assert sel.target_id == 7, sel.target_id
assert sel.source_id == 9, sel.source_id
# the uid at 4 (header target) and the uid at 20 must be the same device
assert f.payload_uuid(4) == sel.target_uid, 'header target and target_uid disagree'
print('0x43 : orientation matches the builder and the header target')

# --- 0x48 mxr_tx_ir_data: timings start at sizeof = 36, not 34
meta = struct.pack('<HHHHB', 2, 38000, 4, 0, 0x01) + bytes(1)      # 10 bytes
p = SINK + bytes([1, 3]) + bytes(2) + struct.pack('<I', 0x11223344) + meta + bytes(2)
assert len(p) == 36, len(p)
timings = struct.pack('<4H', 9000, 4500, 560, 1690)
f = process_mxr_frame(mx, time.time(), create_mxr_frame(SINK, 0x48, p + timings), ADDR)
print('0x48 :', f)
assert f.local_mode == 1 and f.local_bay == 3
assert f.timestamp_ticks == 0x11223344, hex(f.timestamp_ticks)
assert f.carrier_frequency == 38000 and f.nb_timings == 4
assert f.timings_raw == timings, f'timings misaligned: {f.timings_raw[:8].hex()} vs {timings[:8].hex()}'
print('0x48 : timings at sizeof 36, not past the last field at 34')

print()
print('ALL OK')
