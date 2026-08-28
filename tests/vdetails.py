######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Bay.video_details: one format, from whichever source has it.

Two sources carry the same four fields, and they are not equally current. The
bay config snapshot refreshes on the broadcast cycle; a signal status report
arrives on a signal change. The report therefore wins, and from_report says
which one a caller is holding.
'''

import os, struct, sys, time, logging
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

feat = (1 << 5) | (1 << 6)
rx(0x00, struct.pack('<H', 0x28) + name('MX-1') + name('P8SN12345678')
        + name('5.0.0') + struct.pack('<I', feat))
dev = mx.get_by_uid(mx_remote.MxrDeviceUid(UID))

# ---- nothing has carried a format yet
sigdesc = b'1920x1080p60Hz'                       # exactly 14, no terminator
def cfg(port, sigtype):
    return bytes([port, 0, port, 0, 0]) + name('In %d' % port) + name('In %d' % port) \
         + sigdesc + sigtype + struct.pack('<I', 0) + struct.pack('<I', 2)

UNSET = bytes([0, (5 << 5)])                      # bpp index 5 is the unset sentinel
rx(0x02, cfg(0, UNSET))
bay = dev.get_by_portnum(0)
assert bay.video_details is None, 'an unset signal type is not a format'
print('unset       : None')

# ---- the bay config snapshot is the fallback
# svd 16, colour 1 (YUV444), bpp index 2 (=10), non_int at bit 4
SNAP = bytes([16, (2 << 5) | (1 << 4) | 1])
rx(0x02, cfg(0, SNAP))
d = bay.video_details
assert d is not None and d.from_report is False, d
assert d.svd == 16, d.svd
assert d.colour == mx_remote.VideoColourSpace.YUV444, d.colour
assert d.bpp == 10, d.bpp
assert d.non_int is True, d.non_int
print('bay config  :', d)

# ---- a signal status report supersedes it, and says so
def av_details(port, status, svd, bpp, colour):
    hdr   = struct.pack('<HBBB3s', 1, 0x03, 0x00, 8, b'\0\0\0')
    video = bytes([svd, colour, bpp, 1, 0, 0, 0, 0]) + struct.pack('<HIH', 60, 297000000, 0)
    baybl = struct.pack('<HI', port, status) + bytes([svd, (2 << 5) | 1]) + struct.pack('<I', 297000000)
    d = hdr + bytes(16) + bytes(16) + video + bytes(32) + struct.pack('<III', 0, 0, 0) + baybl
    assert len(d) == 112, len(d)
    return d

STATUS = (1 << 3) | (1 << 4)
rx(0x31, av_details(0, STATUS, svd=97, bpp=12, colour=int(mx_remote.VideoColourSpace.YUV422)))
d = bay.video_details
assert d is not None and d.from_report is True, d
assert d.svd == 97, d.svd
assert d.colour == mx_remote.VideoColourSpace.YUV422, d.colour
assert d.bpp == 12, d.bpp
print('report      :', d)

# ---- and a later bay config does not pull the older snapshot back over it
rx(0x02, cfg(0, SNAP))
d = bay.video_details
assert d.from_report is True, 'the snapshot must not displace a report'
assert d.svd == 97 and d.bpp == 12, d
print('after cfg   : report still held ->', d)

print('ALL OK')
