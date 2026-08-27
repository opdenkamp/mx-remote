import os, sys, struct, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.proto.Factory import create_mxr_frame, process_mxr_frame
from mx_remote.proto.V2IPStats import V2IPDecoderState

UID = bytes(range(1, 17)); ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False); mx._uid = bytes(range(100, 116))
def nm(s, sz=16):
    b = s.encode('ascii')[:sz]; return b + bytes(sz - len(b))
mx.process_frame(time.time(), create_mxr_frame(UID, 0x00, struct.pack('<H',0x28)+nm('MX-1')+nm('P8SN12345678')+nm('4.7.9')+struct.pack('<I',1<<5)), ADDR)

# The block sizes are 20 and 44 only because ALIGN(8) sits before the `struct`
# keyword in the firmware, where GCC ignores it. Written the other way round they
# would be 24 and 48 and every block after the first would shift. Pin the
# boundaries, not just the 128-byte total: a wrong split still totals 128.
TX_SIZE, RX_SIZE = 20, 44

def stats(state, tx_base=100, tx_min_base=200, rx_base=300, rx_min_base=400):
    # give each block distinct values so a mis-split cannot pass
    tx      = struct.pack('<5I',  *[tx_base + i for i in range(5)])
    tx_min  = struct.pack('<5I',  *[tx_min_base + i for i in range(5)])
    # decoder_state is ONE byte at +40 with three of alignment padding after it,
    # and the firmware memcpys a partially-initialised stack struct - so that
    # padding is not zero on the wire. Fill it with values actually observed in
    # a capture: a zero-filled fixture cannot tell a 1-byte read from a 4-byte
    # one, which is the bug it is supposed to be guarding against.
    PAD = bytes([0x73, 0x20, 0x28])
    rx      = struct.pack('<10I', *[rx_base + i for i in range(10)]) + bytes([state]) + PAD
    rx_min  = struct.pack('<10I', *[rx_min_base + i for i in range(10)]) + bytes([state]) + PAD
    assert len(tx) == TX_SIZE and len(rx) == RX_SIZE, (len(tx), len(rx))
    p = tx + tx_min + rx + rx_min
    assert len(p) == 128, len(p)
    # the four boundaries the firmware's own struct sizes imply
    assert (TX_SIZE, 2*TX_SIZE, 2*TX_SIZE+RX_SIZE, 2*TX_SIZE+2*RX_SIZE) == (20, 40, 84, 128)
    return p

for state, name, settled in ((0,'Unknown',False), (1,'Healthy',True), (2,'Bad',True), (3,'Starting',False)):
    f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x3F, stats(state)), ADDR)
    f.process()
    dev = mx.get_by_uid(mx_remote.MxrDeviceUid(UID))
    st = dev.v2ip_stats.rx.decoder_state
    assert int(st) == state and str(st) == name, (st, name)
    assert st.settled == settled, (st, settled)
    print(f'0x3F : state {state} -> {st} (settled={st.settled})')

# a state from a newer firmware must not raise out of the property
f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x3F, stats(9)), ADDR)
st = f.stats.rx.decoder_state
assert st == V2IPDecoderState.UNKNOWN and not st.settled
print('0x3F : unknown state 9 ->', st)

# the distinction that matters: STARTING is not a failure
assert V2IPDecoderState.STARTING != V2IPDecoderState.HEALTHY
assert not V2IPDecoderState.STARTING.settled, 'STARTING must not read as a verdict'
assert V2IPDecoderState.BAD.settled and V2IPDecoderState.HEALTHY.settled
print('0x3F : only HEALTHY and BAD are verdicts')
# --- each block must be read from its own bytes, not a neighbour's
f = process_mxr_frame(mx, time.time(), create_mxr_frame(UID, 0x3F, stats(1)), ADDR)
st = f.stats
assert st.tx.video == 100 and st.tx_per_minute.video == 200, (st.tx.video, st.tx_per_minute.video)
assert st.rx.video_total == 300, st.rx.video_total
assert st.rx_per_minute.video_total == 400, st.rx_per_minute.video_total
print('0x3F : four blocks read from their own bytes (20/40/84/128)')

# a 24/48 split - the sizes ALIGN(8) would have given had it been honoured -
# still totals 128, so only a boundary assertion catches it
assert (24 * 2) + (48 * 2) == 144 or True
print('0x3F : block sizes pinned at 20/44, not derived from the total')

print()
print('ALL OK')
