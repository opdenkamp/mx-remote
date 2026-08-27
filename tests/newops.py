import os, sys, struct, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.proto.Factory import create_mxr_frame, process_mxr_frame
from mx_remote.proto.Constants import RCKey, VideoWallOperation, video_wall_geometry_valid

UID = bytes(range(1, 17)); ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False)
mx._uid = bytes(range(100, 116))
def nm(s, sz=16):
    b = s.encode('ascii')[:sz]; return b + bytes(sz - len(b))

# register the sender, with a couple of bays so lookups resolve
hello = struct.pack('<H', 0x28) + nm('MX-1') + nm('P8SN12345678') + nm('4.7.9') + struct.pack('<I', (1<<5)|(1<<24))
mx.process_frame(time.time(), create_mxr_frame(UID, 0x00, hello), ADDR)
def bay(port, mode, num, name):
    return bytes([port, mode, num, 0, 0]) + nm(name) + nm(name) + nm('1080p') \
         + struct.pack('<I', 0) + struct.pack('<I', (1 << 1) if mode == 0 else (1 << 0))
mx.process_frame(time.time(), create_mxr_frame(UID, 0x02, bay(0, 0, 0, 'In 1') + bay(1, 1, 0, 'Out 1')), ADDR)

def rx(opcode, payload=b''):
    return process_mxr_frame(mx, time.time(), create_mxr_frame(UID, opcode, payload), ADDR)

# --- 0x0C RC_TX_KEY: uid[16] + bay u16 + key u16
f = rx(0x0C, UID + struct.pack('<HH', 1, int(RCKey.KEY_PLAY)))
print('0x0C :', f)
assert f.target_uid == mx_remote.MxrDeviceUid(UID) and f.key == RCKey.KEY_PLAY
assert f.bay is not None and f.bay.port == 1
f.process()

# --- 0x0E RC_TX_ACTION: same shape with an action
from mx_remote.proto.Constants import RCAction
f = rx(0x0E, UID + struct.pack('<HH', 1, int(RCAction.ACTION_VOLUME_UP)))
print('0x0E :', f)
assert f.action == RCAction.ACTION_VOLUME_UP
f.process()

# --- 0x11 AUDIO_CLIP: u8 bay + u8 clip
f = rx(0x11, bytes([1, 42]))
print('0x11 :', f)
assert f.clip == 42 and f.bay is not None and f.bay.port == 1
f.process()

# --- 0x13 AUDIO_SET_ROUTE: serial[16] + sink u16 + source u16  (serial, not uid)
f = rx(0x13, nm('P8SN12345678') + struct.pack('<HH', 1, 0))
print('0x13 :', f)
assert f.target_serial == 'P8SN12345678'
assert f.sink_bay is not None and f.sink_bay.port == 1
assert f.source_bay is not None and f.source_bay.port == 0
f.process()

# --- 0x21 V2IP_DETECT_BAYS: empty payload
f = rx(0x21)
print('0x21 :', f)
f.process()

# --- 0x49 V2IP_VIDEOWALL, STORE with a real window
def wall(target, x, y, w, h, rw, rh, op):
    p = target + struct.pack('<HHHHHHB', x, y, w, h, rw, rh, int(op)) + bytes(3)
    assert len(p) == 32, len(p)
    return p
f = rx(0x49, wall(UID, 1920, 0, 1920, 1080, 3840, 2160, VideoWallOperation.STORE))
print('0x49 :', f)
assert f.operation == VideoWallOperation.STORE
assert (f.position_x, f.position_y, f.width, f.height) == (1920, 0, 1920, 1080)
assert (f.raster_width, f.raster_height) == (3840, 2160)
assert f.geometry_valid and not f.clears_wall
f.process()

# PREVIEW
f = rx(0x49, wall(UID, 0, 0, 1920, 1080, 3840, 2160, VideoWallOperation.PREVIEW))
assert f.operation == VideoWallOperation.PREVIEW and f.has_window
print('0x49 :', f)

# a zero window is a CLEAR, not "unset"
f = rx(0x49, wall(UID, 0, 0, 0, 0, 3840, 2160, VideoWallOperation.STORE))
print('0x49 :', f)
assert f.clears_wall and f.width == 0 and f.geometry_valid

# REVERT carries no geometry - its zeros must not read as a clear
f = rx(0x49, wall(UID, 0, 0, 0, 0, 0, 0, VideoWallOperation.REVERT))
print('0x49 :', f)
assert f.operation == VideoWallOperation.REVERT
assert not f.has_window and not f.clears_wall
assert f.width is None and f.position_x is None and f.raster_width is None

# geometry the sink would refuse
f = rx(0x49, wall(UID, 100, 0, 1920, 1080, 3840, 2160, VideoWallOperation.STORE))
print('0x49 :', f)
assert not f.geometry_valid, 'pos_x 100 is not a multiple of 64'
assert not video_wall_geometry_valid(pos_x=0, width=32, height=64), 'width below minimum'
assert not video_wall_geometry_valid(pos_x=0, width=98, height=64), 'width not a multiple of 4'
assert video_wall_geometry_valid(pos_x=0, width=0, height=0), 'a clear is always valid'

# the feature bit
dev = mx.get_by_uid(mx_remote.MxrDeviceUid(UID))
assert dev.supports_video_wall
print('feature: video wall advertised ->', dev.supports_video_wall)

print()
print('ALL OK')
