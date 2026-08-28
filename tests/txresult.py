######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''A command reports success only when its frame was actually sent.

Every one of these methods hands a frame to transmit() and returns a bool. The
bool must follow the send: transmit() returns the number of bytes written, so a
closed or failing socket returns 0 and the command must report False and leave
local state alone.

The comparison is against len(frame.frame), the whole datagram. len(frame) is
the *payload* length, which is always 24 bytes short of what transmit() returns
and can therefore never equal it.
'''

import asyncio, os, struct, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.proto.Factory import create_mxr_frame

UID = bytes(range(1, 17))
ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False)
# construct() needs our own uid; start_async() would load it from disk, and a
# frame builder returns None without one.
mx._uid = bytes(range(0x20, 0x30))

def rx(opcode, payload=b''):
    mx.process_frame(0.0, create_mxr_frame(UID, opcode, payload), ADDR)

def name(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

feat = (1 << 5) | (1 << 6)
rx(0x00, struct.pack('<H', 0x28) + name('MX-1') + name('P8SN12345678')
        + name('5.0.0') + struct.pack('<I', feat))
dev = mx.get_by_uid(mx_remote.MxrDeviceUid(UID))

def bay(port, mode, num, nm):
    return bytes([port, mode, num, 0, 0]) + name(nm) + name(nm) + name('1080p') \
         + struct.pack('<I', 0) + struct.pack('<I', (1 << 1) if mode == 0 else (1 << 0))
rx(0x02, bay(0, 0, 0, 'In 1') + bay(1, 1, 0, 'Out 1'))
out = dev.get_by_portnum(1)
print('output bay  :', out)
assert out is not None and out.is_output

sent = []
def wire(ok):
    '''Stand in for the socket: full write when ok, nothing written when not.'''
    def tx(data):
        sent.append(data)
        return len(data) if ok else 0
    mx.transmit = tx

# a frame's own length must be what a successful send returns
f = create_mxr_frame(UID, 0x0E, b'\x01\x02\x03')
print('frame bytes :', len(f), 'payload len field:', int.from_bytes(f[22:24], 'little'))
assert len(f) != int.from_bytes(f[22:24], 'little'), 'payload len must not equal frame len'

# State is asserted through hidden and user_name, which mirror what the setter
# wrote. power_status is derived from availability and signal detection as well,
# so it is not a witness for whether a command was applied.

# ---- success path: the command reports success and the state advances
wire(True)
assert asyncio.run(out.power_on()) is True, 'power_on must report success on a full write'
print('power_on    : True on a full write')

wire(True)
assert asyncio.run(out.set_hidden(True)) is True
assert out.hidden is True
print('set_hidden  : True, state applied')

wire(True)
assert asyncio.run(out.set_name('Renamed')) is True
assert out.user_name == 'Renamed'
print('set_name    : True, state applied')

# ---- failure path: nothing written, so nothing may be claimed or cached
wire(False)
assert asyncio.run(out.set_hidden(False)) is False, 'a failed send must report False'
assert out.hidden is True, 'a failed send must not update local state'
print('set_hidden  : False on a failed send, state untouched')

wire(False)
assert asyncio.run(out.set_name('Nope')) is False, 'a failed send must report False'
assert out.user_name == 'Renamed', 'a failed send must not update local state'
print('set_name    : False on a failed send, state untouched')

wire(False)
assert asyncio.run(out.power_off()) is False, 'a failed send must report False'
print('power_off   : False on a failed send')

wire(False)
assert asyncio.run(out.tx_action(mx_remote.RCAction.ACTION_POWER_ON)) is False
print('tx_action   : False on a failed send')

# ---- Device-level commands take the same path, and hold most of the call sites
# (19 of the 25), so a Bay-only suite would leave them unguarded.
assert dev.rebooting is False, 'device must not start out rebooting'
wire(False)
assert asyncio.run(dev.reboot()) is False, 'a failed send must report False'
assert dev.rebooting is False, 'a failed send must not mark the device rebooting'
print('reboot      : False on a failed send, state untouched')

wire(True)
assert asyncio.run(dev.reboot()) is True, 'reboot must report success on a full write'
assert dev.rebooting is True, 'a sent reboot must mark the device rebooting'
print('reboot      : True, state applied')

print('frames handed to the wire:', len(sent))
assert len(sent) == 9
print('ALL OK')
