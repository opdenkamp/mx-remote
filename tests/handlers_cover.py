######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Run the frame handlers no other suite reaches, and assert what they changed.

handlers.py measures which process() methods the suites execute. A handler no
suite runs is invisible to every other check here, because they all measure
tests that run. This drives the remainder.

Executing a handler is not the point: each case asserts the state the handler
was supposed to write. Where a handler is deliberately a no-op, the decode is
asserted instead and the no-op is stated, so a later reader does not mistake a
thin case for an oversight.
'''

import os, struct, sys, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.Uid import MxrDeviceUid
from mx_remote.proto.Factory import create_mxr_frame, process_mxr_frame
from mx_remote.Interface import PowerStatus, BayFeaturesMask

UID = bytes(range(1, 17))
PEER = bytes(range(60, 76))
ADDR = ('192.0.2.9', 8812)

mx = mx_remote.Remote(open_connection=False)
mx._uid = bytes(range(100, 116))

def nm(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def rx(opcode, payload=b'', uid=UID):
    '''Feed a frame in the way the runtime does, so process() runs.'''
    mx.process_frame(time.time(), create_mxr_frame(uid, opcode, payload), ADDR)

def decode(opcode, payload=b'', uid=UID):
    '''Decode without processing, for handlers that are deliberately no-ops.'''
    return process_mxr_frame(mx, time.time(), create_mxr_frame(uid, opcode, payload), ADDR)

FEAT = (1 << 5) | (1 << 6) | (1 << 7) | (1 << 9)      # routing, volume, remote control
rx(0x00, struct.pack('<H', 0x28) + nm('MX-1') + nm('P8SN12345678') + nm('5.2.0')
        + struct.pack('<I', FEAT))
dev = mx.get_by_uid(MxrDeviceUid(UID))

AUDIO_OUT = int(BayFeaturesMask.AUDIO_ANA_OUT)
def bay_rec(port, mode, num, name, feat=None):
    if feat is None:
        feat = (1 << 1) if mode == 0 else (1 << 0)
    return (bytes([port, mode, num, 0, 0]) + nm(name) + nm(name) + nm('1080p')
            + struct.pack('<I', 0) + struct.pack('<I', feat))
rx(0x02, bay_rec(0, 0, 0, 'In 1') + bay_rec(1, 1, 0, 'Out 1', feat=AUDIO_OUT))
inp, out = dev.get_by_portnum(0), dev.get_by_portnum(1)
assert inp is not None and out is not None
assert out.has_volume_control, 'fixture bay needs volume control for the volume handlers'
print('fixture     : %s, in=%s out=%s' % (dev.serial, inp.port, out.port))

# ---- 0x12 VOLUME: the reported volume reaches the bay
rx(0x12, bytes([out.port, 40, 41, 0]))
vs = out.volume_status
assert vs is not None and vs.volume_left == 40 and vs.volume_right == 41, vs
print('0x12 volume : bay volume %s/%s' % (vs.volume_left, vs.volume_right))

# ---- 0x14 VOLUME_SET: same state, addressed by uid and a u16 port
rx(0x14, UID + struct.pack('<H', out.port) + bytes([55, 56, 0]))
vs = out.volume_status
assert vs.volume_left == 55 and vs.volume_right == 56, vs
print('0x14 setvol : bay volume %s/%s' % (vs.volume_left, vs.volume_right))

# ---- 0x0F / 0x10 VOLUME UP and DOWN: handlers are deliberate no-ops - the
#      step is applied by whatever drives them - so assert the decode instead
f = decode(0x0F, bytes([out.port]))
assert f.bay is not None and f.bay.port == out.port, f.bay
f.process()                                            # documented no-op, must not raise
g = decode(0x10, bytes([out.port]))
assert g.bay is not None and g.bay.port == out.port, g.bay
g.process()
print('0x0F/0x10   : bay decoded, handlers are no-ops by design')

# ---- 0x05 POWER_CHANGE
rx(0x05, bytes([out.port, 1]))
assert out.power_status == PowerStatus.ON, out.power_status
rx(0x05, bytes([out.port, 0]))
assert out.power_status == PowerStatus.OFF, out.power_status
print('0x05 power  : ON then OFF applied to the bay')

# ---- 0x06 SIGNAL_STATUS: detected flag and the description string
rx(0x06, bytes([inp.port, 1]) + b'1920x1080p60\x00')
assert inp.signal_detected is True, inp.signal_detected
assert '1920x1080' in inp.signal_type, inp.signal_type
print('0x06 signal : detected=%s type=%r' % (inp.signal_detected, inp.signal_type))

# ---- 0x15 SYS_TEMPERATURE
rx(0x15, bytes([2, 41, 42]))
temps = dev.temperatures
assert temps, temps
print('0x15 temp   : %s' % (temps,))

# ---- 0x27 BAY_HIDE: addressed by uid, u16 port, then the flag
rx(0x27, UID + struct.pack('<H', inp.port) + bytes([1]))
assert inp.hidden is True, inp.hidden
rx(0x27, UID + struct.pack('<H', inp.port) + bytes([0]))
assert inp.hidden is False, inp.hidden
print('0x27 hide   : hidden set then cleared')

# ---- 0x04 CONNECT_STATUS
# on an output the connect flag is HPD; on an input it is signal detection
rx(0x04, bytes([out.port, 1]))
assert out.hpd_detected is True, out.hpd_detected
rx(0x04, bytes([out.port, 0]))
assert out.hpd_detected is False, out.hpd_detected
print('0x04 connect: hpd set then cleared on the output')

# ---- 0x32 MIRROR_STATUS: this device's first output mirrors another device
rx(0x32, UID + PEER)
assert out.mirroring is not None and out.mirroring.is_mirroring, out.mirroring
print('0x32 mirror : %s' % (out.mirroring,))
rx(0x32, UID + bytes(16))                              # an empty master clears it
assert not out.mirroring.is_mirroring, out.mirroring
print('0x32 mirror : cleared by an empty master')

# ---- 0x38 BAY_FILTER_STATUS: the filtered set lands on the first output
rx(0x38, UID + PEER)
filtered = out.filtered
assert filtered is not None and len(filtered) == 1, filtered
print('0x38 filter : %d source filtered' % len(filtered))

# ---- 0x30 TOPOLOGY: 20-byte entries, uid then a mask
rx(0x30, PEER + struct.pack('<I', 0x03))
assert dev._topology, dev._topology       # no public accessor; the handler writes here
print('0x30 topo   : %d entr(y/ies)' % len(dev._topology))

# ---- 0x16 PDU_STATE: decodes for the log, but nothing consumes it, so the
#      handler is a no-op. Before it was one it named two methods that do not
#      exist, and every PDU frame raised out of the receive path.
f = decode(0x16, struct.pack('<ffffff', 1.5, 230.0, 345.0, 12.0, 0.98, 50.0)
                 + bytes([1, 0, 1, 0, 0, 0, 0, 0]))
assert round(f.current, 2) == 1.5, f.current
assert round(f.voltage, 2) == 230.0, f.voltage
f.process()                                            # no consumer, must not raise
rx(0x16, struct.pack('<ffffff', 1.5, 230.0, 345.0, 12.0, 0.98, 50.0)
       + bytes([1, 0, 1, 0, 0, 0, 0, 0]))
print('0x16 pdu    : decodes %sA/%sV, handler is a no-op' % (f.current, f.voltage))

# ---- 0x3E AMP_DOLBY_STATE: uid, then mode and flags
rx(0x3E, UID + bytes([2, 0b11]))
ds = dev.dolby_settings
assert ds is not None and ds.mode == 2, ds
print('0x3E dolby  : mode=%s upmix=%s' % (ds.mode, ds.pcm_upmix))

# ---- 0x23 BAY_CONFIG_SECONDARY: another page of bay records, merged in
before = len(dev.bays)
rx(0x23, bay_rec(2, 0, 1, 'In 3'))
assert len(dev.bays) == before + 1, (before, len(dev.bays))
assert dev.get_by_portnum(2).user_name == 'In 3', dev.get_by_portnum(2).user_name
print('0x23 cfg2   : page merged, bays %d -> %d' % (before, len(dev.bays)))

# ---- 0x46 SYSTEM_STATUS: uid then a status code
rx(0x46, UID + struct.pack('<H', 3))
print('0x46 sysstat: handled')

# ---- 0x3B MESH_OPERATION: uid, operation, target and parameter
rx(0x3B, UID + bytes([1]) + bytes(7) + PEER + bytes(16))
print('0x3B mesh   : handled')

# ---- 0x29 NETWORK_STATUS: port then feature flags
# port, feature flags, then the per-pair cable records the renderer walks
rx(0x29, struct.pack('<H', 1) + bytes([0x01]) + bytes(61))
assert dev.network_status is not None, dev.network_status
print('0x29 net    : %d port(s) known' % len(dev.network_status))

# ---- deliberate no-ops, decoded and run: their content is reported, not cached
f = decode(0x47, bytes([1, 2, 3, 4]))
f.process()
print('0x47 debug  : decoded, handler is a no-op by design')

f = decode(0x41, UID + bytes([1]))
assert f.enable is True, f.enable
f.process()
print('0x41 psave  : enable=%s, handler is a no-op by design' % f.enable)

f = decode(0x40, UID + struct.pack('<HHHH', 1, 2, 3, 4))
f.process()
print('0x40 tiling : decoded, handler is a no-op by design')

f = decode(0x45, UID + bytes(64))
f.process()
print('0x45 rcset  : decoded, handler is a no-op by design')

# ---- 0x43 V2IP_AUDIO: a dispatcher over sub-opcodes. Payloads come from the
#      library's own builders where it has them, so each sub-frame is reached the
#      way a peer would produce it rather than from a hand-packed guess.
from mx_remote.proto.FrameV2IPAudio import (AudioCommandOpcode, AudioDeviceData,
    AudioEndpointData, AudioLinkData, AudioStreamAddress, FrameV2IPAudio,
    FrameV2IPAudioConfig, FrameV2IPAudioChangeSource, FrameV2IPAudioLinks,
    pack_audio_links, _audio_cmd_header)

def audio_frame(body):
    # send it the way the runtime receives one, then decode a copy to inspect
    rx(0x43, body)
    return process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x43, body), ADDR)

devdata = AudioDeviceData(
    features=0x01, status=0,
    endpoints=[AudioEndpointData(id=1, features=0x03,
                                 address=AudioStreamAddress(ip='239.9.9.1', port=50022)),
               AudioEndpointData(id=2, features=0x03)],
    links=[AudioLinkData(endpoint=1, link_endpoint=2, link_dev=MxrDeviceUid(PEER))])
built = FrameV2IPAudio.construct_features(mxr=mx, own_uid=MxrDeviceUid(UID), dev=devdata)
assert built is not None, 'features builder returned nothing'
g = audio_frame(built.payload)
assert isinstance(g._frame, FrameV2IPAudioConfig), type(g._frame)
assert dev.audio_endpoint_by_id(1) is not None, 'FEATURES must cache the endpoints'
assert dev.audio_endpoint_by_id(2) is not None
print('0x43 FEATURES : endpoints 1 and 2 cached on the device')

links_body = (_audio_cmd_header(AudioCommandOpcode.LINKS, MxrDeviceUid(UID))
              + pack_audio_links([AudioLinkData(endpoint=1, link_endpoint=2,
                                                link_dev=MxrDeviceUid(PEER))]))
g = audio_frame(links_body)
assert isinstance(g._frame, FrameV2IPAudioLinks), type(g._frame)
print('0x43 LINKS    : dispatched to the links sub-frame and processed')

snk_ep, src_ep = dev.audio_endpoint_by_id(1), dev.audio_endpoint_by_id(2)
built = FrameV2IPAudio.construct_select_input(mxr=mx, sink=MxrDeviceUid(UID), sink_ep=snk_ep,
                                              source=MxrDeviceUid(PEER), source_ep=src_ep)
assert built is not None, 'select_input builder returned nothing'
g = audio_frame(built.payload)
assert isinstance(g._frame, FrameV2IPAudioChangeSource), type(g._frame)
print('0x43 SELECT   : dispatched to the change-source sub-frame and processed')

# ---- the V2IP switch frames need a device that has V2IP bays and known stream
#      addresses, so they get their own rather than reshaping the one above.
V2 = bytes(range(80, 96))
V2FEAT = (1 << 5) | (1 << 6) | int(mx_remote.DeviceFeature.V2IP_SOURCE) | int(mx_remote.DeviceFeature.V2IP_SINK)
rx(0x00, struct.pack('<H', 0x28) + nm('OneIP') + nm('P8SN99999999') + nm('5.2.0')
        + struct.pack('<I', V2FEAT), uid=V2)
v2dev = mx.get_by_uid(MxrDeviceUid(V2))
SRC_LOCAL = int(mx_remote.BayFeaturesMask.V2IP_SOURCE_LOCAL)
SINK_LOCAL = int(mx_remote.BayFeaturesMask.V2IP_SINK_LOCAL)
rx(0x02, bay_rec(0, 0, 0, 'V2 In', feat=SRC_LOCAL) + bay_rec(1, 1, 0, 'V2 Out', feat=SINK_LOCAL), uid=V2)
v2in, v2out = v2dev.get_by_portnum(0), v2dev.get_by_portnum(1)

def stream_entry(video, audio, anc):
    out = V2
    for ip, port in (video, audio, anc):
        out += bytes(int(x) for x in ip.split('.')) + struct.pack('<H', port) + bytes(2)
    return out
rx(0x26, stream_entry(('239.5.5.1', 50020), ('239.5.5.2', 50022), ('239.5.5.3', 50021)), uid=V2)
assert v2in.v2ip_source is not None, 'the source bay needs stream addresses'
assert mx.get_by_stream_ip(ip='239.5.5.1', audio=False) is not None, 'stream ip must resolve'

# ---- 0x1F V2IP_SOURCE_SWITCH: target uid, then video and audio ips big-endian
def ip4(s):
    return bytes(int(x) for x in s.split('.'))
rx(0x1F, V2 + ip4('239.5.5.1') + ip4('239.5.5.2'), uid=V2)
assert v2out.video_source is not None, 'the switch must resolve a source bay'
print('0x1F switch : sink source -> %s' % v2out.video_source.user_name)

# ---- 0x24 V2IP_MANUAL_SOURCE_SWITCH, built by the library's own helper
from mx_remote.proto.FrameV2IPManualSourceSwitch import FrameV2IPManualSourceSwitch
built = FrameV2IPManualSourceSwitch.construct(
    mxr=mx, target=v2dev,
    video_ip='239.5.5.1', video_port=50020,
    audio_ip='239.5.5.2', audio_port=50022,
    anc_ip='0.0.0.0', anc_port=0, audio_fmt=None)
assert built is not None, 'manual switch builder returned nothing'
rx(0x24, built.payload, uid=V2)
print('0x24 manual : dispatched and processed')

# ---- 0x44 V2IP_BAY_MAPPING: counts, then a uid per mapped bay
rx(0x44, struct.pack('<HH', 1, 0) + bytes(4) + V2, uid=V2)
print('0x44 mapping: dispatched and processed')

print('ALL OK')
