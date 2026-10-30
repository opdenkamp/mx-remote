######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Routing and unrouting a OneIP output unit as a mesh controller does.

A controller names a source unit's own stream addresses in the 0x1F switch,
so the output plays them whether or not it lists the source. None of the
units here lists another, so a route through the output's listing could not
name the source at all.

The layout asserted is the firmware-verified one the Rust crate pins:
mxr_v2ip_switch_data (the sink uid, the video and the audio group) followed
by mxr_v2ip_switch_options, one power-on byte padded to 8.

Every refusal sits next to a route that goes out, and each refused case is
built so that, without the check refusing it, the route would be sent.
'''

import asyncio, os, struct, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import DeviceFeature, MxrDeviceUid
from mx_remote.proto.Constants import BayFeaturesMask as F
from mx_remote.proto.Factory import create_mxr_frame

ADDR = ('192.0.2.9', 8812)
HDR = 24

mx = mx_remote.Remote(open_connection=False)
mx._uid = bytes(range(0x20, 0x30))
sent = []
mx.transmit = lambda data, to=None: (sent.append(bytes(data)), len(data))[1]

def call(coro):
    return asyncio.run(coro)

def uid(n):
    return bytes([n]) * 16

def nm(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def ip4(s):
    return bytes(int(x) for x in s.split('.'))

def rx(sender, opcode, payload=b'', protocol=0x2F):
    frame = bytearray(create_mxr_frame(sender, opcode, payload))
    frame[2] = protocol
    mx.process_frame(0.0, bytes(frame), ADDR)

def hello(n, protocol, features):
    rx(uid(n), 0x00, struct.pack('<H', protocol) + nm('ONEIP') + nm('P8SN%08d' % n)
                     + nm('5.0.0') + struct.pack('<I', int(features)), protocol=0x01)
    return mx.get_by_uid(MxrDeviceUid(uid(n)))

def rec(port, mode, num, name, features):
    return bytes([port, mode, num, 0, 0]) + nm(name) + nm(name) + nm('1080p') + struct.pack('<II', 0, int(features))

def streams(n, video, audio, anc):
    '''A 0x26 record: the owner's uid, then video, audio and anc, each an
    address, a port and two bytes of padding.'''
    return uid(n) + b''.join(ip4(ip) + struct.pack('<H', port) + bytes(2)
                             for ip, port in ((video, 50020), (audio, 50022), (anc, 50021)))

def unit(n, protocol=0x2F):
    '''A OneIP transceiver: its own input on port 0 and output on 16, the
    input's streams in groups that name the unit: 239.7.n.1 video,
    239.7.n.2 audio.'''
    dev = hello(n, protocol, DeviceFeature.ONEIP_SOURCE | DeviceFeature.ONEIP_SINK)
    rx(uid(n), 0x02, rec(0, 0, 0, 'Input 1', F.HDMI_IN | F.ONEIP_SOURCE_LOCAL)
                     + rec(16, 1, 0, 'Output 1', F.HDMI_OUT | F.ONEIP_SINK_LOCAL), protocol=protocol)
    rx(uid(n), 0x26, streams(n, f'239.7.{n}.1', f'239.7.{n}.2', f'239.7.{n}.3'), protocol=protocol)
    return dev

def cfg(n, arc):
    '''A 0x3C device configuration from unit n with the given audio return
    group on the port after the audio one; addresses are the unit's own.'''
    av = b''.join(ip4(ip) + struct.pack('<H', port) + bytes(2)
                  for ip, port in ((f'239.7.{n}.1', 50020), (f'239.7.{n}.2', 50022), (f'239.7.{n}.3', 50021)))
    out = (uid(n) + av + bytes([60, 0, 0, 0]) + bytes(4)
           + ip4(arc) + struct.pack('<H', 50023 if arc != '0.0.0.0' else 0) + bytes(2)
           + bytes(8) + bytes(24))
    assert len(out) == 88, len(out)
    rx(uid(n), 0x3C, out)

def sent_payload(what, coro):
    sent.clear()
    assert call(coro) is True, f'{what}: refused'
    assert len(sent) == 1, f'{what}: {len(sent)} frames sent'
    f = sent[0]
    assert int.from_bytes(f[20:22], 'little') == 0x1F, f'{what}: opcode {f[20:22].hex()}'
    return f[HDR:]

def refused(what, coro):
    sent.clear()
    assert call(coro) is False, f'{what}: accepted'
    assert sent == [], f'{what}: a refused route was sent'

sink, video, audio = unit(0xB6), unit(0xB7), unit(0xB8)
older = unit(0xB9, protocol=0x1E)

