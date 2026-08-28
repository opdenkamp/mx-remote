import os, sys, struct, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.proto.Factory import create_mxr_frame, process_mxr_frame
from mx_remote.proto.Constants import MxrSignalType

UID = bytes(range(1, 17)); ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False); mx._uid = bytes(range(100, 116))
def nm(s, sz=16):
    b = s.encode('ascii')[:sz]; return b + bytes(sz - len(b))
mx.process_frame(time.time(), create_mxr_frame(UID, 0x00, struct.pack('<H',0x28)+nm('MX-1')+nm('P8SN12345678')+nm('4.7.9')+struct.pack('<I',(1<<3)|(1<<5))), ADDR)

def entry(uid, ips):
    out = uid
    for ip, port in ips:
        out += bytes(int(x) for x in ip.split('.')) + struct.pack('<H', port) + bytes(2)
    return out
good = entry(UID, [('239.1.1.1', 50020), ('239.1.1.2', 50022), ('239.1.1.3', 50021)])
# a bay-0 record built from stack contents: plausible bytes, not multicast
junk = entry(UID, [('192.0.2.201', 8261), ('192.0.2.7', 12), ('192.0.2.3', 40)])
assert len(good) == 40 and len(junk) == 40
f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x26, junk + good), ADDR)
srcs = f.sources
print('entry 0 (stack junk):', srcs[0].video, '-> valid:', srcs[0].valid)
print('entry 1 (real)      :', srcs[1].video, '-> valid:', srcs[1].valid)
junk_src = srcs[0]
assert srcs[0].valid is False, 'a non-multicast address must not read as usable'
assert srcs[1].valid is True
assert len(srcs) == 2, 'entries are positional - invalid ones are flagged, never dropped'

# a multicast address with port 0 is also not usable
zeroport = entry(UID, [('239.1.1.1', 0), ('239.1.1.2', 0), ('239.1.1.3', 0)])
f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x26, zeroport), ADDR)
assert f.sources[0].valid is False
print('port 0              : rejected')

# the handler is what puts the list on the device
f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x26, junk + good), ADDR)
f.process()
cached = mx.get_by_uid(mx_remote.MxrDeviceUid(UID)).v2ip_sources
assert cached is not None and len(cached) == 2, cached
assert cached[0].valid is False and cached[1].valid is True
print('handler             : both entries cached, validity preserved')

# an unset signal type answers nothing
unset = MxrSignalType(bytes([0, (5 << 5)]))
print('unset signal type   :', unset, '| svd', unset.svd, '| color', unset.color, '| bpp', unset.bpp)
assert (unset.svd, unset.color, unset.non_int, unset.bpp) == (None, None, None, None)
# a real non-HDMI signal still reports svd 0 - a value, not an absence
nonhdmi = MxrSignalType(bytes([0, (2 << 5) | 1]))
assert nonhdmi.is_set and nonhdmi.svd == 0 and nonhdmi.bpp == 10
print('non-HDMI, 10bpp     :', nonhdmi, '| svd', nonhdmi.svd)
# and a set format whose depth is unknown is 0, not None - different answers
unknown_depth = MxrSignalType(bytes([16, (0 << 5) | 1]))
assert unknown_depth.is_set and unknown_depth.bpp == 0
print('set, depth unknown  : bpp', unknown_depth.bpp, '(0, not None)')
print()
# Three states, not two. An all-zero entry reports that the source went away and
# is the only signal of it, so it must not be discarded as malformed.
cleared = entry(UID, [('0.0.0.0', 0), ('0.0.0.0', 0), ('0.0.0.0', 0)])
f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x26, cleared + good), ADDR)
srcs = f.sources
print('cleared entry       :', srcs[0].video, '-> valid', srcs[0].valid, '| cleared', srcs[0].cleared)
assert srcs[0].valid is False and srcs[0].cleared is True
assert srcs[1].valid is True and srcs[1].cleared is False

f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x26, junk), ADDR)
malformed = f.sources[0]
assert malformed.valid is False and malformed.cleared is False
print('malformed entry     : neither valid nor cleared')

print()
print('ALL OK')
