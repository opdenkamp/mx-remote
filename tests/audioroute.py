######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Audio routes across units, and what a sent audio command holds (0x43).

A route across units is switched by every unit owning an endpoint on the way,
each finding the path itself, so the path here must be the one a unit finds:
searched back from the sink within the sink's device, depth first. Each unit on
it is sent the whole request, from the sink's end.

A sent route or lock is held as the device's state once the frame is away,
and the device's features and links reports are ignored for 500 ms after an
audio command, so a report it sent before taking the command cannot undo it.

Every entry's padding is poisoned, so a field read at the wrong offset shows.
Each refusal sits next to a send that goes out.
'''

import asyncio, os, struct, sys, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import AudioFeatures, AudioHop, DeviceFeature, MxrDeviceUid
from mx_remote.proto.Constants import BayFeaturesMask as F
from mx_remote.proto.Factory import create_mxr_frame

ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False)
mx._uid = bytes(range(0x20, 0x30))

# The module's feature bits and entry kinds, written out so a wrong constant in
# the library cannot agree with itself here.
INPUT, OUTPUT, TX, RX = 1 << 0, 1 << 1, 1 << 2, 1 << 3
HDMI, SPDIF, TRIGGER, MUTE, LOCK = 1 << 4, 1 << 6, 1 << 7, 1 << 8, 1 << 15
ENDPOINT, ADDRESS, ROUTE_IN, PARENT = 1, 2, 3, 5
GUARD = 0.5

def uid(n):
    return bytes([n]) * 16

def name(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def rx(sender, opcode, payload=b'', protocol=0x2F, at=None):
    frame = bytearray(create_mxr_frame(sender, opcode, payload))
    frame[2] = protocol
    mx.process_frame(time.time() if (at is None) else at, bytes(frame), ADDR)

def hello(n, protocol=0x2F):
    rx(uid(n), 0x00, struct.pack('<H', protocol) + name('ONEIP') + name(f'P8SN{n:08X}')
                   + name('5.0.0') + struct.pack('<I', int(DeviceFeature.ONEIP_SINK)))
    return mx.get_by_uid(MxrDeviceUid(uid(n)))

def report(n, entries, stride=16):
    '''A features report from unit n listing entries, each the endpoint id,
    the entry kind and the two words at entry offsets 8 and 12.'''
    p = bytearray([0xA5] * (36 + stride * len(entries)))
    p[0:4] = bytes(4)                          # FEATURES, and its padding
    p[4:20] = uid(n)                           # a unit reports only its own
    p[28:30] = struct.pack('<H', len(entries))
    for i, (id, kind, first, second) in enumerate(entries):
        at = 36 + i * stride
        p[at], p[at + 1] = id, kind
        p[at + 8:at + 16] = struct.pack('<II', first, second)
    return bytes(p)

def encoder_tree(n):
    '''An encoder: its HDMI input (2) feeding the stream it sends (0).'''
    return report(n, [(0, ENDPOINT, OUTPUT | TX, 0), (0, ROUTE_IN, 1 << 2, 1 << 2),
                      (2, ENDPOINT, INPUT | HDMI, 0), (2, PARENT, 0, 0)])

def decoder_tree(n):
    '''A decoder: the stream it receives (1) feeding its HDMI output (3) and
    its S/PDIF output (4), each routed from nothing.'''
    return report(n, [(1, ENDPOINT, INPUT | RX, 0),
                      (3, ENDPOINT, OUTPUT | HDMI, 0), (3, ROUTE_IN, 1 << 1, 0), (3, PARENT, 1, 0),
                      (4, ENDPOINT, OUTPUT | SPDIF, 0), (4, ROUTE_IN, 1 << 1, 0), (4, PARENT, 1, 0)])

def U(n):
    return MxrDeviceUid(uid(n))

sent = []
mx.transmit = lambda data, to=None: (sent.append((data, to)), len(data))[1]

def call(coro):
    return asyncio.new_event_loop().run_until_complete(coro)

def selections(frames):
    '''The addressee, sink, sink endpoint, source and source endpoint of each
    current SELECT_INPUT.'''
    rv = []
    for data, _ in frames:
        p = data[24:]
        assert int.from_bytes(data[20:22], 'little') == 0x43
        assert len(p) == 56, f'not the current SELECT_INPUT: {len(p)} bytes'
        assert p[:4] == bytes([3, 0, 0, 0]), 'not SELECT_INPUT'
        rv.append((MxrDeviceUid(p[4:20]), MxrDeviceUid(p[20:36]), int.from_bytes(p[52:54], 'little'),
                   MxrDeviceUid(p[36:52]), int.from_bytes(p[54:56], 'little')))
    return rv

def route(sink, sink_ep, source, source_ep):
    del sent[:]
    return call(mx.select_audio_endpoint_input(U(sink), sink_ep, U(source), source_ep))

def refused(sink, sink_ep, source, source_ep, why):
    assert route(sink, sink_ep, source, source_ep) is False, why
    assert sent == [], f'{why}: refused, but transmitted anyway'

def hop(sink_device, sink, source_device, source):
    return AudioHop(U(sink_device), sink, U(source_device), source)

ENC, DEC = 0x40, 0x41
encoder, decoder = hello(ENC), hello(DEC)
rx(uid(ENC), 0x43, encoder_tree(ENC))
rx(uid(DEC), 0x43, decoder_tree(DEC))

# ------------------------------------------------------------------- the path
# The shortest route, hop by hop from the source: an encoder's sent stream
# joins another unit's received one.
assert mx.audio_route(U(DEC), 3, U(ENC), 2) == [hop(ENC, 0, ENC, 2), hop(DEC, 1, ENC, 0), hop(DEC, 3, DEC, 1)], \
    mx.audio_route(U(DEC), 3, U(ENC), 2)
assert mx.audio_route(U(DEC), 3, U(ENC), 0) == [hop(DEC, 1, ENC, 0), hop(DEC, 3, DEC, 1)], \
    mx.audio_route(U(DEC), 3, U(ENC), 0)
assert mx.audio_route(U(ENC), 2, U(DEC), 3) is None, 'backwards'
assert mx.audio_route(U(DEC), 4, U(DEC), 3) is None, 'unroutable'
assert mx.audio_route(U(DEC), 3, U(DEC), 3) is None, 'itself'
assert mx.audio_route(U(DEC), 9, U(ENC), 2) is None, 'a sink endpoint nothing reported'
assert mx.audio_route(U(DEC), 3, U(0x7F), 2) is None, 'a source device that reported nothing'
# Through the stream the sink is routed from, not the unit's first receiving
# one, which only the fallback takes.
TWO = 0x42
hello(TWO)
rx(uid(TWO), 0x43, report(TWO, [(5, ENDPOINT, INPUT | RX, 0), (1, ENDPOINT, INPUT | RX, 0),
                                (3, ENDPOINT, OUTPUT | HDMI, 0), (3, ROUTE_IN, 1 << 1, 0)]))
assert mx.audio_route(U(TWO), 3, U(ENC), 0) == [hop(TWO, 1, ENC, 0), hop(TWO, 3, TWO, 1)], \
    mx.audio_route(U(TWO), 3, U(ENC), 0)
# Failing that, the source unit's first sending endpoint feeds the sink unit's
# first receiving one, with no hop where either is already the end.
FB = 0x43
hello(FB)
rx(uid(FB), 0x43, report(FB, [(1, ENDPOINT, INPUT | RX, 0), (3, ENDPOINT, OUTPUT | HDMI, 0)]))
assert mx.audio_route(U(FB), 3, U(ENC), 0) == [hop(FB, 1, ENC, 0), hop(FB, 3, FB, 1)], \
    'a source that sends needs no hop into its own stream'
assert mx.audio_route(U(DEC), 1, U(ENC), 2) == [hop(ENC, 0, ENC, 2), hop(DEC, 1, ENC, 0)], \
    'a sink that receives needs no hop out of its own stream'
print('path        : shortest, through the stream, none backwards or to itself')

def routes_tree(n, nodes):
    '''Output endpoints, each routable from the endpoint ids it lists (none
    for an empty list), and an input endpoint 1 to start from.'''
    entries = [(1, ENDPOINT, INPUT, 0)]
    for id, sources in nodes:
        entries.append((id, ENDPOINT, OUTPUT, 0))
        if sources:
            entries.append((id, ROUTE_IN, sum(1 << s for s in sources), 0))
    return report(n, entries)

TIES, SHORTER, SEARCHED, COLLISION = 0x4A, 0x4B, 0x4C, 0x4D
for n in (TIES, SHORTER, SEARCHED, COLLISION):
    hello(n)
rx(uid(TIES), 0x43, routes_tree(TIES, [(7, [3, 5]), (3, [1]), (5, [1])]))
rx(uid(SHORTER), 0x43, routes_tree(SHORTER, [(7, [2, 4]), (2, [6]), (6, [1]), (4, [1])]))
rx(uid(SEARCHED), 0x43, routes_tree(SEARCHED, [(7, [2, 4]), (2, [4]), (4, [1])]))
rx(uid(COLLISION), 0x43, routes_tree(COLLISION, [(7, [1])]))
assert mx.audio_route(U(TIES), 7, U(TIES), 1) == [hop(TIES, 3, TIES, 1)], \
    'the lower id of two as short, the sink\'s own hop left out'
assert mx.audio_route(U(SHORTER), 7, U(SHORTER), 1) == [hop(SHORTER, 4, SHORTER, 1)], \
    'a later, strictly shorter candidate'
assert mx.audio_route(U(SEARCHED), 7, U(SEARCHED), 1) == [hop(SEARCHED, 4, SEARCHED, 1), hop(SEARCHED, 2, SEARCHED, 4)], \
    '4 was searched through 2, so not again from 7'
assert mx.audio_route(U(COLLISION), 7, U(TIES), 1) == [hop(COLLISION, 7, TIES, 1)], \
    'a source on another device whose id the routes name'
# The sink counts as searched from the start, so a loop back through it is
# not a route.
LOOP = 0x4F
hello(LOOP)
rx(uid(LOOP), 0x43, routes_tree(LOOP, [(7, [3, 5]), (3, [7]), (5, [1])]))
assert mx.audio_route(U(LOOP), 7, U(LOOP), 1) == [hop(LOOP, 5, LOOP, 1)], mx.audio_route(U(LOOP), 7, U(LOOP), 1)
print('search      : back from the sink, ascending ids, strictly shorter, each endpoint once')

# ------------------------------------------------------------------- sending
# One SELECT_INPUT to each unit owning a hop's sink endpoint, from the sink's
# end, each carrying the whole request and sent by the unit's own path.
assert route(DEC, 3, ENC, 2) is True
assert selections(sent) == [(U(DEC), U(DEC), 3, U(ENC), 2), (U(ENC), U(DEC), 3, U(ENC), 2)], selections(sent)
assert [to for _, to in sent] == [decoder, encoder], 'a route frame not sent by its unit\'s path'
assert route(DEC, 4, DEC, 1) is True
assert selections(sent) == [(U(DEC), U(DEC), 4, U(DEC), 1)], selections(sent)
print('send        : to each unit on the route, from the sink\'s end')

refused(ENC, 2, DEC, 3, 'a route without a path')
print('no route    : refused, nothing sent')

# An output bay's endpoint route goes the same way: the bay names its unit's
# endpoint, and the source bay's device the source's.
def rec(port, mode, label, features):
    return bytes([port, mode, 0, 0, 0]) + name(label) + name(label) + name('1080p') + struct.pack('<II', 0, int(features))
def transceiver(n):
    rx(uid(n), 0x00, struct.pack('<H', 0x2F) + name('ONEIP') + name(f'P8SN{n:08X}') + name('5.0.0')
                     + struct.pack('<I', int(DeviceFeature.ONEIP_SOURCE | DeviceFeature.ONEIP_SINK)))
    rx(uid(n), 0x02, rec(0, 0, 'Input 1', F.HDMI_IN | F.ONEIP_SOURCE_LOCAL)
                     + rec(16, 1, 'Output 1', F.HDMI_OUT | F.ONEIP_SINK_LOCAL))
    return mx.get_by_uid(U(n))
def transceiver_tree(n):
    '''Both trees on one unit: a bay maps to its unit's first root endpoint
    of each direction.'''
    return report(n, [(0, ENDPOINT, OUTPUT | TX, 0), (0, ROUTE_IN, 1 << 2, 1 << 2),
                      (2, ENDPOINT, INPUT | HDMI, 0), (2, PARENT, 0, 0),
                      (1, ENDPOINT, INPUT | RX, 0),
                      (3, ENDPOINT, OUTPUT | HDMI, 0), (3, ROUTE_IN, 1 << 1, 0), (3, PARENT, 1, 0),
                      (4, ENDPOINT, OUTPUT | SPDIF, 0), (4, ROUTE_IN, 1 << 1, 0), (4, PARENT, 1, 0)])
BENC, BDEC = 0x44, 0x45
benc, bdec = transceiver(BENC), transceiver(BDEC)
rx(uid(BENC), 0x43, transceiver_tree(BENC))
rx(uid(BDEC), 0x43, transceiver_tree(BDEC))
sink_bay = bdec.first_output
assert (sink_bay is not None) and sink_bay.is_oneip_sink and (sink_bay.audio_endpoint is not None), sink_bay
sink_ep = sink_bay.audio_endpoint.id
assert mx.audio_route(U(BDEC), sink_ep, U(BDEC), sink_ep) is None, 'an endpoint routed to itself through its own stream'
want = mx.audio_route(U(BDEC), sink_ep, U(BENC), 2)
assert want is not None and {h.sink_device for h in want} == {U(BENC), U(BDEC)}, want
del sent[:]
assert call(sink_bay.select_audio_source(benc.first_input, endpoint='2')) is True, 'an output bay\'s route was refused'
assert selections(sent) == [(U(BDEC), U(BDEC), sink_ep, U(BENC), 2), (U(BENC), U(BDEC), sink_ep, U(BENC), 2)], \
    selections(sent)
# A unit sending no stream, and naming nothing the sink is routed from.
mute_unit = transceiver(0x46)
rx(uid(0x46), 0x43, report(0x46, [(5, ENDPOINT, INPUT | HDMI, 0)]))
assert mx.audio_route(U(BDEC), sink_ep, U(0x46), 5) is None
del sent[:]
assert call(sink_bay.select_audio_source(mute_unit.first_input, endpoint='5')) is False and sent == [], \
    'an output bay\'s route without a path'
print('bay route   : an output bay\'s endpoint route goes to every unit on it')

# ------------------------------------------------------------------- holding
# Once a route is sent, each hop within a unit reads as routed here, and an
# older report from the unit cannot undo it.
for n in (ENC, DEC):
    mx.get_by_uid(U(n))._audio_commanded = None
rx(uid(ENC), 0x43, encoder_tree(ENC))
rx(uid(DEC), 0x43, decoder_tree(DEC))
assert decoder.audio_endpoint_by_id(3).input is None, 'the fixture routes 3 already'
calls = []
decoder.register_callback(lambda d: calls.append(d))
assert route(DEC, 3, ENC, 2) is True
assert decoder.audio_endpoint_by_id(3).input is decoder.audio_endpoint_by_id(1), 'a sent route was not held'
assert encoder.audio_endpoint_by_id(0).input is encoder.audio_endpoint_by_id(2)
assert decoder.audio_endpoint_by_id(4).input is None, 'a hop the route does not take was routed'
assert len(calls) == 1, f'{len(calls)} callbacks for a held route'
rx(uid(DEC), 0x43, decoder_tree(DEC))
assert decoder.audio_endpoint_by_id(3).input is decoder.audio_endpoint_by_id(1), 'an older report undid it'
rx(uid(DEC), 0x43, decoder_tree(DEC), at=time.time() + GUARD)
assert decoder.audio_endpoint_by_id(3).input is None and len(calls) == 2, \
    'a report changing only the routing was not a change'

# A hop from another unit is that unit's stream, not this one's routing, even
# where the source's id is one this unit routes from.
assert route(COLLISION, 7, TIES, 1) is True
assert mx.get_by_uid(U(COLLISION)).audio_endpoint_by_id(7).input is None, 'a hop from another unit was held'
# A unit's own hop into an endpoint that reports no routes holds nothing.
NR = 0x4E
noroutes = hello(NR)
rx(uid(NR), 0x43, report(NR, [(0, ENDPOINT, OUTPUT | TX, 0), (2, ENDPOINT, INPUT | HDMI, 0),
                              (1, ENDPOINT, INPUT | RX, 0)]))
assert mx.audio_route(U(NR), 1, U(NR), 2) == [hop(NR, 0, NR, 2)], mx.audio_route(U(NR), 1, U(NR), 2)
assert route(NR, 1, NR, 2) is True
assert noroutes.audio_endpoint_by_id(0).input is None, 'a hop into an endpoint without routes was held'
noroutes.hold_audio_route(sink=0, source=2)
assert noroutes.audio_endpoint_by_id(0).input is None
decoder.hold_audio_route(sink=4, source=40)
assert decoder.audio_endpoint_by_id(4).in_routes == 0, 'a source id no routes word can name was held'
print('hold route  : each unit\'s own hops read routed until it reports')

# ------------------------------------------------------------------- 4.4.2
# A unit on released firmware up to 4.4.2 is sent the 8-byte form naming two
# of its own endpoints, and anything newer the form naming both units, as its
# own features report says.
OLD, NEW = 0x50, 0x51
old, new = hello(OLD, protocol=0x1E), hello(NEW)
own = [(4, ENDPOINT, OUTPUT, 0), (4, ROUTE_IN, 1 << 9, 0), (9, ENDPOINT, INPUT, 0)]
rx(uid(OLD), 0x43, report(OLD, own, stride=24), protocol=0x1E)
rx(uid(NEW), 0x43, report(NEW, own))
assert route(OLD, 4, OLD, 9) is True
p = sent[-1][0][24:]
assert len(p) == 28, len(p)
assert p[:2] == bytes([3, 0]) and p[4:20] == uid(OLD)
assert p[20:28] == bytes([4, 0, 0, 0, 9, 0, 0, 0]), p[20:28].hex()
assert route(NEW, 4, NEW, 9) is True
assert selections(sent) == [(U(NEW), U(NEW), 4, U(NEW), 9)]
# A report in the current layout from the older-numbered unit decides it, once
# the guard after the command above has passed.
old._audio_commanded = None
rx(uid(OLD), 0x43, report(OLD, own), protocol=0x1E)
assert route(OLD, 4, OLD, 9) is True
assert selections(sent) == [(U(OLD), U(OLD), 4, U(OLD), 9)]

# A route that crosses a unit on 4.4.2 is refused whole, since that unit routes
# only between its own endpoints.
XENC, XDEC = 0x52, 0x53
hello(XENC), hello(XDEC, protocol=0x1E)
rx(uid(XENC), 0x43, report(XENC, [(0, ENDPOINT, OUTPUT | TX, 0)]))
rx(uid(XDEC), 0x43, report(XDEC, [(1, ENDPOINT, INPUT | RX, 0)], stride=24), protocol=0x1E)
assert mx.audio_route(U(XDEC), 1, U(XENC), 0) == [hop(XDEC, 1, XENC, 0)]
refused(XDEC, 1, XENC, 0, 'a route across a 4.4.2 unit')
# The 4.4.2 unit here is the second one sent to, so a route sending as it went
# would already have sent the first.
YDEC, YTX = 0x55, 0x56
hello(YDEC)
rx(uid(YDEC), 0x43, report(YDEC, [(1, ENDPOINT, INPUT | RX, 0), (2, ENDPOINT, OUTPUT | HDMI, 0),
                                  (2, ROUTE_IN, 1 << 1, 0)]))
hello(YTX, protocol=0x1E)
rx(uid(YTX), 0x43, report(YTX, [(0, ENDPOINT, OUTPUT | TX, 0), (0, ROUTE_IN, 1 << 3, 0),
                                (3, ENDPOINT, INPUT | HDMI, 0)], stride=24), protocol=0x1E)
assert [h.sink_device for h in mx.audio_route(U(YDEC), 2, U(YTX), 3)] == [U(YTX), U(YDEC), U(YDEC)]
refused(YDEC, 2, YTX, 3, 'a route whose second unit is on 4.4.2')
print('4.4.2       : its own endpoints in 8 bytes; a route reaching it from another unit refused')

# ------------------------------------------------------------------- the lock
# A sent lock is the unit's state here once the frame is away, on its own bit,
# until the unit reports.
SW = 0x60
switch = hello(SW)
def switchable(status0=0, status1=0):
    '''Endpoint 0 can be muted, endpoint 1 can lock its source and drive a
    trigger.'''
    return report(SW, [(0, ENDPOINT, OUTPUT | MUTE, status0), (1, ENDPOINT, INPUT | LOCK | TRIGGER, status1)])
rx(uid(SW), 0x43, switchable(status0=MUTE, status1=TRIGGER))
del sent[:]
assert call(switch.set_audio_endpoint_locked(1, True)) is True
assert sent[-1][1] is switch, 'a lock not sent by the unit\'s path'
assert switch.audio_endpoint_by_id(1).status == AudioFeatures(LOCK | TRIGGER), switch.audio_endpoint_by_id(1).status
assert switch.audio_endpoint_by_id(0).status == AudioFeatures(MUTE), 'another endpoint was touched'
swcalls = []
switch.register_callback(lambda d: swcalls.append(d))
switch._audio_commanded = None
assert call(switch.set_audio_endpoint_locked(1, False)) is True
assert len(swcalls) == 1, f'{len(swcalls)} callbacks for a held lock'
assert call(switch.set_audio_endpoint_locked(1, False)) is True
assert len(swcalls) == 1, 'an unchanged lock was reported as a change'
switch.audio_endpoint_by_id(1).status = None
assert call(switch.set_audio_endpoint_locked(1, True)) is True
assert switch.audio_endpoint_by_id(1).status is None, 'a lock was held on an endpoint that reported no status'
switch.audio_endpoint_by_id(1).status = AudioFeatures(TRIGGER)
assert switch.audio_endpoint_by_id(1).status == AudioFeatures(TRIGGER), 'an unlock was not held'
del sent[:]
assert call(switch.set_audio_endpoint_locked(0, True)) is False and sent == [], 'an endpoint that cannot lock'
assert switch.audio_endpoint_by_id(0).status == AudioFeatures(MUTE), 'a refused lock was held'
print('hold lock   : held on its own bit once sent')

# ------------------------------------------------------------------- the guard
# For 500 ms after a command, a unit's features and links reports are ignored;
# one after that is taken, and other units' reports always are.
G, H = 0x61, 0x62
guarded, other = hello(G), hello(H)
def tree(n, status=0):
    return report(n, [(0, ENDPOINT, OUTPUT, status), (1, ENDPOINT, INPUT | LOCK, 0)])
t0 = time.time()
rx(uid(G), 0x43, tree(G), at=t0)
rx(uid(H), 0x43, tree(H), at=t0)
assert guarded.audio_reported == t0, 'the time a report was taken'
assert call(guarded.set_audio_endpoint_locked(1, True)) is True
sent_at = guarded._audio_commanded
assert sent_at is not None, 'the command was not recorded'

rx(uid(G), 0x43, tree(G, status=MUTE), at=sent_at + GUARD - 0.001)
assert guarded.audio_endpoint_by_id(1).audio_locked is True, 'a report inside the guard undid the lock'
assert guarded.audio_endpoint_by_id(0).status == AudioFeatures(0), 'a report inside the guard was taken'
assert guarded.audio_reported == t0, 'an ignored report counted'
rx(uid(G), 0x43, tree(G, status=MUTE), at=sent_at - 1.0)
assert guarded.audio_endpoint_by_id(0).status == AudioFeatures(0), 'a report stamped before the command was taken'

def links(n, ep, far, far_dev):
    return struct.pack('<H', 5) + bytes(2) + uid(n) + struct.pack('<H', 1) + bytes(2) \
        + struct.pack('<BB', ep, far) + bytes(2) + far_dev
rx(uid(G), 0x43, links(G, 0, 1, uid(H)), at=sent_at + GUARD - 0.001)
assert guarded.audio_endpoint_by_id(0).link(mx) is None, 'a links report inside the guard was taken'

rx(uid(H), 0x43, tree(H, status=MUTE), at=sent_at + 0.1)
assert other.audio_endpoint_by_id(0).status == AudioFeatures(MUTE), 'a unit with no command was guarded'

rx(uid(G), 0x43, links(G, 0, 1, uid(H)), at=sent_at + GUARD)
assert guarded.audio_endpoint_by_id(0).link(mx) is other.audio_endpoint_by_id(1), 'the guard outlived 500 ms for links'
rx(uid(G), 0x43, tree(G, status=MUTE), at=sent_at + GUARD)
assert guarded.audio_endpoint_by_id(0).status == AudioFeatures(MUTE), 'the guard outlived 500 ms'
assert guarded.audio_endpoint_by_id(1).audio_locked is False, 'the unit\'s own report did not replace the held lock'
assert guarded.audio_reported == sent_at + GUARD
print('guard       : reports ignored for 500 ms after a command, then taken')

# ------------------------------------------------------------------- address
# The entry with the device's own id carries the unit's address and HTTP port,
# which no endpoint takes.
A = 0x63
addressed = hello(A)
p = bytearray([0xA5] * 68)
p[0:4] = bytes(4)
p[4:20] = uid(A)
p[28:30] = struct.pack('<H', 2)
p[36], p[37] = 0xFF, ADDRESS
p[44:48] = bytes([10, 1, 2, 3])
p[48:50] = struct.pack('<H', 80)
p[52], p[53] = 3, ENDPOINT
p[60:64] = struct.pack('<I', OUTPUT)
rx(uid(A), 0x43, bytes(p))
eps = addressed.audio_endpoints
assert (eps.address.ip, eps.address.port) == ('10.1.2.3', 80), eps.address
assert list(eps.endpoints) == [3], list(eps.endpoints)
acalls = []
addressed.register_callback(lambda d: acalls.append(d))
p[37] = PARENT
rx(uid(A), 0x43, bytes(p))
assert addressed.audio_endpoints.address is None, 'only an address entry names one'
assert len(acalls) == 1, 'a report changing only the address was not a change'
print('address     : the device\'s own address from its 0xFF entry')

print('ALL OK')
