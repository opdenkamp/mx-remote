######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''A device that stops answering, and who notices.

Nothing on the wire marks a device gone: it simply stops pinging, and the probe
loop comparing its last ping against the clock is the only thing that can tell.
So a pass the loop skips is not a late report, it is none - the device stays
online in the registry for as long as the client runs, and a caller reading
`online` is told it is there.

Which makes the interesting client the one where nothing has completed. A device
drops off in whatever state it reached, including before it ever described
itself, and a client whose devices are all in that state is exactly the one with
no completed device to ride along with.

The hello here carries no bay configuration on purpose. That is what keeps
`configuration_complete` false for the life of the test, so the pass cannot be
reached by way of a device that finished.
'''

import logging, os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.Uid import MxrDeviceUid
from mx_remote.proto.Factory import create_mxr_frame
from datetime import timedelta

UID = bytes(range(1, 17))
ADDR = ('192.0.2.9', 8812)

changes = []
class Watching(mx_remote.MxrCallbacks):
    def on_device_online_status_changed(self, dev, online):
        changes.append((dev, online))

def nm(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

mx = mx_remote.Remote(open_connection=False, callbacks=Watching())
mx._uid = bytes(range(100, 116))
mx.transmit = lambda data: len(data)  # no socket; the loop's sends are not the subject

# Protocol 0x28, so the 15s ping window applies rather than the 120s one.
mx.process_frame(time.time(), create_mxr_frame(
    UID, 0x00, struct.pack('<H', 0x28) + nm('MX-1') + nm('P8SN12345678') + nm('4.7.9')
             + struct.pack('<I', (1 << 5) | (1 << 6))), ADDR)
dev = mx.get_by_uid(MxrDeviceUid(UID))
assert dev is not None and dev.online and dev.protocol >= 0x20

# Nothing has completed and nothing will: the hello described no bays.
mx._probe_once()
assert not mx.has_completed_devices(), 'a hello on its own describes no bays'
assert changes == [], 'a device that is answering is not a change'
print('offline     : a device inside its ping window is left alone')

# Stop answering. Only the clock says so - no frame reports this.
dev._last_ping -= timedelta(seconds=16)
assert not dev.online, 'the ping window has passed'
assert changes == [], 'and nothing has reported it yet'

mx._probe_once()
assert changes == [(dev, False)], \
    'the loop must report a device gone even when no device has completed'
assert not dev.configuration_complete, 'which is still the state it went offline in'
print('offline     : reported gone with no completed device to ride along with')

# Once only, and the state it left behind is the one a caller reads.
mx._probe_once()
assert changes == [(dev, False)], 'a device already gone is not a change'
print('offline     : reported once, not once per pass')

# Answering again is the other direction, and has to come back through the same
# pass: a device that returns while still describing nothing is the same client.
dev._last_ping = dev._last_ping + timedelta(seconds=16)
mx._probe_once()
assert changes == [(dev, False), (dev, True)], changes
print('offline     : and back again, through the same pass')

# A management client sends no bays or links, so waiting for them never ends:
# it has to count as described, or every client that sees one discovers forever.
MANAGER = bytes(range(33, 49))
mx.process_frame(time.time(), create_mxr_frame(
    MANAGER, 0x00, struct.pack('<H', 0x29) + nm('MXR Python') + nm('P9SN00000000') + nm('5.9.1')
             + struct.pack('<I', (1 << 19))), ADDR)
assert mx.get_by_uid(MxrDeviceUid(MANAGER)).configuration_complete, 'a manager has nothing more to send'
print('offline     : a management client counts as described')

print()
print('ALL OK')
