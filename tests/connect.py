######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''The Pulse-Eight device a connect frame names on a bay.

The 96-byte long form of DEV_CONNECT (0x04) carries the connected device's
model_info at 4. The fixture is composed from the layout the Rust crate pins,
with every byte no field covers poisoned, so a field read at a neighbour's
offset or width reads a different value.
'''

import os, struct, sys, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import DeviceFeature, MxrDeviceUid, P8ModelInfo
from mx_remote.proto.Factory import create_mxr_frame

UID = bytes([111]) * 16
ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False)

def rx(opcode, payload=b''):
    mx.process_frame(time.time(), create_mxr_frame(UID, opcode, payload), ADDR)

def nm(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def rec(port, mode, name):
    return bytes([port, mode, port, 0, 0]) + nm(name) + nm(name) + nm('1080p') + struct.pack('<II', 0, 0)

rx(0x00, struct.pack('<H', 0x2F) + nm('MX-1') + nm('P8SN00000111') + nm('5.0.0')
         + struct.pack('<I', int(DeviceFeature.VIDEO_ROUTING)))
rx(0x02, rec(1, 1, 'Output 1') + rec(2, 1, 'Output 2'))
dev = mx.get_by_uid(MxrDeviceUid(UID))
out1, out2 = dev.get_by_portnum(1), dev.get_by_portnum(2)
assert out1 is not None and out2 is not None

def p8_connect(port, connected):
    p = bytearray([0xA5] * 96)
    p[0] = port
    p[1] = connected
    for at, s in ((4, 'Pulse-Eight'), (20, 'PROAMP8'), (37, 'P8SN00001234'), (53, '1.4.2')):
        p[at:at + 16] = nm(s)
    p[36] = 7
    p[72:76] = struct.pack('<i', 1)
    p[76:80] = struct.pack('<i', 3)
    p[80] = 1
    p[81] = 0
    p[84:88] = bytes([10, 66, 0, 150])
    p[88:92] = bytes([255, 255, 254, 0])
    p[92:96] = bytes([10, 66, 0, 1])
    return bytes(p)

PROAMP = P8ModelInfo(vendor='Pulse-Eight', model='PROAMP8', board_rev=7, serial='P8SN00001234',
                     version='1.4.2', remote_mode=1, remote_bay=3, loopback=True, hdmi=False,
                     ip='10.66.0.150', mask='255.255.254.0', gateway='10.66.0.1')

assert out2.p8_device is None
rx(0x04, p8_connect(2, 1))
assert out2.p8_device == PROAMP, out2.p8_device
assert out2.hpd_detected, 'the connect status was not applied'
assert out1.p8_device is None, 'port 2 only'
print('long        :', out2.p8_device)

# A negative mode is unknown rather than a huge number.
p = bytearray(p8_connect(2, 1)); p[72:76] = struct.pack('<i', -1)
rx(0x04, bytes(p))
assert out2.p8_device.remote_mode == -1, out2.p8_device.remote_mode

rx(0x04, p8_connect(2, 1)[:95])
assert out2.p8_device is None, 'a frame too short to hold it'
assert out2.hpd_detected, 'a short connect frame was not applied'
rx(0x04, p8_connect(2, 1))
assert out2.p8_device == PROAMP
rx(0x04, p8_connect(2, 0))
assert out2.p8_device is None, 'disconnected'
assert not out2.hpd_detected, 'the disconnect was not applied'
print('short/off   : no device')

print('ALL OK')
