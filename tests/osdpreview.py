#!/usr/bin/env python3
######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Previewing an overlay sync on one unit (0x53): a version 3 sync with
PREVIEW, and the preview command, kind 7, that holds, commits or reverts it.

The layouts are composed here byte by byte from the Rust crate's, which the
firmware has yet to confirm. Every refusal sits next to a command that goes
out.'''

import asyncio, os, struct, sys, time, logging, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import DeviceFeature, MxrDeviceUid, OsdCaption, OsdSyncContent, OsdSyncEntry, OsdSyncImage
from mx_remote.proto.Constants import OSD_PREVIEW_TIMEOUT_MAX, OsdSyncState, OsdSyncWhat as W
from mx_remote.proto.Factory import create_mxr_frame
from mx_remote.proto.FrameV2IPOsdSync import osd_crc32

ADDR = ('192.0.2.9', 8812)
OURS = bytes(range(0x20, 0x30))

def uid(n):
    return bytes([n]) * 16

UNIT, OTHER, PLAIN = uid(0x10), uid(0x12), uid(0x13)

def nm(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def client():
    mx = mx_remote.Remote(open_connection=False)
    mx._uid = OURS
    sent = []
    mx.transmit = lambda data, to=None: (sent.append(bytes(data)), len(data))[1]
    return mx, sent

def rx(mx, sender, opcode, payload=b'', protocol=0x2F):
    frame = bytearray(create_mxr_frame(sender, opcode, payload))
    frame[2] = protocol
    mx.process_frame(time.time(), bytes(frame), ADDR)

def hello(mx, sender, features):
    rx(mx, sender, 0x00, struct.pack('<H', 0x2F) + nm('ONEIP') + nm('P8SN%08d' % sender[0]) + nm('4.8.0')
                         + struct.pack('<I', int(features)), protocol=0x01)
    return mx.get_by_uid(MxrDeviceUid(sender))

def u16(frame, at):
    return struct.unpack_from('<H', frame, 24 + at)[0]

def payload(frame):
    return frame[24:]

def request(target, seq, missing, source=OURS):
    return bytes([2, 1]) + struct.pack('<H', seq) + target + bytes([int(W.CAPTIONS), 0xA5]) \
        + missing.ljust(16, b'\0') + source

def report(target, seq, state):
    return (bytes([2, 3]) + struct.pack('<H', seq) + target + bytes([state, 0xA5]) + struct.pack('<HH', 0, 0)
            + b'why').ljust(90, b'\0')

def caption(text):
    return OsdSyncEntry(value=OsdCaption(text=text), set=0x0100)

def named(name, n, images=None):
    return OsdSyncContent(what=W.CAPTIONS, entries=tuple(caption(f'{name} {i}') for i in range(n)), images=images)

def answered(mx, sent, unit, seq, missing):
    '''The settings sent for unit's request of missing of sync seq, as their
    index and caption text.'''
    sent.clear()
    rx(mx, unit, 0x53, request(unit, seq, missing))
    while mx._osd_pass():
        pass
    out = []
    for f in sent:
        p = payload(f)
        if (p[1] == 2):
            length = struct.unpack_from('<H', p, 30 + 46)[0]
            out.append((struct.unpack_from('<H', p, 20)[0], p[30 + 48:30 + 48 + length].decode()))
    return out

def png(width, height):
    return b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + struct.pack('>II', width, height) + bytes(20)

def run(coro):
    return asyncio.run(coro)

def setup():
    mx, sent = client()
    devs = (hello(mx, UNIT, DeviceFeature.ONEIP_SINK | DeviceFeature.OSD_SYNC),
            hello(mx, OTHER, DeviceFeature.ONEIP_SINK | DeviceFeature.OSD_SYNC),
            hello(mx, PLAIN, DeviceFeature.ONEIP_SINK))
    sent.clear()
    return (mx, sent) + devs

# ------------------------------------------------------- the preview sync
mx, sent, unit, other, plain = setup()
seq = run(mx.send_osd_preview(unit, named('preview', 3), layer=0x5A, timeout=0x0E10))
assert seq is not None and seq != 0
f, = sent
assert int.from_bytes(f[20:22], 'little') == 0x53 and f[2] == 0x2F, 'opcode and stamp'
p = payload(f)
assert len(p) == 84, len(p)
assert p[:4] == bytes([3, 0]) + struct.pack('<H', seq), 'version 3, a sync, its number'
assert p[4:20] == UNIT, 'a preview names its unit'
assert (p[20], p[21]) == (int(W.CAPTIONS), 1), 'what, and the PREVIEW flag at 21'
assert struct.unpack_from('<HIH', p, 22) == (0, 0, 3), 'no image server, the source unspecified, 3 records'
assert p[32:80] == bytes(48), 'no slots without images'
assert struct.unpack_from('<HBB', p, 80) == (0x0E10, 0x5A, 0), 'the timeout, the layer and a reserved byte'
assert not mx.osd_sync_held, 'a preview took the manager part'
print('sync        : version 3 to one unit, PREVIEW at 21, the timeout at 80 and the layer at 82')

# A previewing unit is answered from its preview; every other unit, and a sync
# of the held content, still get the held content.
held = run(mx.send_osd_sync(named('held', 2)))
assert answered(mx, sent, UNIT, seq, b'\x05') == [(0, 'preview 0'), (2, 'preview 2')]
assert answered(mx, sent, UNIT, held, b'\x01') == [(0, 'held 0')]
assert answered(mx, sent, OTHER, held, b'\x03') == [(0, 'held 0'), (1, 'held 1')]
assert answered(mx, sent, OTHER, seq, b'\x01') == [], 'another unit answered from the preview'
# Kept after the held sync is cleared, with what was queued for it.
rx(mx, UNIT, 0x53, request(UNIT, seq, b'\x02'))
run(mx.clear_osd_sync())
sent.clear()
assert mx._osd_pass() == 1 and u16(sent[0], 20) == 1, 'settings queued for a preview went with the held sync'
assert answered(mx, sent, UNIT, seq, b'\x02') == [(1, 'preview 1')], 'a preview went with the held sync'
print('answered    : from the preview, beside the held sync')

# ------------------------------------------------------- the preview command
sent.clear()
assert run(mx.hold_osd_preview(unit, 0xA1B2, layer=0x5A, timeout=0x0E10)) is True
assert run(mx.commit_osd_preview(unit, 0xA1B2)) is True
assert run(mx.revert_osd_preview(unit, 0xA1B2)) is True
hold, commit, revert = (payload(f) for f in sent)
assert hold == bytes([3, 7, 0xB2, 0xA1]) + UNIT + bytes([1, 0x5A]) + struct.pack('<H', 0x0E10), hold.hex()
assert commit == bytes([3, 7, 0xB2, 0xA1]) + UNIT + bytes([2, 0, 0, 0]), commit.hex()
assert revert == bytes([3, 7, 0xB2, 0xA1]) + UNIT + bytes([3, 0, 0, 0]), revert.hex()
assert answered(mx, sent, UNIT, seq, b'\x01') == [(0, 'preview 0')], 'a command on another sync ended the preview'
print('commands    : HOLD with its layer and timeout, COMMIT and REVERT with neither')

# Committing or reverting ends the preview.
for end in (mx.commit_osd_preview, mx.revert_osd_preview):
    seq = run(mx.send_osd_preview(unit, named('preview', 3), layer=1))
    assert answered(mx, sent, UNIT, seq, b'\x01') == [(0, 'preview 0')]
    assert run(end(unit, seq)) is True
    assert answered(mx, sent, UNIT, seq, b'\x01') == [], f'{end.__name__} left the preview answered'

# A report that it was stored, failed or put back ends it; one that it
# previews, or one on another sync, does not.
for state, ends in ((OsdSyncState.TAKING, False), (OsdSyncState.PREVIEWING, False), (OsdSyncState.DONE, True),
                    (OsdSyncState.FAILED, True), (OsdSyncState.REVERTED, True)):
    seq = run(mx.send_osd_preview(unit, named('preview', 3), layer=1))
    rx(mx, UNIT, 0x53, report(UNIT, (seq + 1) & 0xFFFF, int(state)))
    assert answered(mx, sent, UNIT, seq, b'\x01') == [(0, 'preview 0')], f'{state!r} on another sync'
    rx(mx, UNIT, 0x53, report(UNIT, seq, int(state)))
    assert unit.osd_sync_report.state == state
    assert (answered(mx, sent, UNIT, seq, b'\x01') == []) == ends, f'{state!r}'
# A new preview replaces the unit's last.
first = run(mx.send_osd_preview(unit, named('first', 3), layer=1))
second = run(mx.send_osd_preview(unit, named('second', 3), layer=1))
assert answered(mx, sent, UNIT, second, b'\x01') == [(0, 'second 0')]
assert answered(mx, sent, UNIT, first, b'\x01') == [], 'the replaced preview answered'
print('ended       : by a commit, a revert, a report that it ended, or a new preview')

# ------------------------------------------------------- refused
mx, sent, unit, other, plain = setup()
images = (OsdSyncImage(png=png(16, 16), percent=40), OsdSyncImage(), OsdSyncImage(), OsdSyncImage())
for coro, why in ((mx.send_osd_preview(plain, named('x', 1), layer=1), 'a unit that takes no overlay sync'),
                  (mx.send_osd_preview(unit, named('x', 1), layer=1, timeout=OSD_PREVIEW_TIMEOUT_MAX + 1), 'a timeout'),
                  (mx.send_osd_preview(unit, named('x', 1), layer=256), 'a layer'),
                  (mx.send_osd_preview(unit, OsdSyncContent(what=W(0), entries=()), layer=1), 'copying nothing')):
    assert run(coro) is None and sent == [], why
for coro, why in ((mx.hold_osd_preview(unit, 1, layer=1, timeout=OSD_PREVIEW_TIMEOUT_MAX + 1), 'a timeout'),
                  (mx.hold_osd_preview(plain, 1, layer=1), 'a unit that takes no overlay sync'),
                  (mx.commit_osd_preview(plain, 1), 'a commit to a unit that takes no overlay sync'),
                  (mx.revert_osd_preview(plain, 1), 'a revert to a unit that takes no overlay sync')):
    assert run(coro) is False and sent == [], why
assert run(mx.send_osd_preview(unit, named('x', 1), layer=1, timeout=OSD_PREVIEW_TIMEOUT_MAX)) is not None
assert run(mx.hold_osd_preview(unit, 1, layer=255, timeout=OSD_PREVIEW_TIMEOUT_MAX)) is True
# One that cannot be sent is not kept.
mx.transmit = lambda data, to=None: 0
assert run(mx.send_osd_preview(unit, named('lost', 1), layer=1)) is None
assert MxrDeviceUid(UNIT) not in mx._osd.previews, 'a preview that did not go out was kept'
print('refused     : nothing a unit refuses is sent; one not sent is not kept')

# ------------------------------------------------------- images
async def images_of_their_own():
    mx, sent, unit, other, plain = setup()
    held_images = (OsdSyncImage(png=png(8, 4)), OsdSyncImage(), OsdSyncImage(), OsdSyncImage())
    await mx.send_osd_sync(named('held', 1, images=held_images))
    held_port = u16(sent[-1], 22)
    seq = await mx.send_osd_preview(unit, named('preview', 1, images=images), layer=1)
    p = payload(sent[-1])
    port = struct.unpack_from('<H', p, 22)[0]
    assert p[20] == int(W.CAPTIONS | W.LOGO_SLOTS) and port not in (0, held_port), (port, held_port)
    assert struct.unpack_from('<IIB', p, 32) == (len(images[0].png), osd_crc32(images[0].png), 40)
    assert len(p) == 84 and struct.unpack_from('<HB', p, 80) == (0, 1)
    def get(port):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/osd-sync/slot1.png', timeout=5) as r:
                return r.read()
        except OSError:
            return None
    loop = asyncio.get_running_loop()
    assert await loop.run_in_executor(None, get, port) == images[0].png, 'the preview\'s image'
    assert await loop.run_in_executor(None, get, held_port) == held_images[0].png, 'the held sync\'s image moved'
    # Ending the preview stops its server, and leaves the held sync's.
    rx(mx, UNIT, 0x53, report(UNIT, seq, int(OsdSyncState.REVERTED)))
    await asyncio.sleep(0.05)
    assert await loop.run_in_executor(None, get, port) is None, 'an ended preview\'s images still served'
    assert await loop.run_in_executor(None, get, held_port) == held_images[0].png
    # A new preview's server replaces the last one's.
    await mx.send_osd_preview(unit, named('first', 1, images=images), layer=1)
    first = u16(sent[-1], 22)
    await mx.send_osd_preview(unit, named('second', 1, images=images), layer=1)
    assert await loop.run_in_executor(None, get, first) is None, 'a replaced preview\'s images still served'
    assert await loop.run_in_executor(None, get, u16(sent[-1], 22)) == images[0].png
    await mx.close()
run(images_of_their_own())
print('images      : served on a port of their own, stopped with the preview')

print('ALL OK')
