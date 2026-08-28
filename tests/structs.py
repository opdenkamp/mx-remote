"""Offsets that only a struct can settle: alignment padding, u16 bays, packed records."""
import os, sys, struct, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.proto.Factory import create_mxr_frame, process_mxr_frame
from mx_remote.proto.BayConfig import BayConfig

UID = bytes(range(1, 17)); ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False); mx._uid = bytes(range(100, 116))
def nm(s, sz=16):
    b = s.encode('ascii')[:sz]; return b + bytes(sz - len(b))
hello = struct.pack('<H', 0x28) + nm('MX-1') + nm('P8SN12345678') + nm('4.7.9') + struct.pack('<I', (1<<5)|(1<<17))
mx.process_frame(time.time(), create_mxr_frame(UID, 0x00, hello), ADDR)
def bay(port, mode, num, name):
    # 5 header + 16 name + 16 user_name + 14 signal desc + 2 signal type + 4 + 4 = 61
    return bytes([port, mode, num, 0, 0]) + nm(name) + nm(name) + b'1080p60' + bytes(7) + bytes(2) \
         + struct.pack('<I', 0) + struct.pack('<I', (1 << 1) if mode == 0 else (1 << 0))
mx.process_frame(time.time(), create_mxr_frame(UID, 0x02, bay(0,0,0,'In 1')+bay(1,0,1,'In 2')+bay(2,1,0,'Out 1')), ADDR)

# --- 0x08 mxr_routing_change: PACKED, u16 bays, scrambled between video and audio
#     sink u16@0 | selected u16@2 | video u16@4 | scrambled u8@6 | audio u16@7
p = struct.pack('<HHH', 2, 1, 0) + bytes([1]) + struct.pack('<H', 1)
assert len(p) == 9, len(p)
f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x08, p), ADDR)
print('0x08 :', f)
assert f.sink_bay.port == 2, f.sink_bay
assert f.selected_bay.port == 1, f.selected_bay
assert f.video_bay.port == 0, f.video_bay
assert f.audio_bay.port == 1, f.audio_bay
assert f.scrambled is True
# the four fields must be distinguishable: selected != video here on purpose
assert f.selected_bay.port != f.video_bay.port, 'selected must not be read as video'
print('0x08 : sink/selected/video/audio all read from their own field')
f.process()
sink = mx.get_by_uid(mx_remote.MxrDeviceUid(UID)).get_by_portnum(2)
assert sink.video_source.port == 0, sink.video_source
assert sink.audio_source.port == 1, sink.audio_source
print('0x08 : handler routed video 0 and audio 1 to the sink')

# --- 0x39 mxr_bay_status: local_bay is a u16, description is 14 bytes not 16
sigdesc = b'3840x2160p60Hz'                      # exactly 14, no terminator
sigtype = bytes([16, (2 << 5) | 1])
p = struct.pack('<H', 1) + sigdesc + sigtype + bytes(2) + struct.pack('<II', (1 << 3), (1 << 1))
assert len(p) == 28, len(p)
f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x39, p), ADDR)
print('0x39 :', f)
assert f.bay is not None and f.bay.port == 1, f.bay
assert f.signal_type == '3840x2160p60Hz', repr(f.signal_type)
f.process()
assert f.bay.signal_detected is True
print('0x39 : handler set signal detected on the reporting bay')

# --- bay config: description and signal type are separate fields
rec = bytes([0,0,0,0,0]) + nm('In 1') + nm('In 1') + sigdesc + sigtype + struct.pack('<I',0) + struct.pack('<I',2)
b = BayConfig(rec)
assert b.signal_type == '3840x2160p60Hz', repr(b.signal_type)
assert b.signal is not None and b.signal.svd == 16 and b.signal.bpp == 10
print('0x02 : description', repr(b.signal_type), '| signal', b.signal)

# --- 0x3D mxr_amp_zone_settings: delays are 4-aligned, so padding precedes them
from mx_remote.proto.FrameAmpZoneSettings import FrameAmpZoneSettings
DELAY_L, DELAY_R = 96000, 144000                 # 2s and 3s at 48kHz: both > 65535
p = (bytes(16) + struct.pack('<H', 1) + bytes([200, 200, 1, 248])
     + bytes(2)                                   # padding before delay_left
     + struct.pack('<II', DELAY_L, DELAY_R)
     + bytes([128, 128, 0, 1, 40]) + bytes(3)
     + struct.pack('<I', 900)
     + bytes([1,2,3,4,5]) + bytes([6,7,8,9,10]) + bytes(2))
assert len(p) == 56, len(p)
f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x3D, p), ADDR)
print('0x3D : delays', f.delay_left, f.delay_right, '| bass', f.bass, '| timeout', f.power_timeout)
assert f.delay_left == DELAY_L, f.delay_left
assert f.delay_right == DELAY_R, f.delay_right
assert f.bass == 128 and f.treble == 128 and f.power_timeout == 900
assert f.eq_left == [1,2,3,4,5] and f.eq_right == [6,7,8,9,10]
# a delay above 65535 is the case a 22/26 read cannot represent
assert f.delay_left > 0xFFFF and f.delay_right > 0xFFFF
print('0x3D : delays above 65535 survive, and bass/eq still line up')
f.process()
zone_bay = mx.get_by_uid(mx_remote.MxrDeviceUid(UID)).get_by_portnum(1)
assert zone_bay.amp_settings is not None, 'a notification must reach the cache'
assert zone_bay.amp_settings.delay_left == DELAY_L
# a targeted frame is a request, so it must not reach the cache
req = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x3D, UID + p[16:]), ADDR)
assert not req.is_notification
before = zone_bay.amp_settings.delay_left
req.process()
assert zone_bay.amp_settings.delay_left == before, 'a request must not be cached'
print('0x3D : notification cached, request ignored')

print()
print('ALL OK')
