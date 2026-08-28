######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Applying the same frame twice must not change anything the second time.

Frames arrive more than once, for two reasons that reach a client differently.

Devices do send some frames twice, to the multicast group and to the subnet
broadcast address - hello and discover always, and everything else from a device
that has a peer needing broadcast. Today that pair does not reach this library,
because the copies go to different ports, 8812 and 8811, and a connection binds
one of them. That is a property of binding a single port per mode, not of the
protocol: a client that binds both receives hello twice, and firmware does bind
both. So this is a reason the duplication below is not worse than it is, not a
reason it cannot happen.

What does reach us is duplication on a single path. One route change puts two
identical 0x08 frames on the wire, measured 0.11s to 0.43s apart. And a device
re-broadcasts unchanged state on its periodic cycle, which is the same bytes
again seconds or minutes later. Newer firmware deduplicates received frames
within a 100ms window, which by design does not touch either case: the paired
transmission is two genuine sends, and a periodic re-broadcast is far outside
the window.

So a handler must be safe to run twice on the same bytes. Each case asserts the
first application changed something and the second changed nothing - the first
half matters, because a case that changes nothing at all would pass the second
assertion on its own and prove that a handler is idempotent by never running it.

The exception is deliberate and pinned below: a keypress is an event, not state.
'''

import collections, logging, os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.Uid import MxrDeviceUid
from mx_remote.proto.Factory import create_mxr_frame
from mx_remote.proto.Constants import BayFeaturesMask

fired = collections.Counter()
class Counting(mx_remote.MxrCallbacks):
    pass
for _name in [m for m in dir(mx_remote.MxrCallbacks) if m.startswith('on_')]:
    def _make(n):
        def hook(self, *a, **k):
            fired[n] += 1
        return hook
    setattr(Counting, _name, _make(_name))

UID, PEER = bytes(range(1, 17)), bytes(range(60, 76))
ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False, callbacks=Counting())
mx._uid = bytes(range(100, 116))

def nm(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))
def rx(op, pl=b''):
    mx.process_frame(time.time(), create_mxr_frame(UID, op, pl), ADDR)

FEAT = (1 << 5) | (1 << 6) | (1 << 7) | (1 << 9)
rx(0x00, struct.pack('<H', 0x28) + nm('MX-1') + nm('P8SN12345678') + nm('5.3.0')
        + struct.pack('<I', FEAT))
dev = mx.get_by_uid(MxrDeviceUid(UID))
AUD = int(BayFeaturesMask.AUDIO_ANA_OUT)
def bay_rec(port, mode, num, name, feat=None):
    if feat is None:
        feat = (1 << 1) if mode == 0 else (1 << 0)
    return (bytes([port, mode, num, 0, 0]) + nm(name) + nm(name) + nm('1080p')
            + struct.pack('<I', 0) + struct.pack('<I', feat))
# two inputs, so a routing frame can select a source the bay is not already on
rx(0x02, bay_rec(0, 0, 0, 'In 1') + bay_rec(2, 0, 1, 'In 3')
       + bay_rec(1, 1, 0, 'Out 1', feat=AUD))

def snapshot():
    '''Everything a handler in this suite can reach, as a comparable value.'''
    out = [dev.serial, dev.name, str(dev.dolby_settings), str(dev.temperatures),
           str(dev.network_status), repr(getattr(dev, '_topology', None)),
           # the v2ip source list, which 0x26 writes and nothing else in the
           # snapshot would show
           repr([str(x) for x in (getattr(dev, '_v2ip_sources', None) or [])])]
    for port, b in sorted(dev.bays.items()):
        out += [port, b.user_name, b.hidden, b.signal_detected, b.signal_type,
                b.hpd_detected, str(b.power_status), str(b.volume_status),
                str(b.mirroring), str(b.filtered), str(b.video_details),
                getattr(b.video_source, 'user_name', None),
                getattr(b.audio_source, 'user_name', None)]
    return repr(out)

def apply_twice(label, op, payload):
    '''Return (changed on first, changed on second) as (callbacks, state) pairs.'''
    before = snapshot(); fired.clear()
    rx(op, payload)
    mid = snapshot(); first = (sum(fired.values()), mid != before)
    fired.clear()
    rx(op, payload)
    after = snapshot(); second = (sum(fired.values()), after != mid)
    return first, second

CASES = [
    ('0x02 bay config',     0x02, bay_rec(0, 0, 0, 'Renamed')),
    ('0x23 bay config 2nd', 0x23, bay_rec(3, 0, 2, 'In 4')),
    ('0x03 links',          0x03, bytes([0, 0]) + nm('P8SN00000001') + nm('Out 1')
                                  + struct.pack('<I', 1)),
    ('0x04 connect',        0x04, bytes([1, 1])),
    ('0x05 power',          0x05, bytes([1, 1])),
    ('0x06 signal',         0x06, bytes([0, 1]) + b'1920x1080p60\x00'),
    ('0x08 routing change', 0x08, struct.pack('<HHH', 1, 2, 2) + bytes([0]) + struct.pack('<H', 2)),
    ('0x12 volume',         0x12, bytes([1, 40, 41, 0])),
    ('0x15 temperature',    0x15, bytes([2, 41, 42])),
    ('0x27 bay hide',       0x27, UID + struct.pack('<H', 0) + bytes([1])),
    ('0x26 v2ip sources',   0x26, UID + b''.join(
        bytes(int(x) for x in ip.split('.')) + struct.pack('<H', port) + bytes(2)
        for ip, port in (('239.7.7.1', 50020), ('239.7.7.2', 50022), ('239.7.7.3', 50021)))),
    ('0x30 topology',       0x30, PEER + struct.pack('<I', 3)),
    ('0x32 mirror',         0x32, UID + PEER),
    ('0x38 filter',         0x38, UID + PEER),
    ('0x3E amp dolby',      0x3E, UID + bytes([2, 0b11])),
]

print('%-22s %-24s %s' % ('frame', 'first (cbs, state)', 'second (cbs, state)'))
for label, op, payload in CASES:
    first, second = apply_twice(label, op, payload)
    print('%-22s %-24s %s' % (label, first, second))
    assert first != (0, False), f'{label}: first application changed nothing, so this case tests nothing'
    assert second == (0, False), f'{label}: acted on the repeat -> {second}'

# ---- the deliberate exception, pinned so a change in either direction shows up.
# A keypress is an event and the frame carries no sequence number, so a repeat is
# indistinguishable from a real second press. Firmware does not deduplicate by
# content either. Swallowing one here would drop genuine repeats, which is worse
# than delivering a duplicate, so this fires twice on purpose.
fired.clear(); rx(0x0B, struct.pack('<H', 1) + struct.pack('<H', int(mx_remote.RCKey.KEY_5)))
once = fired.get('on_key_pressed', 0)
fired.clear(); rx(0x0B, struct.pack('<H', 1) + struct.pack('<H', int(mx_remote.RCKey.KEY_5)))
twice = fired.get('on_key_pressed', 0)
print('\n0x0B rc key            fires per frame: %d then %d (edge-triggered by design)' % (once, twice))
assert once == 1 and twice == 1, 'a keypress must be delivered every time it arrives'

# ---- the guards above only suppress a repeat if the values they compare know
# how to compare. A value class without __eq__ falls back to identity, every
# frame builds a fresh instance, and the guard silently never fires. Asserted
# directly: the frame cases cannot see it, because the guards it defeats reach
# internal device callbacks rather than the public callback surface.
from mx_remote.proto.V2IPConfig import V2IPStreamSourceImpl, V2IPStreamSourcesImpl

def two(make):
    return make(), make()

a, b = two(lambda: V2IPStreamSourceImpl('video', bytes([239, 1, 1, 1, 0x44, 0xC3])))
assert a is not b and a == b, 'a stream source must compare by address, not identity'
c = V2IPStreamSourceImpl('video', bytes([239, 1, 1, 2, 0x44, 0xC3]))
assert a != c, 'different addresses must not compare equal'

x, y = two(lambda: V2IPStreamSourcesImpl(video=a, audio=a, anc=a))
assert x is not y and x == y and [x] == [y], 'a source list must compare element-wise'

def amp(cls, **over):
    o = cls()
    for n in cls.__annotations__:
        setattr(o, n, over.get(n, 0))
    return o
for cls, field in ((mx_remote.AmpDolbySettings, 'mode'), (mx_remote.AmpZoneSettings, 'gain_left')):
    p1, p2 = amp(cls), amp(cls)
    assert p1 is not p2 and p1 == p2, f'{cls.__name__} must compare by value'
    assert p1 != amp(cls, **{field: 7}), f'{cls.__name__} must notice a changed field'
print('value equality      : stream source, source list, and both amp settings types')

print('\nALL OK')
