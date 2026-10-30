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
def av_details(port, status, svd, bpp, colour, support=0x03, flags=0x00, active=(0, 0)):
    hdr   = struct.pack('<HBBB3s', 1, support, flags, 8, b'\0\0\0')
    video = bytes([svd, colour, bpp, 1, 0, 0, 0, 0]) + struct.pack('<HIH', 60, 297000000, 0)
    # the timing block, poisoned but for the active width at 58 and height at 68
    vsync = bytearray([0xA5] * 32)
    vsync[2:4] = struct.pack('<H', active[0])
    vsync[12:14] = struct.pack('<H', active[1])
    baybl = struct.pack('<HI', port, status) + bytes([svd, (2 << 5) | 1]) + struct.pack('<I', 297000000)
    d = hdr + bytes(16) + bytes(16) + video + bytes(vsync) + struct.pack('<III', 0, 0, 0) + baybl
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

# ---- a report hands over what signal_type is written from
INTERLACED, HDR = 1 << 1, 1 << 4
rx(0x31, av_details(0, STATUS, svd=20, bpp=10, colour=int(mx_remote.VideoColourSpace.YUV420),
                    flags=INTERLACED | HDR, active=(1680, 1050)))
d = bay.video_details
assert (d.svd, d.width, d.height, d.colour, d.bpp) == (20, 1920, 1080, mx_remote.VideoColourSpace.YUV420, 10), d
assert (d.interlaced, d.hdr) == (True, True), (d.interlaced, d.hdr)
assert bay.signal_type.startswith('1920x1080 / ') and ' interlaced HDR ' in bay.signal_type, bay.signal_type
rx(0x31, av_details(0, STATUS, svd=20, bpp=10, colour=0, flags=HDR, active=(1680, 1050)))
d = bay.video_details
assert (d.interlaced, d.hdr) == (False, True), (d.interlaced, d.hdr)

# A stream with no mode is described by the size its timing measures.
rx(0x31, av_details(0, STATUS, svd=0, bpp=10, colour=0, flags=HDR, active=(1680, 1050)))
d = bay.video_details
assert d.from_report and (d.svd, d.width, d.height, d.interlaced, d.hdr) == (0, 1680, 1050, False, True), d
assert bay.signal_type.startswith('1680x1050 / '), bay.signal_type

# A stream detected but not valid describes no video.
rx(0x31, av_details(0, STATUS, svd=16, bpp=10, colour=0, support=0x01, active=(1680, 1050)))
assert bay.signal_type == 'Invalid Signal', bay.signal_type
d = bay.video_details
assert d is None or not d.from_report, 'a stream that is not valid described its video: %s' % d
a = mx_remote.VideoSignalDetails(svd=20, colour=None, bpp=10, non_int=False, from_report=True,
                                 width=1920, height=1080, interlaced=False, hdr=False)
for k in ('width', 'height', 'interlaced', 'hdr'):
    b = mx_remote.VideoSignalDetails(svd=20, colour=None, bpp=10, non_int=False, from_report=True,
                                     **{**dict(width=1920, height=1080, interlaced=False, hdr=False),
                                        k: {'width': 1280, 'height': 720}.get(k, True)})
    assert a != b, 'details differing in %s compare equal' % k
print('parts       : size, interlaced and HDR as signal_type is written from them')

print('ALL OK')
