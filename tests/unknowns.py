import os, sys, struct, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.proto.Factory import create_mxr_frame, process_mxr_frame
from mx_remote.Uid import MxrDeviceUid
from mx_remote.proto.Constants import (decode_enum, FirmwareType, RCKey, RCAction, UtpLinkSpeed,
    MXR_OPCODE_VERSIONS)

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
assert decode_enum(FirmwareType, 2) == FirmwareType.RTOS
assert decode_enum(FirmwareType, 0) == FirmwareType.MCU, 'type 0 is the unit firmware, not unknown'
assert decode_enum(RCKey, 9999) is None, 'RCKey has no UNKNOWN, so unknown is None'
assert decode_enum(RCAction, 99) is None
assert decode_enum(UtpLinkSpeed, 7) == UtpLinkSpeed.UNKNOWN
# and never a confident wrong answer
assert decode_enum(FirmwareType, 99) != FirmwareType.VIDEO_PROCESSOR
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

# A video processor report carries the RTOS and loader hashes behind its 144
# bytes, then the unit's firmware and bootloader, each with its own hash, time
# and version, as units on the mesh send all 200.
report = (struct.pack('<III', 1, 0x11111111, 1700000001) + nm('fpga-3.1', 128) + bytes([0xA5] * 4)
          + struct.pack('<II', 0x22222222, 0x33333333)
          + struct.pack('<IIII', 0x44444444, 1700000002, 0x55555555, 1700000003)
          + nm('4.7.9', 16) + nm('boot-1.2', 16))
assert len(report) == 200, len(report)
f = rx(0x2A, report)
got = {v.firmware_type: (v.hash, v.timestamp, v.version) for v in f.versions}
assert got == {FirmwareType.VIDEO_PROCESSOR: (0x11111111, 1700000001, 'fpga-3.1'),
               FirmwareType.RTOS: (0x22222222, 1700000001, 'fpga-3.1'),
               FirmwareType.LOADER: (0x33333333, 1700000001, 'fpga-3.1'),
               FirmwareType.MCU: (0x44444444, 1700000002, '4.7.9'),
               FirmwareType.BOOTLOADER: (0x55555555, 1700000003, 'boot-1.2')}, got
assert set(mx.get_by_uid(MxrDeviceUid(UID)).oneip_firmware_versions) >= set(got), 'not every version was kept'
assert [v.firmware_type for v in rx(0x2A, report[:199]).versions] == \
    [FirmwareType.VIDEO_PROCESSOR, FirmwareType.RTOS, FirmwareType.LOADER], 'a block was read past the frame'
assert len(rx(0x2A, report[:151]).versions) == 1
print('0x2A   : a video processor report names five components')

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

# 0x3F a decoder reason and colour format from a newer firmware. Neither enum
# has an UNKNOWN member, because 0 is a verdict in both - OK and RGB - so
# folding an unrecognised value onto a member is a confident wrong answer where
# None is an honest one.
from mx_remote.proto.V2IPStats import V2IPDecoderReason, V2IPColorFormat
assert decode_enum(V2IPDecoderReason, 200) is None
assert decode_enum(V2IPColorFormat, 0x0102) is None
assert decode_enum(V2IPDecoderReason, 4) == V2IPDecoderReason.FORMAT_MISMATCH
assert decode_enum(V2IPColorFormat, 255) == V2IPColorFormat.UNNAMED

detail = bytes([1, 200, 0, 0]) + struct.pack('<HHHH', 1920, 1080, 0x0102, 3) \
       + struct.pack('<II', 0, 0) + bytes(4)
# stamped as a device stamps this opcode, which is the opcode's row
raw = bytearray(create_mxr_frame(UID, 0x3F, bytes(128) + detail))
raw[2] = MXR_OPCODE_VERSIONS[0x3F]
f = process_mxr_frame(mx, time.time(), bytes(raw), ADDR)
f.process()
reading = f.decoder.reading
assert reading.reason is None and reading.reason_value == 200, reading.reason
assert reading.format is None and reading.format_value == 0x0102, reading.format
assert reading.width == 1920, 'an unnamed value must not cost the rest of the block'
print('0x3F   : unknown reason/format ->', reading.reason, '/', reading.format)

print()
print('ALL OK')
