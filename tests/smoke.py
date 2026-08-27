import os, sys, struct
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mx_remote
from mx_remote.proto.Constants import (MXR_PROTOCOL_VERSION, MXR_OPCODE_VERSIONS, DeviceFeature,
    MXR_V2IP_DSCP_SET, V2IP_DSCP_DEFAULT, v2ip_dscp_value, v2ip_rate_valid, MxrSignalType, mxr_sig_bpp_get)
from mx_remote.proto.FrameV2IPDeviceConfiguration import V2IPDeviceOptions
from mx_remote.Interface import DeviceV2IPDetails, V2IPDscpConfig

print('version', mx_remote.const.VERSION, 'proto', hex(MXR_PROTOCOL_VERSION))
assert MXR_PROTOCOL_VERSION == 0x28
assert MXR_OPCODE_VERSIONS[0x49] == 0x28 and MXR_OPCODE_VERSIONS[0x3C] == 0x11
assert DeviceFeature.VIDEO_WALL == (1 << 24)

# --- dscp: 0 is a legal marking, only the set bit says it is there
opts = V2IPDeviceOptions(bytes([50, MXR_V2IP_DSCP_SET | 0, MXR_V2IP_DSCP_SET | 16, MXR_V2IP_DSCP_SET | 63]))
assert opts.tx_rate == 50, opts.tx_rate
assert (opts.dscp.video, opts.dscp.audio, opts.dscp.anc) == (0, 16, 63), str(opts.dscp)
assert opts.dscp.complete
print('dscp set  :', opts)

# --- no marking, no rate (an address-only controller write)
opts2 = V2IPDeviceOptions(bytes([0, 0, 0, 0]))
assert opts2.tx_rate is None and not opts2.dscp.complete
assert opts2.dscp.video is None
print('dscp unset:', opts2)

# --- merge keeps the cached rate/marking a rate-less write does not carry
prev = DeviceV2IPDetails(None, None, None, None, tx_rate=50, scaling=None, dscp=opts.dscp)
new  = DeviceV2IPDetails(None, None, None, None, tx_rate=opts2.tx_rate, scaling=None, dscp=opts2.dscp)
merged = new.merge(prev)
assert merged.tx_rate == 50, merged.tx_rate
assert merged.dscp.audio == 16
# a real rate-only write does replace it
rate_only = DeviceV2IPDetails(None, None, None, None, tx_rate=80, scaling=None, dscp=opts2.dscp)
assert rate_only.merge(prev).tx_rate == 80
print('merge ok  : rate', merged.tx_rate, 'dscp', merged.dscp)

# --- mxr_signal_type: bpp is an index, not a bit depth
st = MxrSignalType(bytes([16, (2 << 5) | (1 << 4) | 1]))
assert (st.svd, st.color, st.non_int, st.bpp_index, st.bpp) == (16, 1, True, 2, 10)
assert MxrSignalType(bytes([0, (5 << 5)])).is_set is False
assert mxr_sig_bpp_get(5) == 0 and mxr_sig_bpp_get(0) == 0
print('sigtype ok:', st)
assert v2ip_rate_valid(5) and v2ip_rate_valid(100) and not v2ip_rate_valid(4) and not v2ip_rate_valid(101)
print('ALL OK')
