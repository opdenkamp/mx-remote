import os, sys, struct, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.proto.Factory import create_mxr_frame, process_mxr_frame
from mx_remote.proto.Constants import MXR_OPCODE_VERSIONS

UID = bytes(range(1, 17)); ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False); mx._uid = bytes(range(100, 116))
def nm(s, sz=16):
    b = s.encode('ascii')[:sz]; return b + bytes(sz - len(b))
hello = struct.pack('<H', 0x28) + nm('MX-1') + nm('P8SN12345678') + nm('4.7.9') + struct.pack('<I', 1 << 5)
mx.process_frame(time.time(), create_mxr_frame(UID, 0x00, hello), ADDR)
def bay(port, mode, num, name):
    return bytes([port, mode, num, 0, 0]) + nm(name) + nm(name) + nm('1080p') \
         + struct.pack('<I', 0) + struct.pack('<I', (1 << 1) if mode == 0 else (1 << 0))
mx.process_frame(time.time(), create_mxr_frame(UID, 0x02, bay(0, 0, 0, 'In 1') + bay(9, 1, 0, 'Out 1')), ADDR)

def rx(op, pl):
    '''Decode a frame stamped the way a device sends it: at the opcode's floor.

    Some receivers refuse a frame stamped below the version that introduced
    their opcode, so a fixture stamped at 1 is not a frame any device would
    have sent, and testing offsets on one would test a frame nobody accepts.
    '''
    f = bytearray(create_mxr_frame(UID, op, pl))
    f[2] = MXR_OPCODE_VERSIONS.get(op, 1)
    return process_mxr_frame(mx, time.time(), bytes(f), ADDR)

# --- 0x09 mxr_routing_change_request: PACKED, u16 bays, 21 bytes
#     bay numbers deliberately > 255 so a u8 read cannot accidentally pass
p = nm('P8SN12345678') + struct.pack('<HHB', 300, 511, 1)
assert len(p) == 21, len(p)
f = rx(0x09, p)
print('0x09 :', f)
assert f.serial == 'P8SN12345678'
assert f.sink_bay == 300, f.sink_bay
assert f.source_bay == 511, f.source_bay
assert f.no_power_on is True
# and the low-byte case that used to "work" by accident
f = rx(0x09, nm('P8SN12345678') + struct.pack('<HHB', 9, 0, 0))
assert (f.sink_bay, f.source_bay, f.no_power_on) == (9, 0, False)
print('0x09 : u16 bays, no_power_on at 20')

# --- 0x0A mxr_ir_data: not packed, 2 bytes pad after the u16 port, 24 bytes
# nb_timings and repeat_offset describe the timings appended below. Nothing on
# the wire ties them to what arrived, and a receiver reads that many entries, so
# a fixture claiming more than it carries is a frame that would over-read a
# device - and one this library now refuses.
meta = struct.pack('<HHHHB', 2, 38000, 8, 4, 0x03) + bytes(1)   # 10 bytes
p = struct.pack('<H', 9) + bytes(2) + struct.pack('<II', 0xDEADBEEF, 0x0BADF00D) + meta + bytes(2)
assert len(p) == 24, len(p)
timings = struct.pack('<8H', *range(100, 108))
f = rx(0x0A, p + timings)
print('0x0A :', f)
assert f.bay is not None and f.bay.port == 9
assert f.ir_timestamp == 0xDEADBEEF, hex(f.ir_timestamp)
assert f.last_change == 0x0BADF00D, hex(f.last_change)
assert f.timer_resolution == 2 and f.frequency == 38000
assert f.nb_timings == 8 and f.repeat_offset == 4 and f.status == 0x03
assert f.timings == timings, 'timings must start at sizeof(mxr_ir_data) = 24'
print('0x0A : timestamp past the padding, timings at 24')

# --- 0x09 and 0x13 are the same struct; they must agree on bay width
f9  = rx(0x09, nm('P8SN12345678') + struct.pack('<HHB', 300, 511, 0))
f13 = rx(0x13, nm('P8SN12345678') + struct.pack('<HH', 300, 511))
assert f9.sink_bay == 300 and f9.source_bay == 511
assert f13.payload_u16(16) == 300 and f13.payload_u16(18) == 511
print('0x09/0x13 : agree on u16 bays')

print()
print('ALL OK')
