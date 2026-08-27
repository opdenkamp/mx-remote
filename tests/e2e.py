import os, sys, logging, struct, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.proto.Factory import create_mxr_frame

UID = bytes(range(1, 17))
ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False)

def rx(opcode, payload=b''):
    mx.process_frame(time.time(), create_mxr_frame(UID, opcode, payload), ADDR)

def name(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

# ---- hello so the device registers
feat = (1 << 5) | (1 << 6) | (1 << 24)          # video+audio routing + VIDEO_WALL
hello = struct.pack('<H', 0x28) + name('MX-1') + name('P8SN12345678') + name('4.7.9') + struct.pack('<I', feat)
rx(0x00, hello)
dev = mx.get_by_uid(mx_remote.MxrDeviceUid(UID))
print('device      :', dev, '| video wall:', dev.supports_video_wall)
assert dev.supports_video_wall

# ---- bay config, paged: 3 bays over 2 frames. a merging receiver ends with 3.
def bay(port, mode, num, nm):
    return bytes([port, mode, num, 0, 0]) + name(nm) + name(nm) + name('1080p') \
         + struct.pack('<I', 0) + struct.pack('<I', (1 << 1) if mode == 0 else (1 << 0))
rx(0x02, bay(0, 0, 0, 'In 1') + bay(1, 0, 1, 'In 2'))     # page 1
rx(0x02, bay(2, 1, 0, 'Out 1'))                            # page 2
print('bays        :', sorted(b.bay_name for b in dev.bays.values()))
assert len(dev.bays) == 3, dev.bays

# ---- links, paged the same way
def link(port, serial, baynm):
    return bytes([port, 0]) + name(serial) + name(baynm) + struct.pack('<I', 1)
rx(0x03, link(0, 'P8SN00000001', 'Out 1'))
rx(0x03, link(1, 'P8SN00000002', 'Out 2'))
print('links       : merged ok')

# ---- 0x31 signal status: full 112-byte report for port 1
def av_details(port, status, svd=16, bpp_idx=2, clock=297000000):
    hdr   = struct.pack('<HBBB3s', 1, 0x03, 0x00, 8, b'\0\0\0')      # version, support, stream, depth
    avi   = bytes(16)
    audio = bytes(16)
    video = bytes([svd, 1, 8, 1, 0, 0, 0, 0]) + struct.pack('<HIH', 60, 297000000, 0)
    vsync = bytes(32)
    errs  = struct.pack('<III', 0, 0, 0)
    sig   = bytes([svd, (bpp_idx << 5) | 1])
    baybl = struct.pack('<HI', port, status) + sig + struct.pack('<I', clock)
    d = hdr + avi + audio + video + vsync + errs + baybl
    assert len(d) == 112, len(d)
    return d

from mx_remote.proto.FrameSignalStatusNew import FrameSignalStatusNew
from mx_remote.proto.Factory import process_mxr_frame
STATUS = (1 << 3) | (1 << 4) | (1 << 21)   # signal, hpd, and ENCODER_ERROR at 21
f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x31, av_details(1, STATUS)), ADDR)
print('0x31 report :', f)
assert isinstance(f, FrameSignalStatusNew)
assert f.port_number == 1, f.port_number
assert f.video.frame_rate == 60, f.video.frame_rate
assert f.video.tmds_clock == 297000000, f.video.tmds_clock
assert f.scaling.bpp == 10 and f.scaling.svd == 16, str(f.scaling)
assert f.clock_rate == 297000000
# the whole word, not just the flags read below: a u32 -> u16 truncation keeps
# every bit any flag assertion tests, so only the full value catches it
assert int(f.bay_status) == STATUS, hex(int(f.bay_status))
print('  port', f.port_number, '| status', f.bay_status, '| scaling', f.scaling, '| clock', f.clock_rate)
f.process()

# ---- a truncated (68..111 byte) report must not be attributed to a bay
short = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x31, av_details(1, 0)[:68]), ADDR)
assert short.bay_details == b'', short.bay_details
assert short.port_number == 0xFF
short.process()   # must be a no-op, not a misattribution
print('short report: dropped, not misattributed')

# ---- 0x3C device config with dscp
from mx_remote.proto.Constants import MXR_V2IP_DSCP_SET
def av_source(ips):
    out = b''
    for ip, port in ips:
        out += bytes(int(x) for x in ip.split('.')) + struct.pack('<H', port) + bytes(2)
    return out
cfg = UID \
    + av_source([('239.1.1.1', 50020), ('239.1.1.2', 50022), ('239.1.1.3', 50021)]) \
    + bytes([60, MXR_V2IP_DSCP_SET | 34, MXR_V2IP_DSCP_SET | 46, MXR_V2IP_DSCP_SET | 0]) + bytes(4) \
    + av_source([('0.0.0.0', 0)]) + bytes(2) \
    + struct.pack('<HHB3s', 0, 60, 1, b'\0\0\0') \
    + bytes(24)
f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x3C, cfg), ADDR)
print('0x3C cfg    :', f)
f.process()
d = dev.v2ip_details
print('  rate', d.tx_rate, '| dscp', d.dscp)
assert d.tx_rate == 60 and (d.dscp.video, d.dscp.audio, d.dscp.anc) == (34, 46, 0)

# ---- an address-only write (rate 0, no dscp) must not wipe them
cfg2 = bytearray(cfg); cfg2[40:44] = bytes([0, 0, 0, 0])
f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x3C, bytes(cfg2)), ADDR)
f.process()
d = dev.v2ip_details
print('  after address-only write: rate', d.tx_rate, '| dscp', d.dscp)
assert d.tx_rate == 60 and d.dscp.audio == 46

print('\nALL OK')
