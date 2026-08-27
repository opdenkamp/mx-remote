import os, sys, struct, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.proto.Factory import create_mxr_frame, process_mxr_frame
from mx_remote.proto.Constants import (MXR_V2IP_DSCP_SET, MXR_SCALING_FLAG_MODE_VALID,
    MXR_SCALING_FLAG_OPTIONS_VALID, MXR_SCALING_FLAG_AUTO_SCALING)

UID = bytes(range(1, 17)); ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False)
def nm(s, sz=16):
    b = s.encode('ascii')[:sz]; return b + bytes(sz - len(b))
hello = struct.pack('<H', 0x28) + nm('MX-1') + nm('P8SN12345678') + nm('4.7.9') + struct.pack('<I', 1 << 5)
mx.process_frame(time.time(), create_mxr_frame(UID, 0x00, hello), ADDR)
dev = mx.get_by_uid(mx_remote.MxrDeviceUid(UID))

ZERO = bytes(3)
def src(ips):
    out = b''
    for ip, port in ips:
        out += bytes(int(x) for x in ip.split('.')) + struct.pack('<H', port) + bytes(2)
    return out

def cfg(addrs=None, rate=0, dscp=None, scaling=(0, 0, 0)):
    addrs = addrs or [('0.0.0.0', 0)] * 3
    d = dscp or (0, 0, 0)
    mode, refresh, flags = scaling
    out = (UID + src(addrs)                                          # 0..40
           + bytes([rate, d[0], d[1], d[2]]) + bytes(4)              # 40..48 options
           + src([('0.0.0.0', 0)])                                   # 48..56 arc
           + struct.pack('<HHB3s', mode, refresh, flags, ZERO)       # 56..64 scaling
           + bytes(24))                                              # 64..88 tiling
    assert len(out) == 88, len(out)
    return out

def rx(payload):
    f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x3C, payload), ADDR)
    f.process()
    return dev.v2ip_details

def sc(d):
    return (hex(d.scaling.mode), d.scaling.refresh, hex(d.scaling.flags))

# 1. a full periodic broadcast establishes the cache
d = rx(cfg(addrs=[('239.1.1.1', 50020), ('239.1.1.2', 50022), ('239.1.1.3', 50021)],
           rate=60,
           dscp=(MXR_V2IP_DSCP_SET | 34, MXR_V2IP_DSCP_SET | 46, MXR_V2IP_DSCP_SET | 0),
           scaling=(0x1050, 60, MXR_SCALING_FLAG_MODE_VALID | MXR_SCALING_FLAG_OPTIONS_VALID | MXR_SCALING_FLAG_AUTO_SCALING)))
print('broadcast  :', d.video, '| rate', d.tx_rate, '| dscp', d.dscp, '| scaling', sc(d))
assert d.video.ip == '239.1.1.1' and d.tx_rate == 60 and d.scaling.mode == 0x1050

# 2. RATE-ONLY controller write: everything else zeroed on the wire
d = rx(cfg(rate=80))
print('rate-only  :', d.video, '| rate', d.tx_rate, '| dscp', d.dscp, '| scaling', sc(d))
assert d.video.ip == '239.1.1.1', f"addresses wiped: {d.video}"
assert d.audio.ip == '239.1.1.2' and d.anc.ip == '239.1.1.3'
assert d.tx_rate == 80, d.tx_rate
assert d.dscp.audio == 46, 'dscp wiped'
assert d.scaling.mode == 0x1050 and d.scaling.refresh == 60, 'scaling wiped'

# 3. ADDRESS-ONLY write: rate/dscp/scaling all absent
d = rx(cfg(addrs=[('239.9.9.1', 50020), ('239.9.9.2', 50022), ('239.9.9.3', 50021)]))
print('addr-only  :', d.video, '| rate', d.tx_rate, '| dscp', d.dscp, '| scaling', sc(d))
assert d.video.ip == '239.9.9.1' and d.tx_rate == 80 and d.dscp.video == 34
assert d.scaling.mode == 0x1050

# 4. a non-multicast address is not a valid address: cache must survive
d = rx(cfg(addrs=[('192.0.2.5', 50020), ('192.0.2.5', 50022), ('192.0.2.5', 50021)]))
assert d.video.ip == '239.9.9.1', f"unicast accepted: {d.video}"
d = rx(cfg(addrs=[('239.9.9.1', 0), ('239.9.9.2', 0), ('239.9.9.3', 0)]))
assert d.video.ip == '239.9.9.1', f"port 0 accepted: {d.video}"
print('invalid    : unicast and port-0 both rejected, cache intact')

# 5. OPTIONS-ONLY scaling write must keep mode/refresh and clear auto-scaling
d = rx(cfg(scaling=(0, 0, MXR_SCALING_FLAG_OPTIONS_VALID)))
print('opts-only  : scaling', sc(d))
assert d.scaling.mode == 0x1050 and d.scaling.refresh == 60, 'mode lost on options-only write'
assert (d.scaling.flags & MXR_SCALING_FLAG_AUTO_SCALING) == 0, 'auto-scaling not cleared'
assert (d.scaling.flags & MXR_SCALING_FLAG_MODE_VALID) != 0, 'mode validity lost'

# 6. MODE-ONLY scaling write must keep the options nibble
d = rx(cfg(scaling=(0x2060, 50, MXR_SCALING_FLAG_MODE_VALID)))
print('mode-only  : scaling', sc(d))
assert d.scaling.mode == 0x2060 and d.scaling.refresh == 50
assert (d.scaling.flags & MXR_SCALING_FLAG_OPTIONS_VALID) != 0, 'options validity lost'

# 7. a PARTIAL dscp set (video+audio set, anc unset) overwrites - it is not "absent".
#    firmware gates the cache on the video byte alone and stores all three verbatim.
d = rx(cfg(dscp=(MXR_V2IP_DSCP_SET | 8, MXR_V2IP_DSCP_SET | 12, 0)))
print('dscp partial :', d.dscp, '| carried', d.dscp.carried, '| complete', d.dscp.complete)
assert (d.dscp.video, d.dscp.audio, d.dscp.anc) == (8, 12, None), str(d.dscp)
assert d.dscp.carried and not d.dscp.complete

# 8. video byte unset = the frame carried no marking at all, so keep the cache
d = rx(cfg(dscp=(0, MXR_V2IP_DSCP_SET | 20, MXR_V2IP_DSCP_SET | 20)))
print('dscp no-video:', d.dscp)
assert (d.dscp.video, d.dscp.audio, d.dscp.anc) == (8, 12, None), 'cache not kept'

print()
print('ALL OK')
