"""Enter where the runtime enters.

on_datagram_received is what ConnectionAsync calls. process_frame is one level
below it and is what a test reaches for, because it takes the arguments a test
already has - so a layer that only the runtime touches goes uncovered while the
suite looks like it exercises the receive path.

Here that layer re-announces this client's hello. It has one other caller, at
startup, so if it stopped working the client would announce once and then go
silent to every peer that started later.
"""
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import logging
logging.disable(logging.CRITICAL)

import mx_remote
from mx_remote.Uid import MxrDeviceUid
from mx_remote.proto.Factory import create_mxr_frame

UID = bytes(range(1, 17))
ADDR = ('192.0.2.9', 8812)

class RecordingConn:
    """Stands in for ConnectionAsync so transmits can be counted."""
    def __init__(self):
        self.sent = []
    def transmit(self, data):
        self.sent.append(data)
        return len(data)

def nm(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

HELLO = (struct.pack('<H', 0x28) + nm('MX-1') + nm('P8SN12345678') + nm('4.7.9')
         + struct.pack('<I', 1 << 5))

def opcode_of(frame):
    return int.from_bytes(frame[20:22], 'little')

mx = mx_remote.Remote(open_connection=False)
mx._uid = bytes(range(100, 116))
conn = RecordingConn()
mx.conn = conn

# a datagram arriving must be decoded, not merely counted
mx.on_datagram_received(create_mxr_frame(UID, 0x00, HELLO), ADDR)
assert mx.get_by_uid(MxrDeviceUid(UID)) is not None, 'the datagram was not processed'
print('entry : a datagram reaching on_datagram_received is decoded')

# and it must re-announce once the interval has passed
conn.sent.clear()
mx._last_hello = time.time() - 31
mx.on_datagram_received(create_mxr_frame(UID, 0x00, HELLO), ADDR)
hellos = [f for f in conn.sent if opcode_of(f) == 0x00]
assert hellos, 'no hello re-announced; this client would go silent to later peers'
print('entry : hello re-announced after the interval')

# not on every datagram, or the mesh floods
conn.sent.clear()
mx.on_datagram_received(create_mxr_frame(UID, 0x00, HELLO), ADDR)
assert not [f for f in conn.sent if opcode_of(f) == 0x00], 'hello sent again inside the interval'
print('entry : and not again inside it')

print()
print('ALL OK')
