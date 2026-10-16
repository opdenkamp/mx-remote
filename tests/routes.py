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

# Audio port 0xFFFE is audio following the video, which drops a separate audio
# source; 0xFFFF is no port, and leaves both where they are.
def routing(video, audio):
    rx(uid(0x10), 0x08, struct.pack('<HHH', 16, video, video) + bytes([0]) + struct.pack('<H', audio))

switch(uid(0x10), '239.1.1.1', '239.2.2.2')
assert (out.video_source, out.audio_source) == (A, B), (out.video_source, out.audio_source)
seen.video.clear(); seen.audio.clear()
routing(0xFFFF, 0xFFFF)
assert (out.video_source, out.audio_source) == (A, B), 'port 0xFFFF moved the route'
assert (seen.video, seen.audio) == ([], []), (seen.video, seen.audio)
routing(0xFFFF, 0xFFFE)
assert out.video_source is A, out.video_source
assert out.audio_source is A, 'a separate audio source outlived audio port 0xFFFE'
assert seen.audio == [A], 'the audio rejoining the video was not reported: %s' % seen.audio
print('routing     : audio port 0xFFFE has the audio follow the video, 0xFFFF leaves it')

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

# --------------------------------------------- a OneIP output takes a volume
DIG_OUT = int(BayFeaturesMask.AUDIO_DIG_OUT)
vol = hello(uid(0x19), 0x2F, DeviceFeature.ONEIP_SINK | DeviceFeature.VOLUME_CONTROL)
rx(uid(0x19), 0x02, bay_rec(16, 1, 0, 'Output', SINK_LOCAL | DIG_OUT))
vout = vol.get_by_portnum(16)
sent.clear()
assert vout.volume_set(40) is True, 'a OneIP output refused a volume'
assert int.from_bytes(sent[-1][20:22], 'little') == 0x14 and sent[-1][24 + 18] == 40, sent[-1].hex()
print('volume      : a OneIP output, with its digital audio output, takes a volume')

# ------------------------------------------------- only from management
# Current firmware takes routing and hide only from management: a sender
# announcing MANAGER, or the controller the unit follows. MESH_MASTER stands in
# for that controller only until the unit has said whom it follows.
cur = sink(0x18, 0x2F)
switch(uid(0x18), '239.1.1.1', '0.0.0.0')
assert cur.video_source is A
peer = uid(0x42)
hello(peer, 0x2F, DeviceFeature.ONEIP_SINK)
switch(uid(0x18), '239.2.2.1', '0.0.0.0', sender=peer)
assert cur.video_source is A, 'a peer routed a current unit'
CTRL, OTHER = uid(0x43), uid(0x44)
hello(CTRL, 0x2F, DeviceFeature.MESH_MASTER | DeviceFeature.VIDEO_ROUTING)
hello(OTHER, 0x2F, DeviceFeature.MESH_MASTER | DeviceFeature.VIDEO_ROUTING)
switch(uid(0x18), '239.2.2.1', '0.0.0.0', sender=OTHER)
assert cur.video_source is B, 'a controller was not taken while the unit had named none'
from mx_remote.proto.FrameMeshOperation import MeshOperation
rx(uid(0x18), 0x3B, bytes([MeshOperation.REPORT_MEMBERSHIP.value, 0, 0, 0]) + CTRL + bytes(20))
switch(uid(0x18), '239.1.1.1', '0.0.0.0', sender=OTHER)
assert cur.video_source is B, 'a controller the unit does not follow routed it'
switch(uid(0x18), '239.1.1.1', '0.0.0.0', sender=CTRL)
assert cur.video_source is A, 'the controller the unit follows was not taken'

# A hide is taken at 24 bytes and a manual switch at 40, from management.
hide = uid(0x18) + struct.pack('<H', 16) + bytes([1])
rx(MANAGER, 0x27, hide)
assert not cur.hidden, 'a hide short of its padding was taken'
rx(peer, 0x27, hide + bytes(5))
assert not cur.hidden, 'a peer hid a current unit\'s bay'
rx(MANAGER, 0x27, hide + bytes(5))
assert cur.hidden
manual = uid(0x18) + b''.join(ip4(ip) + struct.pack('<HH', port, 0) for ip, port in
                              (('239.2.2.1', 50020), ('239.2.2.2', 50022), ('0.0.0.0', 0)))
rx(MANAGER, 0x24, manual[:38])
assert cur.video_source is A, 'a manual switch short of 40 bytes was taken'
rx(peer, 0x24, manual)
assert cur.video_source is A, 'a peer\'s manual switch was taken'
rx(MANAGER, 0x24, manual)
assert cur.video_source is B
print('management  : routing and hide only from MANAGER or the followed controller, at their lengths')

# ------------------------------------------------- mirror and filter frames
# Both name their sink in the first 16 bytes, and a unit takes them from the
# sink's own unit or from management - not from whoever sent them.
# A sink on current firmware takes them only from management.
STRANGER = uid(0x41)
hello(STRANGER, 0x28, DeviceFeature.ONEIP_SINK)
mout = sink(0x1A, 0x2F)
rx(STRANGER, 0x32, uid(0x1A) + uid(0x01))
assert not (mout.mirroring and mout.mirroring.is_mirroring), 'a third party set the mirror'
rx(MANAGER, 0x32, uid(0x1A) + uid(0x01))
assert mout.mirroring.is_mirroring and mout.mirroring.target.device == MxrDeviceUid(uid(0x01)), mout.mirroring
rx(uid(0x1A), 0x32, uid(0x1A) + bytes([0xFF] * 16))
assert not mout.mirroring.is_mirroring, 'a mirror of all 0xFF is no mirror'
rx(MANAGER, 0x32, uid(0x1A) + uid(0x01) + bytes(8))
assert not mout.mirroring.is_mirroring, 'a mirror at a length a unit drops was taken'
print('mirror      : filed under the sink it names, all 0xFF is none, only at 32 bytes')

rx(MANAGER, 0x38, uid(0x1A) + uid(0x01) + uid(0x02))
assert mout.filtered is not None and len(mout.filtered) == 2, mout.filtered
manager = mx.get_by_uid(MxrDeviceUid(MANAGER))
assert manager.first_output is None, 'fixture: the manager has no output to misfile on'
rx(MANAGER, 0x38, uid(0x1A) + uid(0x01) + bytes(4))
assert len(mout.filtered) == 2, 'a list of no whole number of uids was taken'
rx(STRANGER, 0x38, uid(0x1A))
assert len(mout.filtered) == 2, 'a third party set the list'
print('filter      : filed under the sink it names, whole uids only')

# --------------------------------------- released firmware takes them from anyone
# Below 0x2F a unit applies routing, hide, mirror and filter from any sender.
switch(uid(0x10), '239.2.2.1', '0.0.0.0', sender=STRANGER)
assert out.video_source is B, "a released unit's route from a peer was dropped"
rx(STRANGER, 0x27, uid(0x10) + struct.pack('<H', 16) + bytes([1]) + bytes(5))
assert out.hidden, "a released unit's hide from a peer was dropped"
rx(STRANGER, 0x32, uid(0x10) + uid(0x02))
assert out.mirroring.is_mirroring, "a released unit's mirror from a peer was dropped"
rx(STRANGER, 0x38, uid(0x10) + uid(0x01))
assert len(out.filtered) == 1, "a released unit's filter from a peer was dropped"
print('released    : below 0x2F routing, hide, mirror and filter come from anyone')

print('ALL OK')