# ------------------------------------------------------------------- routes
p = sent_payload('video', sink.route_oneip_unit(video))
assert p[:16] == uid(0xB6), 'not addressed to the sink'
assert p[16:20] == bytes([239, 7, 0xB7, 1]), p[16:20]
assert p[20:24] == bytes(4), 'the audio does not follow the video'
assert p[24:] == bytes([1, 0, 0, 0, 0, 0, 0, 0]), f'no power-on options: {p[24:].hex()}'

p = sent_payload('video and audio', sink.route_oneip_unit(video, audio=audio))
assert p[16:20] == bytes([239, 7, 0xB7, 1]), p[16:20]
assert p[20:24] == bytes([239, 7, 0xB8, 2]), "not the audio unit's audio"

p = sent_payload('no power-on', sink.route_oneip_unit(video, power_on=False))
assert p[24:] == bytes(8), 'the display was powered on'

# Firmware up to 4.4.4 routes no audio for a switch naming none, so a unit
# below 0x27 is told the source's own audio, as Bay.select_video_source does.
p = sent_payload('older sink', older.route_oneip_unit(video))
assert p[20:24] == bytes([239, 7, 0xB7, 2]), 'an older unit was not told the audio'
print('route       : the source unit\'s own streams, the audio from it, another unit or the video')

# ----------------------------------------------------------------- unroute
p = sent_payload('unroute', sink.unroute_oneip_unit())
assert p[:16] == uid(0xB6), 'not addressed to the sink'
assert p[16:24] == bytes(8), 'a stream was named'
assert p[24:] == bytes([1, 0, 0, 0, 0, 0, 0, 0]), f'no power-on options: {p[24:].hex()}'
print('unroute     : names no streams')

# ---------------------------------------------------------------- refusals
# A unit with an input of its own that has not reported its streams.
silent = hello(0xC3, 0x2F, DeviceFeature.ONEIP_SOURCE)
rx(uid(0xC3), 0x02, rec(0, 0, 0, 'Input 1', F.HDMI_IN | F.ONEIP_SOURCE_LOCAL))
refused('no streams', sink.route_oneip_unit(silent))
refused('no streams for the audio', sink.route_oneip_unit(video, audio=silent))

# A matrix with an output of its own, which a OneIP switch cannot address.
matrix = hello(0xC4, 0x2F, DeviceFeature.VIDEO_ROUTING)
rx(uid(0xC4), 0x02, rec(16, 1, 0, 'Output 1', F.HDMI_OUT))
refused('not a sink', matrix.route_oneip_unit(video))
refused('not a sink: unroute', matrix.unroute_oneip_unit())

# An output-only unit whose one input is a mesh bay standing for another
# unit: it reports streams for that input, but they are the other unit's.
lister = hello(0xC5, 0x2F, DeviceFeature.ONEIP_SINK)
rx(uid(0xC5), 0x02, rec(16, 1, 0, 'Output 1', F.HDMI_OUT | F.ONEIP_SINK_LOCAL))
rx(uid(0xC5), 0x44, struct.pack('<HH', (1 << 1) | 1, 1) + bytes([0xA5] * 4) + uid(0xB7))
rx(uid(0xC5), 0x26, streams(0xB7, '239.7.183.1', '239.7.183.2', '239.7.183.3'))
assert lister.first_input is not None and not lister.first_input.is_local, lister.first_input
assert lister.oneip_source(lister.first_input) is not None, 'the mesh input reported no streams'
refused('only a mesh input', sink.route_oneip_unit(lister))
refused('only a mesh input for the audio', sink.route_oneip_unit(video, audio=lister))
refused('only a mesh input with an audio return', sink.route_oneip_unit_with_arc(lister, video))
print('refused     : an output that is not OneIP, a source with no streams or no input of its own')

# -------------------------------------------------------------- audio return
# The audio is the audio return group another unit's output last reported.
arc = unit(0xD8)
refused('before the output reported its audio return', sink.route_oneip_unit_with_arc(video, arc))
cfg(0xD8, '0.0.0.0')
assert arc.oneip_details is not None, 'the configuration was not taken'
refused('an audio return group that is not one', sink.route_oneip_unit_with_arc(video, arc))
cfg(0xD8, '239.9.8.7')
p = sent_payload('audio return', sink.route_oneip_unit_with_arc(video, arc, power_on=False))
assert p[:16] == uid(0xB6), 'not addressed to the sink'
assert p[16:20] == bytes([239, 7, 0xB7, 1]), "not the source unit's video"
assert p[20:24] == bytes([239, 9, 8, 7]), "not the output's audio return"
assert p[24:] == bytes(8), 'the display was powered on'
p = sent_payload('audio return, power on', sink.route_oneip_unit_with_arc(video, arc))
assert p[24] == 1, 'the display was not powered on'
refused('not a sink: audio return', matrix.route_oneip_unit_with_arc(video, arc))
refused('no streams: audio return', sink.route_oneip_unit_with_arc(silent, arc))
print('arc         : the audio return group an output last reported')

print('ALL OK')
