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

# ---- a send that raises must not end the loop. This loop is now the only thing
# that announces and the only thing that drives discovery, so a task that dies on
# a transient socket error silences the client for good.
async def survives_raising_transmit():
    mx = mx_remote.Remote(open_connection=False)
    mx._uid = bytes(range(0x20, 0x30))
    sent = []
    state = {'raise': True}
    def wire(data):
        if state['raise']:
            raise OSError('network is unreachable')
        sent.append(data)
        return len(data)
    mx.transmit = wire
    task = asyncio.ensure_future(mx._background_probe())
    await asyncio.sleep(2.2)
    alive_while_failing = not task.done()
    state['raise'] = False          # the socket comes back
    await asyncio.sleep(2.2)
    mx._closing = True
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    return alive_while_failing, [f for f in sent if opcode(f) == HELLO]

alive, recovered = asyncio.run(survives_raising_transmit())
print('raising wire       : loop alive=%s, hellos after recovery=%d' % (alive, len(recovered)))
assert alive, 'a raising send must not end the probe loop'
assert len(recovered) >= 1, 'the client must announce again once sending works'

# ---- a task that dies must say so. asyncio only reports an unretrieved task
# exception when the task object is collected, which is a different moment and may
# never come, so without this a background task dies in silence. Driven through
# start_async so the real registration is what is under test, not _on_task_done.
class Boom(BaseException):
    """Not an Exception, so the loop's own guard does not catch it."""

class FakeConn:
    def __init__(self):
        self.sent = []
    async def start_srv(self):
        return (None, None)
    def transmit(self, data):
        self.sent.append(data)
        return len(data)
    def close(self):
        pass

async def dying_task_is_reported():
    records = []
    class Catch(logging.Handler):
        def emit(self, rec):
            records.append(rec)
    handler = Catch()
    logging.disable(logging.NOTSET)
    log = logging.getLogger('mx_remote.remote.Remote')
    prev_level, prev_prop = log.level, log.propagate
    # do not propagate: with logging re-enabled these records would reach the root
    # handler and print to stderr, in the middle of whatever suite is running
    log.propagate = False
    log.addHandler(handler); log.setLevel(logging.DEBUG)
    try:
        mx = mx_remote.Remote(open_connection=False)
        mx._uid = bytes(range(0x20, 0x30))
        mx.conn = FakeConn()
        mx._probe_once = lambda: (_ for _ in ()).throw(Boom('probe exploded'))
        await mx.start_async()
        await asyncio.sleep(1.6)
        task = next(iter(mx._tasks), None)
        died = [r for r in records if r.levelno >= logging.ERROR and 'died' in r.getMessage()]
        return died
    finally:
        # remove the instance, not the class: passing the class leaves the handler
        # attached, and the logger keeps emitting into every suite that runs after
        log.removeHandler(handler)
        log.setLevel(prev_level)
        log.propagate = prev_prop
        logging.disable(logging.CRITICAL)

died = asyncio.run(dying_task_is_reported())
print('task killed by a BaseException: %d error(s) logged' % len(died))
assert len(died) >= 1, 'a background task that dies must be reported, not vanish'

# ---- a client must announce itself before it can be heard. A device drops
# every frame from a uid it has no record of, except hello and discover, so a
# command sent between start_async returning and the probe loop's first pass
# would be dropped by every peer - and nothing answers a frame it discarded, so
# the caller sees success. The announce has to be on the way out of start_async,
# not one probe interval later.
async def announces_on_start():
    mx = mx_remote.Remote(open_connection=False)
    mx._uid = bytes(range(0x40, 0x50))
    conn = FakeConn()
    mx.conn = conn
    mx._probe_once = lambda: None          # the loop must not be what sends these
    await mx.start_async()
    return [d[20] | (d[21] << 8) for d in conn.sent]

opcodes = asyncio.run(announces_on_start())
print('opcodes sent by start_async: %s' % [hex(o) for o in opcodes])
assert 0x00 in opcodes, 'start_async must announce this client before anything else is sent'
assert 0x01 in opcodes, 'start_async must solicit, rather than wait out each peer announce interval'

# ---- a disconnected interface must not bury the log in identical tracebacks
async def one_traceback_then_quiet():
    records = []
    class Catch(logging.Handler):
        def emit(self, rec):
            records.append(rec)
    handler = Catch()
    logging.disable(logging.NOTSET)
    log = logging.getLogger('mx_remote.remote.Remote')
    prev_level, prev_prop = log.level, log.propagate
    # do not propagate: with logging re-enabled these records would reach the root
    # handler and print to stderr, in the middle of whatever suite is running
    log.propagate = False
    log.addHandler(handler); log.setLevel(logging.DEBUG)
    try:
        mx = mx_remote.Remote(open_connection=False)
        mx._uid = bytes(range(0x20, 0x30))
        mx.transmit = lambda data: (_ for _ in ()).throw(OSError('network is unreachable'))
        task = asyncio.ensure_future(mx._background_probe())
        await asyncio.sleep(3.2)
        mx._closing = True
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return [r for r in records if r.levelno >= logging.WARNING]
    finally:
        log.removeHandler(handler)
        log.setLevel(prev_level)
        log.propagate = prev_prop
        logging.disable(logging.CRITICAL)

warns = asyncio.run(one_traceback_then_quiet())
print('3 failing ticks    : %d warning(s)' % len(warns))
assert len(warns) == 1, 'only the first failure carries a traceback; repeats must not flood'

print('ALL OK')
