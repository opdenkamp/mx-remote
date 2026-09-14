######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''When a device counts as fully described, and what each half of that rests on.

Both halves are paged lists with nothing on the wire marking the last page: no
count, no index, no terminating frame. So neither can be tested by comparing
what arrived against what is still to come, and each rests on the list having
been sent at all.

The bays additionally need the primary list specifically, which every unit sends
whatever else it sends; the secondary one does not stand in for it.

Only the links stop being waited for. What a device withholds is reported the
same way as what it does not have, so a wait with no end hides a fault rather
than reporting one - but a bay is what a caller names things after, and a name
assigned to a placeholder outlives the frame that would have corrected it. So
the window below releases the links, and is checked against the two halves it
must not release.

The two device shapes below are the geometry of real units, and each shows why a
count of bays is not the number of link records to expect. Both are built here
from frames rather than from mock bays, because the bay a record names is looked
up in the cache the bay frames fill: a test that sets the bays directly never
exercises the path that decides whether a record counts.
'''

import logging, os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.const import MXR_CONFIG_TIMEOUT
from mx_remote.Uid import MxrDeviceUid
from mx_remote.proto.Factory import create_mxr_frame

class Watching(mx_remote.MxrCallbacks):
    def __init__(self, sink):
        self.sink = sink
    def on_device_config_complete(self, dev):
        self.sink.append(dev)

completed = []
ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False, callbacks=Watching(completed))
mx._uid = bytes(range(100, 116))

# device features
VIDEO_ROUTING, AUDIO_ROUTING, VOLUME_CONTROL = (1 << 5), (1 << 6), (1 << 7)
V2IP_SOURCE, V2IP_SINK = (1 << 3), (1 << 4)
# bay features
HDMI_OUT, HDMI_IN = (1 << 0), (1 << 1)
V2IP_SOURCE_REMOTE, V2IP_SINK_REMOTE = (1 << 13), (1 << 14)

def nm(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))
def rx(uid, op, pl=b''):
    mx.process_frame(time.time(), create_mxr_frame(uid, op, pl), ADDR)
def hello(uid, name, serial, features):
    rx(uid, 0x00, struct.pack('<H', 0x28) + nm(name) + nm(serial) + nm('4.7.9')
                + struct.pack('<I', features))
    return mx.get_by_uid(MxrDeviceUid(uid))
def bay(port, mode, num, name, features=0):
    bayfeat = features | (HDMI_IN if mode == 0 else HDMI_OUT)
    return bytes([port, mode, num, 0, 0]) + nm(name) + nm(name) + nm('1080p') \
         + struct.pack('<I', 0) + struct.pack('<I', bayfeat)
def link(port, serial, baynm):
    return bytes([port, 0]) + nm(serial) + nm(baynm) + struct.pack('<I', 1)

MATRIX = bytes(range(1, 17))
dev = hello(MATRIX, 'MX-1', 'P8SN12345678', VIDEO_ROUTING | AUDIO_ROUTING)
assert dev is not None and dev.is_video_matrix
assert not dev.configuration_complete, 'a hello describes no bays'
print('complete    : a hello on its own is not a configuration')

# ---- the primary bay list, and only that one
# The secondary list registers the same bays, so after it the device knows every
# bay it will ever hear about and still has not heard the list that says so.
rx(MATRIX, 0x23, bay(0, 0, 0, 'In 1') + bay(1, 0, 1, 'In 2') + bay(2, 1, 0, 'Out 1'))
assert len(dev.bays) == 3, dev.bays
assert not dev.has_bays, 'the secondary list does not stand in for the primary one'
assert not dev.configuration_complete

rx(MATRIX, 0x02, bay(0, 0, 0, 'In 1') + bay(1, 0, 1, 'In 2'))
assert dev.has_bays, 'the primary list is what completes the bays'
assert len(dev.bays) == 3, 'a page is merged into the cache, never replaces it'
print('complete    : the bays need the primary list, whatever else arrived')

# ---- the links, reported
assert dev.need_link_config, 'no link configuration has arrived'
assert not dev.configuration_complete
assert not completed, 'nothing may be announced complete before the links are in'

rx(MATRIX, 0x03, link(0, 'P8SN00000001', 'Out 1'))
assert not dev.need_link_config, 'the device has reported its links'
assert dev.configuration_complete
print('complete    : the links need the list, and the list to have been sent')

# ---- announced once, at that moment
assert completed == [dev], completed
rx(MATRIX, 0x02, bay(0, 0, 0, 'In 1') + bay(1, 0, 1, 'In 2'))
rx(MATRIX, 0x03, link(0, 'P8SN00000001', 'Out 1'))
assert completed == [dev], 'a re-sent configuration must not announce completion again'
print('complete    : announced once, when the last of it arrived')

# ---- a V2IP transceiver: 14 bays, two of them its own
# Its remaining bays are proxies for streams on other devices. A link record
# describes one of the sender's own ports, so those twelve own no record and a
# count of bays is one no page will ever reach.
ONEIP = bytes(range(17, 33))
tz = hello(ONEIP, 'OneIP', 'P9SN66662814', V2IP_SOURCE | V2IP_SINK | VIDEO_ROUTING)
assert tz is not None and tz.is_v2ip
bays = bay(0, 0, 0, 'Input 1')
for port in range(1, 13):
    bays += bay(port, 0, port, f'Input {port + 1}', V2IP_SOURCE_REMOTE)
bays += bay(16, 1, 0, 'Output 1')
rx(ONEIP, 0x02, bays)
assert len(tz.bays) == 14, tz.bays
assert tz.nb_inputs + tz.nb_outputs == 14, 'every bay is an input or an output here'

# Its V2IP source list, which completion needs for a V2IP device in its own right.
rx(ONEIP, 0x26, bytes(40 * 13))
assert tz.v2ip_sources is not None and len(tz.v2ip_sources) == 13

assert tz.need_link_config and not tz.configuration_complete
rx(ONEIP, 0x03, link(0, 'P9SN66662903', 'Output 1') + link(16, 'P9SN66662903', 'Input 1'))
assert not tz.need_link_config, 'two records are this device\'s whole list'
assert tz.configuration_complete, 'a bay that owns no link record must not gate completion'
assert completed == [dev, tz], completed
print('complete    : a V2IP device reports links for its own two bays, not its fourteen')

# ---- an amplifier: 18 bays, 17 records, no second page
# The list is cut to what fits one payload rather than continued, so the last
# bay is never accounted for on any device.
AMP = bytes(range(33, 49))
amp = hello(AMP, 'PROAMP8', 'P9SN66667000', AUDIO_ROUTING | VOLUME_CONTROL)
assert amp is not None and amp.is_amp
bays = b''.join(bay(port, 0, port, f'Input {port + 1}') for port in range(9)) \
     + b''.join(bay(9 + num, 1, num, f'Output {num + 1}') for num in range(9))
rx(AMP, 0x02, bays)
assert len(amp.bays) == 18, amp.bays

records = b''.join(link(port, 'P9SN66662814', 'Output 1') for port in range(17))
assert len(records) == 646, 'the page a ProAmp8 sends, to the byte'
rx(AMP, 0x03, records)
assert not amp.need_link_config, 'the page the device sent is the list it has'
assert amp.configuration_complete, 'a bay left out of a cut list must not gate completion'
assert completed == [dev, tz, amp], completed
print('complete    : a cut list is the whole of what a device reports')

# ---- waiting for the links ends, and for nothing else
# Wind the clock back rather than sleeping, and drive it through the call the
# probe loop makes: no frame arrives when a window expires, so that call is the
# only thing that can announce it.
LATE = bytes(range(49, 65))
late = hello(LATE, 'MX-2', 'P8SN22222222', VIDEO_ROUTING | AUDIO_ROUTING)
assert late.need_link_config, 'inside the window the links are still awaited'
late._hello_received -= (MXR_CONFIG_TIMEOUT + 1)
assert not late.need_link_config, 'past it they are not'

rx(LATE, 0x23, bay(0, 0, 0, 'In 1'))
assert not late.has_bays and not late.configuration_complete, \
    'the window must not stand in for the primary bay list'
assert not late.check_configuration_complete_timeout(), 'a device still owing bays is still asked'
assert late not in completed, 'and nothing may name a bay it has not described'

rx(LATE, 0x02, bay(0, 0, 0, 'In 1'))
assert late.configuration_complete, 'the bays arrived, and the links are no longer awaited'
assert late.check_configuration_complete_timeout()
assert completed == [dev, tz, amp, late], completed
print('complete    : the links stop being waited for, the bays never do')

# A V2IP device owes its source list in its own right, which the window does not
# release either.
LATEV2IP = bytes(range(65, 81))
vl = hello(LATEV2IP, 'OneIP-2', 'P9SN66662905', V2IP_SOURCE | V2IP_SINK)
vl._hello_received -= (MXR_CONFIG_TIMEOUT + 1)
rx(LATEV2IP, 0x02, bay(0, 0, 0, 'Input 1') + bay(16, 1, 0, 'Output 1'))
assert vl.has_bays and not vl.need_link_config
assert not vl.configuration_complete, 'the window must not stand in for the V2IP source list'
assert not vl.check_configuration_complete_timeout()
assert vl not in completed

rx(LATEV2IP, 0x26, bytes(40 * 2))
assert vl.configuration_complete and vl.check_configuration_complete_timeout()
assert completed == [dev, tz, amp, late, vl], completed
print('complete    : nor does it stand in for a V2IP source list')

# Announced by the expiry alone, driven the way the runtime drives it. No frame
# arrives when a window closes, so the probe loop is the only thing that can
# notice, and the call it makes there is the whole of the announcement path.
stuck_seen = []
runtime = mx_remote.Remote(open_connection=False, callbacks=Watching(stuck_seen))
runtime._uid = bytes(range(100, 116))
runtime.transmit = lambda data: len(data)  # no socket; the loop's sends are not the subject

STUCK = bytes(range(81, 97))
def rx_runtime(op, pl):
    runtime.process_frame(time.time(), create_mxr_frame(STUCK, op, pl), ADDR)
rx_runtime(0x00, struct.pack('<H', 0x28) + nm('MX-3') + nm('P8SN33333333') + nm('4.7.9')
                + struct.pack('<I', VIDEO_ROUTING | AUDIO_ROUTING))
stuck = runtime.get_by_uid(MxrDeviceUid(STUCK))
rx_runtime(0x02, bay(0, 0, 0, 'In 1'))

runtime._probe_once()
assert not stuck.configuration_complete
assert stuck_seen == [], 'inside the window the loop announces nothing'

stuck._hello_received -= (MXR_CONFIG_TIMEOUT + 1)
runtime._probe_once()
assert stuck_seen == [stuck], 'the loop announces a device no further frame will complete'
print('complete    : announced from the probe loop, on the expiry alone')

print()
print('ALL OK')
