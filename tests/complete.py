######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''When a device counts as fully described, and what each half of that rests on.

Both halves are paged lists with nothing on the wire marking the last page: no
count, no index, no terminating frame. So neither can be tested by comparing
what arrived against what is still to come, and each needs a test of its own
shape.

The bays: that the primary list was sent at all, which every unit sends whatever
else it sends. The links: one record per bay, so a record for every input and
output is the whole list.

A device re-sends its configuration, so every assertion below has to survive the
same frame twice. That is what makes the link half a set of ports rather than a
count - one page repeated would otherwise stand in for the pages behind it.
'''

import logging, os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.Uid import MxrDeviceUid
from mx_remote.proto.Factory import create_mxr_frame

completed = []
class Watching(mx_remote.MxrCallbacks):
    def on_device_config_complete(self, dev):
        completed.append(dev)

UID = bytes(range(1, 17))
ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False, callbacks=Watching())
mx._uid = bytes(range(100, 116))

def nm(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))
def rx(op, pl=b''):
    mx.process_frame(time.time(), create_mxr_frame(UID, op, pl), ADDR)
def bay(port, mode, num, name):
    return bytes([port, mode, num, 0, 0]) + nm(name) + nm(name) + nm('1080p') \
         + struct.pack('<I', 0) + struct.pack('<I', (1 << 1) if mode == 0 else (1 << 0))
def link(port, serial, baynm):
    return bytes([port, 0]) + nm(serial) + nm(baynm) + struct.pack('<I', 1)

# A video matrix, so it is a device that reports links at all.
FEAT = (1 << 5) | (1 << 6)
rx(0x00, struct.pack('<H', 0x28) + nm('MX-1') + nm('P8SN12345678') + nm('4.7.9')
        + struct.pack('<I', FEAT))
dev = mx.get_by_uid(MxrDeviceUid(UID))
assert dev is not None and dev.is_video_matrix
assert not dev.configuration_complete, 'a hello describes no bays'
print('complete    : a hello on its own is not a configuration')

# ---- the primary bay list, and only that one
# The secondary list registers the same bays, so after it the device knows every
# bay it will ever hear about and still has not heard the list that says so.
rx(0x23, bay(0, 0, 0, 'In 1') + bay(1, 0, 1, 'In 2') + bay(2, 1, 0, 'Out 1'))
assert len(dev.bays) == 3, dev.bays
assert not dev.has_bays, 'the secondary list does not stand in for the primary one'
assert not dev.configuration_complete

rx(0x02, bay(0, 0, 0, 'In 1') + bay(1, 0, 1, 'In 2'))
assert dev.has_bays, 'the primary list is what completes the bays'
assert len(dev.bays) == 3, 'a page is merged into the cache, never replaces it'
print('complete    : the bays need the primary list, whatever else arrived')

# ---- one link record per bay
assert dev.need_link_config, 'no record has arrived'
assert not dev.configuration_complete

# The same page three times. A count would reach the three records this device
# owes; the ports say one bay has reported and two have not.
for _ in range(3):
    rx(0x03, link(0, 'P8SN00000001', 'Out 1'))
assert dev.need_link_config, 'a repeated page must not stand in for the pages behind it'

# A record for a bay this device never advertised is not one of the three.
rx(0x03, link(9, 'P8SN00000001', 'Out 1'))
assert dev.need_link_config, 'a record on an unknown bay counts for nothing'

rx(0x03, link(1, 'P8SN00000002', 'Out 2'))
assert dev.need_link_config, 'two of three bays have reported'
assert not dev.configuration_complete
assert not completed, 'nothing may be announced complete while a record is missing'

rx(0x03, link(2, 'P8SN00000003', 'In 1'))
assert not dev.need_link_config, 'every bay has reported its link record'
assert dev.configuration_complete
print('complete    : one record per bay, counted per bay and not per page')

# ---- announced once, at that moment
assert completed == [dev], completed
rx(0x02, bay(0, 0, 0, 'In 1') + bay(1, 0, 1, 'In 2'))
rx(0x03, link(0, 'P8SN00000001', 'Out 1'))
assert completed == [dev], 'a re-sent configuration must not announce completion again'
print('complete    : announced once, when the last of it arrived')

print()
print('ALL OK')
