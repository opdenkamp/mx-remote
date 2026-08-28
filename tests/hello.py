######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''A client announces itself on a clock, not when something arrives.

MatrixOS sends SYS_HELLO from its probe loop every 2.5s + random(0..2.5s),
re-drawn after each send and independent of received traffic. A client that
announces only on receipt is invisible to a silent mesh: nothing arrives, so it
never speaks, so nothing learns it is there.

This drives the real periodic loop rather than the pieces under it. Asserting
that "is it due" works and that tx_hello sends proves nothing about whether
anything ever asks.
'''

import asyncio, os, sys, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.proto.Factory import create_mxr_frame
from mx_remote.remote import Remote as RemoteModule

# keep the wall-clock cost down without touching the loop being tested
RemoteModule.MXR_HELLO_INTERVAL_MIN = 0.1
RemoteModule.MXR_HELLO_INTERVAL_RAND = 0.1

HELLO = 0x00

def opcode(frame):
    return int.from_bytes(frame[20:22], 'little')

async def run(seconds, wire_ok=True):
    mx = mx_remote.Remote(open_connection=False)
    mx._uid = bytes(range(0x20, 0x30))
    sent = []
    mx.transmit = lambda data: (sent.append(data), len(data) if wire_ok else 0)[1]
    task = asyncio.ensure_future(mx._background_probe())
    await asyncio.sleep(seconds)
    mx._closing = True
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    return mx, [f for f in sent if opcode(f) == HELLO]

# ---- a silent network: nothing is fed in, and it must still announce, repeatedly
mx, hellos = asyncio.run(run(3.5))
print('silent network, 3.5s: %d hellos' % len(hellos))
assert len(hellos) >= 2, 'a client must keep announcing with no traffic arriving'

# ---- arriving datagrams must not announce, asserted by behaviour rather than by
# name. Checking that "tx_hello" is absent from on_datagram_received passes the
# moment the method is renamed, while the receipt-driven path is back in place.
def announces_on_receipt():
    mx = mx_remote.Remote(open_connection=False)
    mx._uid = bytes(range(0x20, 0x30))
    mx._hello_due = time.time() + 3600          # nothing is due on the clock
    sent = []
    mx.transmit = lambda data: (sent.append(data), len(data))[1]
    peer = bytes(range(1, 17))
    for _ in range(20):
        mx.on_datagram_received(create_mxr_frame(peer, 0x01, b''), ('192.0.2.9', 8812))
    return [f for f in sent if opcode(f) == HELLO]

on_receipt = announces_on_receipt()
print('20 datagrams, nothing due: %d hellos' % len(on_receipt))
assert len(on_receipt) == 0, 'arriving traffic must not trigger an announcement'

# ---- a hello that did not go out does not buy the next interval, as in firmware
mx, hellos = asyncio.run(run(2.5, wire_ok=False))
print('failing wire, 2.5s : %d attempts' % len(hellos))
assert len(hellos) >= 2, 'a send that wrote nothing must be retried, not treated as done'

# ---- the interval is re-drawn per send rather than fixed
mx2 = mx_remote.Remote(open_connection=False)
mx2._uid = bytes(range(0x20, 0x30))
mx2.transmit = lambda data: len(data)
# Measure the interval, not the due timestamp: _hello_due moves every call because
# the clock advances, so counting distinct timestamps says nothing about whether
# anything was drawn.
deltas = []
for _ in range(40):
    before = time.time()
    mx2._arm_hello()
    deltas.append(mx2._hello_due - before)
spread = max(deltas) - min(deltas)
print('interval spread    : %.4fs over 40 draws (rand range %.2fs)'
      % (spread, RemoteModule.MXR_HELLO_INTERVAL_RAND))
assert spread > RemoteModule.MXR_HELLO_INTERVAL_RAND * 0.3, \
    'the interval must be re-drawn per send, not fixed'
assert min(deltas) >= RemoteModule.MXR_HELLO_INTERVAL_MIN, 'a draw must never be shorter than the minimum'

print('ALL OK')
