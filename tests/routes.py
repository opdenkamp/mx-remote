######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''What a OneIP output is routed to, as the frames a unit acts on move it.

Two sources with distinct stream addresses and one sink, so a route that lands
on the wrong source shows. Every route frame comes from a management client,
which every firmware takes routing from, unless the sender is the subject.
'''

import asyncio, os, struct, sys, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import BayFeaturesMask, DeviceFeature, MxrDeviceUid
from mx_remote.proto.Factory import create_mxr_frame

ADDR = ('192.0.2.9', 8812)

class Watching(mx_remote.MxrCallbacks):
    def __init__(self):
        self.video, self.audio = [], []
    def on_video_source_changed(self, bay, video_source):
        self.video.append(video_source)
    def on_audio_source_changed(self, bay, audio_source):
        self.audio.append(audio_source)

seen = Watching()
mx = mx_remote.Remote(open_connection=False, callbacks=seen)
mx._uid = bytes(range(0x20, 0x30))
sent = []
mx.transmit = lambda data: (sent.append(bytes(data)), len(data))[1]

def call(coro):
    return asyncio.run(coro)

def uid(n):
    return bytes([n]) * 16

def nm(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def ip4(s):
    return bytes(int(x) for x in s.split('.'))

def rx(sender, opcode, payload=b'', protocol=0x28):
    frame = bytearray(create_mxr_frame(sender, opcode, payload))
    frame[2] = protocol
    mx.process_frame(time.time(), bytes(frame), ADDR)

def hello(sender, protocol, features, model='ONEIP'):
    rx(sender, 0x00, struct.pack('<H', protocol) + nm(model) + nm('P8SN%08d' % sender[0])
                   + nm('5.0.0') + struct.pack('<I', int(features)), protocol=0x01)
    return mx.get_by_uid(MxrDeviceUid(sender))

def bay_rec(port, mode, num, name, feat):
    return bytes([port, mode, num, 0, 0]) + nm(name) + nm(name) + nm('1080p') \
         + struct.pack('<II', 0, feat)

SRC_LOCAL = int(BayFeaturesMask.ONEIP_SOURCE_LOCAL)
SINK_LOCAL = int(BayFeaturesMask.ONEIP_SINK_LOCAL)

def source(n, video, audio):
    dev = hello(uid(n), 0x28, DeviceFeature.ONEIP_SOURCE | DeviceFeature.VIDEO_ROUTING)
    rx(uid(n), 0x02, bay_rec(0, 0, 0, f'Source {n}', SRC_LOCAL))
    rx(uid(n), 0x26, uid(n) + b''.join(ip4(ip) + struct.pack('<H', port) + bytes(2)
                                       for ip, port in ((video, 50020), (audio, 50022), ('239.9.9.9', 50021))))
    return dev.get_by_portnum(0)

def sink(n, protocol=0x28):
    dev = hello(uid(n), protocol, DeviceFeature.ONEIP_SINK | DeviceFeature.VIDEO_ROUTING)
    rx(uid(n), 0x02, bay_rec(16, 1, 0, f'Output {n}', SINK_LOCAL))
    return dev.get_by_portnum(16)

A = source(0x01, '239.1.1.1', '239.1.1.2')
B = source(0x02, '239.2.2.1', '239.2.2.2')
out = sink(0x10)
MANAGER = uid(0x40)
hello(MANAGER, 0x2F, DeviceFeature.MANAGER, model='MXR Python')

def switch(target, video, audio, sender=MANAGER):
    rx(sender, 0x1F, target + ip4(video) + ip4(audio))

# --------------------------------------------- audio follows video on a switch
# A switch naming no audio has the sink take its audio from its video again,
# so routing video drops a separate audio route.
switch(uid(0x10), '239.1.1.1', '239.2.2.2')
assert (out.video_source, out.audio_source) == (A, B), (out.video_source, out.audio_source)
seen.video.clear(); seen.audio.clear()
switch(uid(0x10), '239.1.1.1', '0.0.0.0')
assert out.video_source is A, out.video_source
assert out.audio_source is A, 'the separate audio route outlived a switch naming no audio'
assert seen.video == [], 'a video route that did not move was reported: %s' % seen.video
assert seen.audio == [A], 'the audio rejoining the video was not reported: %s' % seen.audio

# Audio that follows the video moves with it, and is reported as moving.
seen.audio.clear()
switch(uid(0x10), '239.2.2.1', '0.0.0.0')
assert out.audio_source is B and seen.audio == [B], seen.audio
switch(uid(0x10), '239.1.1.1', '0.0.0.0')

# A video of 0.0.0.0 keeps the video where it is.
switch(uid(0x10), '0.0.0.0', '239.2.2.2')
assert (out.video_source, out.audio_source) == (A, B), (out.video_source, out.audio_source)
print('switch      : no audio address has the audio follow the video again')

# ---------------------------------------------------- the output shows nothing
# A routing change naming video port 0xFFFE is an output showing nothing, which
# clears its video source and raises the change.
seen.video.clear()
rx(uid(0x10), 0x08, struct.pack('<HHH', 16, 0xFFFE, 0xFFFE) + bytes([0]) + struct.pack('<H', 0xFFFE))
assert out.video_source is None, out.video_source
assert seen.video == [None], seen.video
print('routing     : video port 0xFFFE clears the video source')

# ----------------------------------------------- what this client asks for
# From 0x27 a video route names no audio, so the audio follows it. Below 0x27
# some firmware routes no audio for that, so the source's audio is named.
for protocol, audio in ((0x28, bytes(4)), (0x27, bytes(4)), (0x26, ip4('239.1.1.2'))):
    old = sink(0x10 + protocol, protocol)
    sent.clear()
    # route by the port of a source this sink lists
    rx(uid(0x10 + protocol), 0x02, bay_rec(0, 0, 0, 'Source', SRC_LOCAL))
    rx(uid(0x10 + protocol), 0x26, uid(0x10 + protocol) + ip4('239.1.1.1') + struct.pack('<H', 50020) + bytes(2)
                                   + ip4('239.1.1.2') + struct.pack('<H', 50022) + bytes(2)
                                   + ip4('239.9.9.9') + struct.pack('<H', 50021) + bytes(2))
    assert call(old.select_video_source(0)) is True, hex(protocol)
    p = sent[-1][24:]
    assert p[16:20] == ip4('239.1.1.1'), p.hex()
    assert p[20:24] == audio, f'{protocol:#x}: audio {p[20:24].hex()}'
print('select      : below 0x27 the source\'s audio is named, from it none')

print('ALL OK')
