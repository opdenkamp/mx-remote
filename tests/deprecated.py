######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''The V2IP and FPGA names 5.11.0 exported still work, and nothing public is
spelled either way.

The lists below are the public V2IP and FPGA names as released in 5.11.0, written out
rather than read from mx_remote.deprecated, so dropping one from the aliases
fails here instead of agreeing with itself.
'''

import asyncio, enum, inspect, os, re, struct, sys, warnings, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
import mx_remote.Interface as Interface
import mx_remote.proto.Constants as Constants
from mx_remote.deprecated import oneip_name
from mx_remote.proto.Factory import create_mxr_frame
from mx_remote.remote.Remote import Remote

RELEASED_NAMES = (
    'DeviceV2IPDetails', 'DeviceV2IPScalingSettings', 'DeviceV2IPSink',
    'MXR_V2IP_DSCP_SET', 'V2IPAudioFormat', 'V2IPDeviceSetting', 'V2IPDeviceSettings',
    'V2IPDeviceStats', 'V2IPDscpConfig', 'V2IPFpgaFeature', 'V2IPOutputMode',
    'V2IPPowerSaveSchedule', 'V2IPScalingSettings', 'V2IPStreamSource',
    'V2IPStreamSources', 'V2IPStreamSourcesList', 'V2IP_AUDIO_DEFAULT_CHANNELS',
    'V2IP_AUDIO_DEFAULT_SAMPLE_RATE', 'V2IP_AUDIO_MAX_CHANNELS',
    'V2IP_AUDIO_MIN_CHANNELS', 'V2IP_DEVICE_SETTINGS_REPORTED_ONLY',
    'V2IP_DEVICE_SETTING_SWITCHES', 'V2IP_DSCP_DEFAULT', 'V2IP_DSCP_MAX',
    'V2IP_IR_PROFILE_MAX', 'V2IP_IR_PROFILE_NOT_SET', 'V2IP_MINUTES_PER_DAY',
    'V2IP_SCALING_REFRESH_MAX', 'V2IP_SCALING_REFRESH_MIN', 'V2IP_SOURCE_RATE_MAX',
    'V2IP_SOURCE_RATE_MIN', 'v2ip_av_source_valid', 'v2ip_dscp_value',
    'v2ip_rate_valid', 'v2ip_stream_cleared', 'v2ip_stream_valid',
)

RELEASED_MEMBERS = {
    'FirmwareType': (
        'FPGA',
    ),
    'AudioEndpoint': (
        'is_v2ip',
    ),
    'AudioFeatures': (
        'FEATURE_V2IP_TX', 'FEATURE_V2IP_RX', 'is_v2ip_tx', 'is_v2ip_rx',
    ),
    'BayBase': (
        'is_v2ip_remote', 'is_v2ip_source', 'is_v2ip_sink', 'v2ip_source', 'v2ip_uid',
        'v2ip_device',
    ),
    'BayFeaturesMask': (
        'V2IP_SOURCE_REMOTE', 'V2IP_SINK_REMOTE', 'V2IP_SOURCE_LOCAL',
        'V2IP_SINK_LOCAL',
    ),
    'DeviceBase': (
        'is_v2ip', 'v2ip_features', 'v2ip_sources', 'v2ip_stats', 'v2ip_details',
        'v2ip_sink', 'v2ip_settings', 'v2ip_source_local', 'is_v2ip_sink',
        'v2ip_firmware_versions', 'v2ip_source', 'merge_v2ip_sources',
        'set_v2ip_auto_scaling', 'set_v2ip_output_mode', 'clear_v2ip_output_mode',
        'set_v2ip_setting', 'set_v2ip_ir_profile', 'set_v2ip_sink_ir_profile',
        'set_v2ip_auto_power_save', 'set_v2ip_power_save_schedule',
    ),
    'DeviceFeature': (
        'V2IP_SOURCE', 'V2IP_SINK',
    ),
    'Remote': (
        'set_all_v2ip_device_settings',
    ),
}

def deprecated(fn, what):
    '''Call fn, which must raise exactly one DeprecationWarning naming the new
    spelling, and return its result.'''
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        rv = fn()
    dep = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(dep) == 1, f'{what}: {len(dep)} deprecation warnings'
    assert 'is deprecated, use' in str(dep[0].message), str(dep[0].message)
    assert dep[0].filename == __file__, f'{what}: the warning points at {dep[0].filename}'
    return rv

# ------------------------------------------------------------- module names

for old in RELEASED_NAMES:
    new = oneip_name(old)
    assert ('V2IP' not in new.upper()) and ('FPGA' not in new.upper()), new
    for module in (mx_remote, Interface):
        got = deprecated(lambda: getattr(module, old), f'{module.__name__}.{old}')
        assert got is getattr(mx_remote, new), f'{module.__name__}.{old} is not {new}'
    assert old not in vars(mx_remote), f'{old} is a real name, so it neither warns nor goes away'
# The import machinery looks a from-imported name up more than once, and each
# lookup warns.
exec_ns = {}
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter('always')
    exec('from mx_remote import V2IPDeviceSettings', exec_ns)
assert any(issubclass(w.category, DeprecationWarning) for w in caught), 'from-import did not warn'
assert exec_ns['V2IPDeviceSettings'] is mx_remote.OneIPDeviceSettings
deprecated(lambda: Constants.V2IP_DSCP_MAX, 'Constants.V2IP_DSCP_MAX')
try:
    mx_remote.V2IPNoSuchThing
    raise AssertionError('an unknown old-looking name resolved')
except AttributeError:
    pass
print('names       :', len(RELEASED_NAMES), 'module-level names resolve, each with a warning')

# ------------------------------------------------------------------ members

# Enum members and the AudioFeatures bit constants are plain aliases: an enum
# cannot warn on access, and a bit constant is read off the class.
from mx_remote.proto.Constants import FirmwareType
assert FirmwareType(1).name == 'VIDEO_PROCESSOR' and str(FirmwareType(1)) == 'Video Processor'
for cls in (mx_remote.DeviceFeature, mx_remote.BayFeaturesMask, FirmwareType):
    for old in RELEASED_MEMBERS[cls.__name__]:
        assert cls[old] is cls[oneip_name(old)], f'{cls.__name__}.{old}'
        assert oneip_name(old) in str(cls[old]) or cls[old].name == oneip_name(old), cls[old].name
for old in ('FEATURE_V2IP_TX', 'FEATURE_V2IP_RX'):
    assert getattr(mx_remote.AudioFeatures, old) == getattr(mx_remote.AudioFeatures, oneip_name(old))

# A live device, bay, remote and audio endpoint, so each alias is read off an
# instance the way a caller has one.
ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False)
mx._uid = bytes(range(0x20, 0x30))
UID = bytes([0x10]) * 16
def rx(opcode, payload, protocol=0x2B):
    frame = bytearray(create_mxr_frame(UID, opcode, payload))
    frame[2] = protocol
    mx.process_frame(0.0, bytes(frame), ADDR)
def name(s, sz=16):
    return s.encode('ascii').ljust(sz, b'\0')
rx(0x00, struct.pack('<H', 0x2B) + name('ONEIP') + name('P8SN12345678') + name('5.0.0')
         + struct.pack('<I', int(mx_remote.DeviceFeature.ONEIP_SINK)))
dev = mx.get_by_uid(mx_remote.MxrDeviceUid(UID))
bay_rec = (bytes([0, 0]) + name('Out').ljust(32, b'\0'))
from mx_remote.proto.FrameV2IPAudio import AudioDeviceData, AudioEndpointData, FrameV2IPAudio
built = FrameV2IPAudio.construct_features(mxr=mx, own_uid=dev.remote_id,
    dev=AudioDeviceData(features=0, status=0, endpoints=[AudioEndpointData(id=1, features=0x0A)]))
rx(0x43, built.payload, protocol=0x1A)
ep = dev.audio_endpoint_by_id(1)
assert ep is not None
instances = {'DeviceBase': dev, 'AudioEndpoint': ep, 'AudioFeatures': ep.features, 'Remote': mx}

def same(a, b):
    if inspect.ismethod(a) and inspect.ismethod(b):
        return (a.__func__ is b.__func__) and (a.__self__ is b.__self__)
    return (a is b) or (a == b)

for cls_name, olds in RELEASED_MEMBERS.items():
    if cls_name in ('DeviceFeature', 'BayFeaturesMask', 'FirmwareType'):
        continue
    if cls_name == 'BayBase':
        continue
    obj = instances[cls_name]
    for old in olds:
        if old.startswith('FEATURE_'):
            continue
        new = oneip_name(old)
        got = deprecated(lambda: getattr(obj, old), f'{cls_name}.{old}')
        assert same(got, getattr(obj, new)), f'{cls_name}.{old}: {got!r} is not {new}'

# A bay, including the one alias that is also written.
from mx_remote.remote.Bay import Bay
bay = next(iter(dev.bays.values()), None)
if bay is None:
    rx(0x02, bytes([1, 0, 0, 0]) + name('Out').ljust(32, b'\0') + bytes(64))
    bay = next(iter(dev.bays.values()), None)
assert bay is not None, 'no bay to read aliases from'
for old in RELEASED_MEMBERS['BayBase']:
    new = oneip_name(old)
    got = deprecated(lambda: getattr(bay, old), f'BayBase.{old}')
    assert same(got, getattr(bay, new)), f'BayBase.{old} is not {new}'
peer = mx_remote.MxrDeviceUid(bytes([0x44]) * 16)
deprecated(lambda: setattr(bay, 'v2ip_uid', peer), 'BayBase.v2ip_uid =')
assert bay.oneip_uid == peer, 'writing the old name did not write the new one'

# A method called by its old name runs the new one.
sent = []
mx.transmit = lambda data: (sent.append(data), len(data))[1]
fn = deprecated(lambda: dev.set_v2ip_output_mode, 'DeviceBase.set_v2ip_output_mode')
assert fn.__func__ is type(dev).set_oneip_output_mode
print('members     :', sum(map(len, RELEASED_MEMBERS.values())), 'members resolve on live objects')

# ------------------------------------------------------ nothing new is V2IP

# Every public name that is not one of the aliases above is spelled OneIP and
# VideoProcessor, so a name ported from the firmware or the Rust crate cannot
# slip in as V2IP or FPGA.
aliases = set(RELEASED_NAMES) | {m for ms in RELEASED_MEMBERS.values() for m in ms}
pat = re.compile('v2ip|fpga', re.I)
stray = [n for n in dir(mx_remote) if pat.search(n) and (n not in aliases)]
from mx_remote.remote.Device import Device
for cls in [getattr(mx_remote, n) for n in dir(mx_remote)] + [Device, Bay, Remote]:
    if inspect.isclass(cls) and getattr(cls, '__module__', '').startswith('mx_remote'):
        names = cls.__members__ if issubclass(cls, enum.Enum) else vars(cls)
        stray += [f'{cls.__name__}.{n}' for n in names
                  if pat.search(n) and not n.startswith('_') and (n not in aliases)]
assert not stray, f'public names spelled V2IP or FPGA: {sorted(set(stray))}'
print('no new V2IP : every other public name says OneIP, and VideoProcessor for FPGA')

print('ALL OK')
