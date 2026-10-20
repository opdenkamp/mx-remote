######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Overlay sync (0x53): watching one between units, and sending one.

Frames are composed from the layout with every field distinct, so a field read
at a neighbour's offset shows. The sender's side is driven through the same
entry points the runtime uses: process_frame for what arrives, _osd_pass for
the loop that answers it.
'''

import asyncio, os, struct, sys, time, logging, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import (DeviceFeature, MxrDeviceUid, OsdCaption, OsdLogo, OsdSyncContent, OsdSyncEntry,
                       OsdSyncImage, OsdSyncSlot)
from mx_remote.proto.Constants import (OSD_SYNC_RECORDS_MAX, OsdCaptionAlign, OsdCaptionFormat, OsdSyncSize,
                                       OsdSyncState, OsdSyncWhat as W)
from mx_remote.proto.Factory import create_mxr_frame
from mx_remote.proto.FrameV2IPOsdSync import osd_crc32

ADDR = ('192.0.2.9', 8812)
OURS = bytes(range(0x20, 0x30))

class Watching(mx_remote.MxrCallbacks):
    def __init__(self):
        self.requests, self.settings = [], []
    def on_osd_sync_requested(self, dev, request):
        self.requests.append((dev, request))
    def on_osd_sync_setting(self, dev, setting):
        self.settings.append(setting)

def uid(n):
    return bytes([n]) * 16

def nm(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def client():
    seen = Watching()
    mx = mx_remote.Remote(open_connection=False, callbacks=seen)
    mx._uid = OURS
    sent = []
    mx.transmit = lambda data: (sent.append(bytes(data)), len(data))[1]
    return mx, seen, sent

def rx(mx, sender, opcode, payload=b'', protocol=0x2F):
    frame = bytearray(create_mxr_frame(sender, opcode, payload))
    frame[2] = protocol
    mx.process_frame(time.time(), bytes(frame), ADDR)

def hello(mx, sender, features, protocol=0x2F):
    rx(mx, sender, 0x00, struct.pack('<H', protocol) + nm('ONEIP') + nm('P8SN%08d' % sender[0]) + nm('4.8.0')
                         + struct.pack('<I', int(features)), protocol=0x01)
    return mx.get_by_uid(MxrDeviceUid(sender))

def header(kind, seq, target):
    return bytes([2, kind]) + struct.pack('<H', seq) + target

def sync_frame(seq, target, what, records, slots=()):
    p = (header(0, seq, target) + bytes([int(what), 0xA5]) + struct.pack('<H', 0x1F90) + bytes([192, 0, 2, 7])
         + struct.pack('<H', records) + bytes([0xA5, 0xA5]))
    for i in range(4):
        p += struct.pack('<IIB3s', 0x01020300 + i, 0xC0DEF000 + i, 90 + i, b'\xa5\xa5\xa5')
    assert len(p) == 80
    return p

def request(target, seq, what, missing=b'', source=bytes(16)):
    return header(1, seq, target) + bytes([int(what), 0xA5]) + missing.ljust(16, b'\0') + source

def opcode(frame):
    return int.from_bytes(frame[20:22], 'little')

def kind(frame):
    return frame[24 + 1]

def u16(frame, at):
    return int.from_bytes(frame[24 + at:24 + at + 2], 'little')

UNIT, MGR, CTRL = uid(0x10), uid(0x40), uid(0x41)

# ------------------------------------------------------------------ watching
mx, seen, sent = client()
unit = hello(mx, UNIT, DeviceFeature.ONEIP_SINK | DeviceFeature.OSD_SYNC)
mgr = hello(mx, MGR, DeviceFeature.MANAGER)
peer = hello(mx, uid(0x11), DeviceFeature.ONEIP_SINK)

rx(mx, MGR, 0x53, sync_frame(0xA1B2, bytes(16), W.CAPTIONS | W.LOGO_SLOTS, 3))
s = mgr.osd_sync
assert (s.seq, s.target.empty, s.what, s.http_port, s.source_ip, s.records) == \
    (0xA1B2, True, W.CAPTIONS | W.LOGO_SLOTS, 0x1F90, '192.0.2.7', 3), s
assert s.slots[2] == OsdSyncSlot(0x01020302, 0xC0DEF002, 92), s.slots
rx(mx, MGR, 0x53, sync_frame(0xA1B3, bytes(16), W.CAPTIONS, 3))
assert mgr.osd_sync.slots is None, 'slots read from a sync that does not copy them'
print('sync        :', s.seq, s.what, s.slots[0])

# A sync no unit would take is not read: from a peer, of another version, short,
# or announcing more than 128 settings.
for sender, payload in ((uid(0x11), sync_frame(1, bytes(16), W.CAPTIONS, 3)),
                        (MGR, bytes([3]) + sync_frame(2, bytes(16), W.CAPTIONS, 3)[1:]),
                        (MGR, sync_frame(3, bytes(16), W.CAPTIONS, 3)[:79]),
                        (MGR, sync_frame(4, bytes(16), W.CAPTIONS, OSD_SYNC_RECORDS_MAX + 1))):
    rx(mx, sender, 0x53, payload)
assert mgr.osd_sync.seq == 0xA1B3 and peer.osd_sync is None, 'a sync no unit takes was read'
print('sync refused: from a peer, another version, short, or over 128 settings')

# A controller is management once a unit follows it, and only that one is.
from mx_remote.proto.FrameMeshOperation import MeshOperation
ctrl, other = hello(mx, CTRL, DeviceFeature.MESH_MASTER), hello(mx, uid(0x42), DeviceFeature.MESH_MASTER)
rx(mx, uid(0x42), 0x53, sync_frame(5, bytes(16), W.LOGO, 1))
assert other.osd_sync is not None, 'a controller was not taken while no unit names one'
rx(mx, UNIT, 0x3B, bytes([MeshOperation.REPORT_MEMBERSHIP.value, 0, 0, 0]) + CTRL + bytes(20), protocol=0x1D)
rx(mx, uid(0x42), 0x53, sync_frame(6, bytes(16), W.LOGO, 1))
assert other.osd_sync.seq == 5, 'a controller no unit follows was taken'
rx(mx, CTRL, 0x53, sync_frame(7, bytes(16), W.LOGO, 1))
assert ctrl.osd_sync.seq == 7
print('management  : MANAGER, the followed controller, or MESH_MASTER while none is followed')

# A request is about its sender, unless management asks for a new sync, and
# names the sync's source in its last 16 of 54 bytes.
rx(mx, UNIT, 0x53, request(UNIT, 0xA1B3, W.CAPTIONS, b'\x05', uid(0x40)))
dev, req = seen.requests[-1]
assert (dev, req.target, req.seq, req.what) == (unit, MxrDeviceUid(UNIT), 0xA1B3, W.CAPTIONS)
assert req.is_missing(0) and not req.is_missing(1) and req.is_missing(2) and req.source == MxrDeviceUid(MGR)
n = len(seen.requests)
rx(mx, UNIT, 0x53, request(UNIT, 0xA1B3, W.CAPTIONS, b'\x01', b''))
assert len(seen.requests) == n, 'a 38-byte request, naming no source, was read'
rx(mx, UNIT, 0x53, request(UNIT, 0xA1B3, W.CAPTIONS, b'\x01', MGR[:15]))
assert len(seen.requests) == n, 'a request short of its source was read'
rx(mx, uid(0x11), 0x53, request(UNIT, 0xA1B3, W.CAPTIONS, b'\x01'))
assert len(seen.requests) == n, 'a peer asked for another unit'
rx(mx, MGR, 0x53, request(UNIT, 0, W.CAPTIONS))
assert len(seen.requests) == n + 1, 'management may ask a new sync for another unit'
print('request     : about its sender, a source from 54 bytes, management for another')

# A setting is read from management only, with all the text it counts.
def setting(target, index, records, kind, body):
    return header(2, 0xA1B2, target) + struct.pack('<HHBBHH', index, records, kind, 2, 0x2010, 0x0155) + body
caption_body = (b'DejaVu Sans'.ljust(32, b'\0') + struct.pack('<HhhhBBIH', 0x0124, -0x0203, 0x0405, -2, 2, 1,
                                                              0x00A1B2C3, 7) + b'Input 3')
rx(mx, MGR, 0x53, setting(UNIT, 1, 3, 0, caption_body))
st = seen.settings[-1]
assert (st.index, st.records, st.size, st.layers, st.set) == (1, 3, OsdSyncSize.SMALL, 0x2010, 0x0155), st
assert st.value == OsdCaption(text='Input 3', font='DejaVu Sans', size=0x0124, x=-0x0203, y=0x0405, wrap=-2,
                              align=OsdCaptionAlign.RIGHT, format=OsdCaptionFormat.MARKDOWN, colour=0x00A1B2C3)
rx(mx, MGR, 0x53, setting(UNIT, 2, 3, 1, struct.pack('<bxhh', -1, 0x0302, -0x0405)))
assert seen.settings[-1].value == OsdLogo(logo=-1, x=0x0302, y=-0x0405)
rx(mx, MGR, 0x53, setting(UNIT, 0, 3, 2, struct.pack('<I', 0x00C1D2E3)))
assert seen.settings[-1].value == 0x00C1D2E3
n = len(seen.settings)
for sender, payload in ((uid(0x11), setting(UNIT, 0, 3, 2, bytes(4))), (MGR, setting(UNIT, 3, 3, 2, bytes(4))),
                        (MGR, setting(UNIT, 0, 3, 0, caption_body[:-1])), (MGR, setting(UNIT, 0, 3, 7, bytes(4)))):
    rx(mx, sender, 0x53, payload)
assert len(seen.settings) == n, 'a setting no unit takes was read'
print('setting     : caption, logo and background; only from management, whole, within its count')

# A report is the sender's own, 90 bytes.
report = header(3, 0xA1B3, UNIT) + bytes([2, 0xA5]) + struct.pack('<HH', 2, 1) + b'no space'.ljust(64, b'\0')
rx(mx, UNIT, 0x53, report)
r = unit.osd_sync_report
assert (r.seq, r.state, r.written, r.refused, r.reason) == (0xA1B3, OsdSyncState.FAILED, 2, 1, 'no space'), r
rx(mx, uid(0x11), 0x53, report)
assert peer.osd_sync_report is None
rx(mx, UNIT, 0x53, report[:89])
assert unit.osd_sync_report == r
print('report      :', r.state, r.reason)

# ------------------------------------------------------------------- sending
def caption(text):
    return OsdSyncEntry(value=OsdCaption(text=text), set=0x0100)

def content(n, what=W.CAPTIONS, images=None):
    return OsdSyncContent(what=what, entries=tuple(caption(f'caption {i}') for i in range(n)), images=images)

def run(coro):
    return asyncio.run(coro)

mx, seen, sent = client()
unit = hello(mx, UNIT, DeviceFeature.ONEIP_SINK | DeviceFeature.OSD_SYNC)
other = hello(mx, uid(0x12), DeviceFeature.ONEIP_SINK | DeviceFeature.OSD_SYNC)
plain = hello(mx, uid(0x13), DeviceFeature.ONEIP_SINK)

seq = run(mx.send_osd_sync(content(3)))
assert seq is not None and seq != 0
hellos = [f for f in sent if opcode(f) == 0x00]
assert hellos and DeviceFeature.OSD_SYNC in DeviceFeature(int.from_bytes(hellos[-1][24 + 50:24 + 54], 'little')), \
    'holding a sync did not announce the manager part'
s = sent[-1]
assert opcode(s) == 0x53 and s[2] == 0x2F and kind(s) == 0 and u16(s, 2) == seq
assert s[24 + 4:24 + 20] == bytes(16) and u16(s, 28) == 3 and s[24 + 20] == int(W.CAPTIONS)
print('send        : a sync to every unit, naming its settings, the manager announced')

# Settings go only to the unit that asked, only what it lacks, a few at a time.
sent.clear()
rx(mx, UNIT, 0x53, request(UNIT, seq, W.CAPTIONS, b'\x05', OURS))
rx(mx, UNIT, 0x53, request(UNIT, seq, W.CAPTIONS, b'\x05', OURS))
assert mx._osd_pass() == 2, 'a repeated request queued twice'
assert [(kind(f), f[24 + 4:24 + 20], u16(f, 20)) for f in sent] == [(2, UNIT, 0), (2, UNIT, 2)], sent
assert u16(sent[0], 22) == 3 and u16(sent[0], 2) == seq
assert mx._osd_pass() == 0
print('settings    : only what the unit lacks, to that unit')

# A request for settings of another source's sync is left to it, and one
# naming no source is no unit's.
sent.clear()
rx(mx, UNIT, 0x53, request(UNIT, seq, W.CAPTIONS, b'\x01', uid(0x40)))
rx(mx, UNIT, 0x53, request(UNIT, seq, W.CAPTIONS, b'\x02'))
assert mx._osd_pass() == 0 and sent == [], 'a request this client does not source was answered'
print('sources     : only a request naming this client as the source is answered')

# A new ask replaces what was still queued for the unit; the units take turns.
rx(mx, UNIT, 0x53, request(UNIT, seq, W.CAPTIONS, b'\x07', OURS))
rx(mx, UNIT, 0x53, request(UNIT, seq, W.CAPTIONS, b'\x04', OURS))
sent.clear()
assert mx._osd_pass() == 1 and u16(sent[0], 20) == 2, 'what was queued before the new ask was sent'
big = run(mx.send_osd_sync(content(10)))
for u in (UNIT, uid(0x12)):
    rx(mx, u, 0x53, request(u, big, W.CAPTIONS, b'\xff\x03', OURS))
sent.clear()
mx._osd_pass()
assert [f[24 + 4] for f in sent] == [0x10, 0x12, 0x10, 0x12], 'the units did not take turns'
print('turns       : a new ask replaces the old, and units take turns')

# A request for a sync no longer held gets a new one copying what it asks of
# what is held; one asking for none of it gets none.
while mx._osd_pass():
    pass
sent.clear()
rx(mx, UNIT, 0x53, request(UNIT, seq, W.CAPTIONS | W.LOGO, b'\x01', OURS))
assert len(sent) == 1 and kind(sent[0]) == 0 and sent[0][24 + 4:24 + 20] == UNIT, sent
assert sent[0][24 + 20] == int(W.CAPTIONS) and u16(sent[0], 2) not in (0, seq, big)
# Settings still queued for a sync since replaced are not sent.
rx(mx, UNIT, 0x53, request(UNIT, big, W.CAPTIONS, b'\x01', OURS))
big = run(mx.send_osd_sync(content(10)))
assert mx._osd_pass() == 0, 'settings of a replaced sync were sent'
sent.clear()
rx(mx, UNIT, 0x53, request(UNIT, 0, W.LOGO))
assert sent == [], 'a request asking for none of what is held got a sync'
rx(mx, MGR, 0x53, request(UNIT, 0, W.CAPTIONS))
hello(mx, MGR, DeviceFeature.MANAGER)
rx(mx, MGR, 0x53, request(UNIT, 0, W.CAPTIONS))
assert len(sent) == 1 and sent[0][24 + 4:24 + 20] == UNIT, 'management asking a sync for a unit'
print('new sync    : for a sync no longer held, of what it asks of what is held')

# A resend goes to one unit taking overlay syncs, under a new number.
sent.clear()
again = run(mx.resend_osd_sync(unit))
assert again is not None and again not in (seq, big) and sent[-1][24 + 4:24 + 20] == UNIT
assert run(mx.resend_osd_sync(plain)) is None, 'a unit that takes no overlay sync'
print('resend      : to one unit, under a new number')

# Clearing drops what was queued and the manager part.
rx(mx, UNIT, 0x53, request(UNIT, again, W.CAPTIONS, b'\x01', OURS))
sent.clear()
run(mx.clear_osd_sync())
assert mx._osd_pass() == 0, 'settings were sent after clearing'
assert DeviceFeature.OSD_SYNC not in DeviceFeature(int.from_bytes(sent[-1][24 + 50:24 + 54], 'little'))
rx(mx, UNIT, 0x53, request(UNIT, 0, W.CAPTIONS))
assert run(mx.resend_osd_sync(unit)) is None and mx._osd_pass() == 0, 'answered with nothing held'
print('clear       : nothing queued is sent, and the manager part is handed back')

# The number skips zero.
mx._osd._next_seq = 0xFFFF
run(mx.send_osd_sync(content(1)))
assert u16(sent[-1], 2) == 0xFFFF and run(mx.resend_osd_sync(unit)) == 1, 'the number did not skip zero'
run(mx.clear_osd_sync())

# Content a unit would refuse is refused, and leaves what is held.
def png(width, height):
    return b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + struct.pack('>II', width, height) + bytes(20)
fine = tuple(OsdSyncImage(png=png(16, 16), percent=50) for _ in range(4))
for bad in (OsdSyncContent(what=W(0)),
            content(OSD_SYNC_RECORDS_MAX + 1),
            OsdSyncContent(what=W.CAPTIONS, entries=(OsdSyncEntry(value=OsdCaption(font='f' * 32), set=1),)),
            OsdSyncContent(what=W.CAPTIONS, entries=(OsdSyncEntry(value=OsdCaption(text='t' * 361), set=1),)),
            OsdSyncContent(what=W.LOGO, entries=(OsdSyncEntry(value=OsdLogo(logo=5), set=1),)),
            content(1, images=(OsdSyncImage(png=png(1921, 10)),) + fine[1:]),
            content(1, images=(OsdSyncImage(png=b'GIF89a'),) + fine[1:]),
            content(1, images=(OsdSyncImage(png=png(16, 16), percent=101),) + fine[1:])):
    assert run(mx.send_osd_sync(bad)) is None, bad
assert run(mx.send_osd_sync(OsdSyncContent(what=W.CAPTIONS, entries=(caption('t' * 360),)))) is not None
print('refused     : nothing a unit refuses is sent')

# Images are described in the sync and served as described.
async def serve_and_fetch():
    images = (OsdSyncImage(png=png(16, 16), percent=40), OsdSyncImage(), OsdSyncImage(png=png(8, 4)), OsdSyncImage())
    seq = await mx.send_osd_sync(content(1, images=images))
    frame = sent[-1]
    port = u16(frame, 22)
    assert frame[24 + 20] == int(W.CAPTIONS | W.LOGO_SLOTS) and port != 0
    slot = struct.unpack_from('<IIB', frame, 24 + 32)
    assert slot == (len(images[0].png), osd_crc32(images[0].png), 40), slot
    assert struct.unpack_from('<I', frame, 24 + 44)[0] == 0, 'an empty slot'
    def get(path):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}', timeout=5) as r:
                return r.status, r.read(), r.headers.get('Content-Length')
        except urllib.error.HTTPError as e:
            return e.code, b'', None
    loop = asyncio.get_running_loop()
    assert await loop.run_in_executor(None, get, '/osd-sync/slot1.png') == (200, images[0].png, str(len(images[0].png)))
    assert (await loop.run_in_executor(None, get, '/osd-sync/slot2.png'))[0] == 404, 'an empty slot was served'
    assert (await loop.run_in_executor(None, get, '/osd-sync/slot5.png'))[0] == 404
    await mx.close()
run(serve_and_fetch())
assert not mx.osd_sync_held, 'closing kept the sync'
print('images      : described in the sync, served plainly with their length, 404 otherwise')

print('ALL OK')
