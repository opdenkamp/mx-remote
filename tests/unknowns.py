import os, sys, struct, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.proto.Factory import create_mxr_frame, process_mxr_frame
from mx_remote.proto.Constants import decode_enum, FirmwareType, RCKey, RCAction, UtpLinkSpeed

UID = bytes(range(1, 17)); ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False); mx._uid = bytes(range(100, 116))
def nm(s, sz=16):
    b = s.encode('ascii')[:sz]; return b + bytes(sz - len(b))
mx.process_frame(time.time(), create_mxr_frame(UID, 0x00, struct.pack('<H',0x28)+nm('MX-1')+nm('P8SN12345678')+nm('4.7.9')+struct.pack('<I',1<<5)), ADDR)
def bay(port, mode, num, name):
    return bytes([port, mode, num, 0, 0]) + nm(name) + nm(name) + nm('1080p') \
         + struct.pack('<I', 0) + struct.pack('<I', (1 << 1) if mode == 0 else (1 << 0))
mx.process_frame(time.time(), create_mxr_frame(UID, 0x02, bay(0,0,0,'In 1')+bay(1,1,0,'Out 1')), ADDR)

# --- the helper itself
assert decode_enum(FirmwareType, 99) == FirmwareType.UNKNOWN
assert decode_enum(FirmwareType, None) == FirmwareType.UNKNOWN
assert decode_enum(FirmwareType, 2) == FirmwareType.LINUX
assert decode_enum(RCKey, 9999) is None, 'RCKey has no UNKNOWN, so unknown is None'
assert decode_enum(RCAction, 99) is None
assert decode_enum(UtpLinkSpeed, 7) == UtpLinkSpeed.UNKNOWN
# and never a confident wrong answer
assert decode_enum(FirmwareType, 99) != FirmwareType.FPGA
print('helper : unknown -> UNKNOWN where defined, else None; never clamped')

# --- a frame carrying an unknown value must not kill the receive path
def rx(op, pl):
    f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, op, pl), ADDR)
    f.process()
    return f

# 0x2A firmware type 99 - used to raise ValueError out of process_frame
f = rx(0x2A, struct.pack('<III', 99, 0xCAFEBABE, 1700000000) + nm('9.9.9', 128))
assert f.fw_type == FirmwareType.UNKNOWN, f.fw_type
assert f.build_timestamp == 1700000000
print('0x2A   :', f)

# 0x0B an RC key code this build does not know
f = rx(0x0B, struct.pack('<HH', 1, 9999))
assert f.key is None
print('0x0B   : unknown key ->', f.key)

# 0x0D an RC action this build does not know
f = rx(0x0D, struct.pack('<HH', 1, 99))
assert f.action is None
print('0x0D   : unknown action ->', f.action)

# 0x42 a multiviewer sub-opcode from a newer firmware
f = rx(0x42, UID + bytes([200]) + bytes(7) + bytes([1]))
from mx_remote.proto.Multiviewer import MultiviewerOpcode
assert f.opcode == MultiviewerOpcode.UNKNOWN
print('0x42   : unknown sub-opcode ->', f.opcode)

print()
print('ALL OK')
