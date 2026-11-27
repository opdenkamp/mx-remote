######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''A client joined to a OneIP controller's driver proxy.

The fixtures are the controller's own published vectors (driver-proxy.md
section 8, pinned by the controller's the_published_fixtures_hold): the inputs,
both proofs, both session keys, and every join frame plus a sealed INFO and a
sealed driver hello as whole datagrams. A join driven by them must send exactly
the driver's datagrams in them, which no fixture this library built could show.

Needs the mx_remote[proxy] extra; the suite says so and stops without it.
'''

import asyncio, os, struct, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import MxrDeviceUid, ProxyConfig, ProxyStatus, DeviceFeature
from mx_remote.remote import Proxy
from mx_remote.remote.Proxy import (ProxyLink, ProxyConnection, ReplayWindow, controller_proof, driver_proof,
                                    proxy_available, seal, session_keys, unseal)
from mx_remote.proto.FrameProxy import proxy_frame
from mx_remote.proto.Factory import create_mxr_frame

if not proxy_available():
    print('mx_remote[proxy] is not installed: pip install .[proxy]')
    sys.exit(1)

h = bytes.fromhex
K  = h('000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f')
ND = h('101112131415161718191a1b1c1d1e1f')
NC = h('202122232425262728292a2b2c2d2e2f')
UD = h('d0' * 16)
UC = h('c0' * 16)
MESH = h('c1' * 16)
DRIVER_PROOF = h('f22e793df352fff4d76660875d67c080378813eb426ed89d739ac2eac0c6fa2b')
CONTROLLER_PROOF = h('e8dd2bdcf883b25ff4bf51be09abbd2a50cdf385707d5fea765b97767c54a528')
D2C = h('e33e3f4294553040df679722fe9dddb24e1f546bc9ff5df1f02e194b541d9c14')
C2D = h('bb764997d518d7239d36f9fad4c4488642515bcc35ecc6a106831bcbd6c6b543')
JOIN = h('50383600d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0590012000101101112131415161718191a1b1c1d1e1f')
CHALLENGE = h('50383600c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c05900210002101112131415161718191a1b1c1d1e1f'
              '202122232425262728292a2b2c2d2e2f')
PROOF = h('50383600d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d05900410003101112131415161718191a1b1c1d1e1f'
          '202122232425262728292a2b2c2d2e2ff22e793df352fff4d76660875d67c080378813eb426ed89d739ac2eac0c6fa2b')
RESULT0 = h('50383600c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0590044000400003c101112131415161718191a1b1c1d1e1f'
            '202122232425262728292a2b2c2d2e2fe8dd2bdcf883b25ff4bf51be09abbd2a50cdf385707d5fea765b97767c54a528')
INFO_DATA = h('50383600c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c05900430006000000000000000187cdcacbf3e79148c2806b8bdd922c'
              'ee0af9d74226b7740fa86b1809e05f116a2e3724aeb335b5d4125614eb84803f2022b09e69d1f587e19e84')
INFO_INNER = h('50383600c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0590012000701c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1')
HELLO_DATA = h('50383600d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d059006700060000000000000001fa977a5a91314acac6ed75a026ef14'
               '8dc8d95f229f50ed75c0f805dca743ccdbac5abdf7c6203e492ef318491a6b0b05b2b7916615fa247a06c18c9de9b2786b'
               '9fc757b80e45812cf36e08389fb623d68a9288a52a3a39d9471e90ad2b1e')
HELLO_INNER = h('50380100d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0d0000036003600486f6d65204173736973742e00000000000000000000'
                '000000000000000000000000000000000000000000000000000000000800')
CTRL = '192.0.2.40'
CFG = ProxyConfig(controller=CTRL, key=K.hex(), uplink_uid=UC)

# ---- the vectors: proofs, keys, and both sealed frames reproduced byte for byte
assert driver_proof(K, ND, NC, UD, UC) == DRIVER_PROOF
assert controller_proof(K, ND, NC, UD, UC, 60) == CONTROLLER_PROOF
assert session_keys(K, ND, NC, UD, UC) == (D2C, C2D)
assert seal(C2D, UC, 1, INFO_INNER) == INFO_DATA, 'INFO does not seal to the published datagram'
assert seal(D2C, UD, 1, HELLO_INNER) == HELLO_DATA, 'the hello does not seal to the published datagram'
assert unseal(C2D, INFO_DATA) == (1, INFO_INNER) and unseal(D2C, HELLO_DATA) == (1, HELLO_INNER)
for at in (0, 22, 24, 25, 32, 40, len(INFO_DATA) - 1):
    bad = bytearray(INFO_DATA)
    bad[at] ^= 1
    assert unseal(C2D, bytes(bad)) is None, f'a flipped byte at {at} still opens'
assert unseal(D2C, INFO_DATA) is None, 'opened with the other direction'
print('vectors     : proofs, keys, and both sealed datagrams match the controller')

# ---- the replay window
w = ReplayWindow()
assert [w.accept(c) for c in (1, 3, 2, 3, 0)] == [True, True, True, False, False]
assert w.accept(100) and not w.accept(100 - 64) and w.accept(100 - 63) and not w.accept(100 - 63)
print('replay      : each counter once, none 64 or more behind')

# ---- a join driven by the controller's own frames
class Wire:
    def __init__(self):
        self.sent, self.delivered, self.status, self.joins = [], [], [], 0
    def send(self, datagram, address):
        self.sent.append((datagram, address))
        return len(datagram)
    def deliver(self, frame, address):
        self.delivered.append((frame, address))
    def report(self, status, lease):
        self.status.append((status, lease))
    def joined(self):
        self.joins += 1

nonces = []
Proxy.secrets.token_bytes = lambda n: nonces.pop(0)

def link():
    w = Wire()
    return ProxyLink(CFG, UD, w.send, w.deliver, w.report, w.joined), w

def joined_link(now=0.0):
    l, w = link()
    nonces.append(ND)
    l.tick(now)
    l.on_datagram(CHALLENGE, CTRL, now)
    l.on_datagram(RESULT0, CTRL, now)
    assert l.joined
    return l, w

l, w = link()
assert l.transmit(HELLO_INNER) == 0 and w.sent == [], 'sent before a join'
nonces.append(ND)
l.tick(0.0)
assert w.sent == [(JOIN, CTRL)], w.sent
l.on_datagram(CHALLENGE, CTRL, 0.5)
assert w.sent[1] == (PROOF, CTRL), w.sent[1][0].hex()
assert not l.joined
l.on_datagram(RESULT0, CTRL, 1.0)
assert l.joined and l.lease == 60 and w.status == [(ProxyStatus.JOINED, 60)] and w.joins == 1
assert l.transmit(HELLO_INNER) == len(HELLO_INNER)
assert w.sent[2] == (HELLO_DATA, CTRL), 'the first DATA differs from the published one'
l.on_datagram(INFO_DATA, CTRL, 2.0)
assert l.mesh_uid == MxrDeviceUid(MESH) and w.delivered == [], 'INFO is the session\'s, not a mesh frame'
l.mesh_uid = None
l.on_datagram(seal(C2D, UC, 8, proxy_frame(UC, bytes([7, 2]) + h('c2' * 16))), CTRL, 2.0)
assert l.mesh_uid is None, 'an INFO of another version was taken'
print('join        : JOIN, PROOF and the first DATA are the published datagrams')

# ---- relayed mesh frames: delivered once, in any order, never replayed or forged
unit = h('a5' * 16)
def relayed(counter, uid=unit, key=C2D, sender=UC):
    return seal(key, sender, counter, create_mxr_frame(uid, 0x4A, b''))
l.on_datagram(relayed(3), CTRL, 3.0)
l.on_datagram(relayed(2), CTRL, 3.0)
l.on_datagram(relayed(3), CTRL, 3.0)
assert [f[4:20] for f, _ in w.delivered] == [unit, unit] and all(a == CTRL for _, a in w.delivered)
for what, dg, src in (('under another uid', relayed(4, sender=unit), CTRL), ('from another host', relayed(5), '192.0.2.99'),
                      ('sealed d2c', relayed(6, key=D2C), CTRL)):
    l.on_datagram(dg, src, 3.0)
    assert len(w.delivered) == 2, f'a DATA {what} was delivered'
inner_proxy = seal(C2D, UC, 7, proxy_frame(UC, bytes([6])))
l.on_datagram(inner_proxy, CTRL, 3.0)
assert len(w.delivered) == 2, 'a PROXY frame inside DATA was delivered as mesh traffic'
print('data        : relayed once each, replays and forgeries dropped')

# ---- the controller must prove the key; an unproven RESULT 0 moves nothing
for what, change in (('a bad proof', lambda r: r[:-1] + bytes([r[-1] ^ 1])),
                     ('another lease', lambda r: r[:26] + b'\x00\x3d' + r[28:]),
                     ('another Nd', lambda r: r[:28] + bytes([r[28] ^ 1]) + r[29:])):
    l2, w2 = link()
    nonces.append(ND)
    l2.tick(0.0)
    l2.on_datagram(CHALLENGE, CTRL, 0.0)
    l2.on_datagram(change(RESULT0), CTRL, 0.0)
    assert not l2.joined and w2.status == [], f'joined on {what}'
l2, w2 = link()
nonces.append(ND)
l2.tick(0.0)
l2.on_datagram(RESULT0, CTRL, 0.0)
assert not l2.joined, 'joined without having answered a CHALLENGE'
# A RESULT 0 recorded from an earlier join is valid, but for other nonces.
ND2 = bytes(range(0x60, 0x70))
l3, w3 = link()
nonces.append(ND2)
l3.tick(0.0)
l3.on_datagram(proxy_frame(UC, bytes([2]) + ND2 + NC), CTRL, 0.0)
assert w3.sent[-1][0][24] == 3, 'no PROOF for the second join'
l3.on_datagram(RESULT0, CTRL, 0.0)
assert not l3.joined, 'a replayed RESULT 0 of another join was taken'
other = bytearray(CHALLENGE)
other[25] ^= 1
l2.on_datagram(bytes(other), CTRL, 0.0)
l2.on_datagram(CHALLENGE, '192.0.2.99', 0.0)
assert len(w2.sent) == 1, 'answered a CHALLENGE for another Nd, or from another host'
print('proof       : RESULT 0 taken only with the controller\'s proof of this join')

# ---- a refused join is reported and retried after 10, 20, 40, then 60 s
def result(status):
    return proxy_frame(UC, bytes([4, status, 0, 0]))
l, w = link()
for i, wait in enumerate((10.0, 20.0, 40.0, 60.0, 60.0)):
    nonces.append(ND)
    start = sum((10.0, 20.0, 40.0, 60.0, 60.0)[:i])
    l.tick(start)
    assert w.sent[-1][0][24] == 1, 'no JOIN sent when due'
    l.on_datagram(result(ProxyStatus.BAD_PROOF), CTRL, start)
    assert w.status[-1] == (ProxyStatus.BAD_PROOF, None)
    count = len(w.sent)
    l.tick(start + wait - 0.1)
    assert len(w.sent) == count, f'joined again before {wait} s'
print('refused     : reported, retried after 10, 20, 40, then 60 s')

# ---- no answer within 10 s is reported too
l, w = link()
nonces.append(ND)
l.tick(0.0)
l.tick(9.9)
assert w.status == []
l.tick(10.0)
assert w.status == [(ProxyStatus.NO_ANSWER, None)]
print('no answer   : a join unanswered for 10 s')

# ---- the lease lapses without a valid DATA from the controller; then a new join
l, w = joined_link(0.0)
l.on_datagram(relayed(2), CTRL, 50.0)
l.tick(109.9)
assert l.joined, 'expired although a DATA came within the lease'
nonces.append(ND)
l.tick(110.0)
assert not l.joined and w.status[-1] == (ProxyStatus.LEASE_EXPIRED, None)
assert w.sent[-1] == (JOIN, CTRL), 'no new join after the lease lapsed'
print('lease       : lapses 60 s after the last valid DATA, then joins again')

# ---- RESULT 4 while joined: the controller restarted; join again at once
l, w = joined_link(0.0)
nonces.append(ND)
l.on_datagram(result(ProxyStatus.NOT_JOINED), CTRL, 5.0)
assert not l.joined and w.status[-1] == (ProxyStatus.NOT_JOINED, None) and w.sent[-1] == (JOIN, CTRL)
l, w = joined_link(0.0)
l.on_datagram(result(ProxyStatus.NOT_JOINED), '192.0.2.99', 5.0)
assert l.joined, 'a RESULT 4 from another host ended the session'
# Any refusal from the session's address ends it, reported as such.
l, w = joined_link(0.0)
nonces.append(ND)
l.on_datagram(result(ProxyStatus.PROXY_OFF), CTRL, 5.0)
assert not l.joined and w.status[-1] == (ProxyStatus.PROXY_OFF, None) and w.sent[-1] == (JOIN, CTRL)
# A session ending while its address backs off waits for the backoff.
l.on_datagram(result(ProxyStatus.PROXY_OFF), CTRL, 5.5)       # the new join refused: back off 10 s
nonces.append(ND)
l.tick(15.5)
l.on_datagram(CHALLENGE, CTRL, 15.6)
l.on_datagram(RESULT0, CTRL, 15.7)
assert l.joined
l._retry[CTRL] = (100.0, 20.0)       # as if refused again since
count = len(w.sent)
l.on_datagram(result(ProxyStatus.NOT_JOINED), CTRL, 20.0)
assert not l.joined and len(w.sent) == count, 'joined again at once while backing off'
nonces.append(ND)
l.tick(100.0)
assert w.sent[-1] == (JOIN, CTRL), 'no join once the backoff ran out'
print('result      : any refusal ends a session, which joins again unless backing off')

# ---- LEAVE either way, inside DATA
l, w = joined_link(0.0)
nonces.append(ND)
l.on_datagram(seal(C2D, UC, 2, proxy_frame(UC, bytes([5]))), CTRL, 1.0)
assert not l.joined and w.status[-1] == (ProxyStatus.LEFT, None) and w.sent[-1] == (JOIN, CTRL), \
    'a LEAVE from the controller does not end the session and join again'
l, w = joined_link(0.0)
count = len(w.sent)
l.leave()
assert not l.joined and len(w.sent) == count + 1
assert unseal(D2C, w.sent[-1][0]) == (1, proxy_frame(UD, bytes([5]))), 'LEAVE is not sealed d2c'
assert l.transmit(HELLO_INNER) == 0
print('leave       : taken from the controller, and sent sealed on stop')

# ---- a new controller address: joined there only once the key is proven there
NEW = '192.0.2.41'
def uplink_hello(name='OneIP Controller'):
    pad = lambda s: s.encode() + bytes(16 - len(s))
    return create_mxr_frame(UC, 0x00, struct.pack('<H', 0x36) + pad(name) + pad('P8SN00001234') + pad('1.1.0')
                            + struct.pack('<I', int(DeviceFeature.MESH_MEMBER)))
l, w = joined_link(0.0)
l.on_passive(uplink_hello(), CTRL, 1.0)
assert (l.name, l.serial, l.version) == ('OneIP Controller', 'P8SN00001234', '1.1.0')
assert len(w.sent) == 2, 'the hello at the current address started a join'
l.on_passive(create_mxr_frame(h('a5' * 16), 0x00, uplink_hello()[24:]), NEW, 1.0)
assert len(w.sent) == 2, 'a hello under another uid started a join'
nonces.append(ND)
l.on_passive(uplink_hello(), NEW, 1.0)
assert w.sent[-1] == (JOIN, NEW), 'no join at the new address'
l.on_datagram(result(ProxyStatus.BAD_PROOF), NEW, 1.5)
assert l.joined and l.address == CTRL and w.status == [(ProxyStatus.JOINED, 60)], \
    'a refusal at an unproven address was reported or moved the session'
l.on_passive(uplink_hello(), NEW, 5.0)
assert w.sent[-1][1] != NEW or len(w.sent) == 3, 'joined the new address again inside its backoff'
nonces.append(ND)
l.on_passive(uplink_hello(), NEW, 11.5)
l.on_datagram(CHALLENGE, NEW, 11.6)
l.on_datagram(RESULT0, NEW, 11.7)
assert l.joined and l.address == NEW and w.status[-1] == (ProxyStatus.JOINED, 60)
assert l.transmit(HELLO_INNER) and w.sent[-1][1] == NEW, 'frames still go to the old address'
print('address     : a new one is joined, and used only once proven')

# ---- a Remote behind the proxy: relayed units carry the controller's address
class Calls(mx_remote.MxrCallbacks):
    def __init__(self):
        self.status = []
    def on_proxy_join_status(self, status, lease):
        self.status.append((status, lease))
calls = Calls()
mx = mx_remote.Remote(open_connection=False, callbacks=calls, proxy=CFG)
mx._uid = UD
wire = Wire()
conn = ProxyConnection(callbacks=mx, config=CFG, local_ip='192.0.2.1')
conn.link = ProxyLink(CFG, UD, wire.send, conn._deliver, mx.on_proxy_status, mx.on_proxy_joined)
conn._closed = False
mx.conn = conn
nonces.append(ND)
conn.link.tick(0.0)
conn.link.on_datagram(CHALLENGE, CTRL, 0.0)
conn.link.on_datagram(RESULT0, CTRL, 0.0)
assert calls.status == [(ProxyStatus.JOINED, 60)] and mx.proxy is conn.link
ops = [unseal(D2C, d)[1][20] for d, _ in wire.sent[2:]]
assert ops == [0x00, 0x01], f'a join is not followed by a hello and a discover: {ops}'
pad = lambda s: s.encode() + bytes(16 - len(s))
unit_hello = create_mxr_frame(unit, 0x00, struct.pack('<H', 0x36) + pad('OneIP') + pad('P8SN00000001') + pad('5.0.0')
                              + struct.pack('<I', int(DeviceFeature.ONEIP_SINK)))
conn.link.on_datagram(seal(C2D, UC, 2, unit_hello), CTRL, 1.0)
dev = mx.get_by_uid(MxrDeviceUid(unit))
assert dev is not None and dev.address == CTRL, 'a relayed unit is not registered at the controller\'s address'
print('remote      : joined, announced, and relayed units registered')

# ---- what does not pass the proxy is refused, not sent
before = len(wire.sent)
async def refused():
    content = mx_remote.OsdSyncContent(what=mx_remote.OsdSyncWhat.CAPTIONS)
    assert await mx.send_osd_sync(content) is None
    assert await mx.keep_osd_sync(content) is False
    assert await mx.request_osd_sync(mx_remote.OsdSyncWhat.CAPTIONS) is False
    assert await mx.send_osd_preview(dev, content, 1) is None
    assert await mx.commit_osd_preview(dev, 1) is False
    assert await mx.clear_osd_sync() is None
    # get_api() and get_log() swallow every error, so record the attempt.
    attempts = []
    def no_http(url, *a, **k):
        attempts.append(url)
        raise OSError('no HTTP here')
    mx.http_session.get = no_http
    assert await dev.get_api('x') is None and await dev.get_log() is None
    assert attempts == [], f'HTTP was attempted: {attempts}'
asyncio.run(refused())
assert len(wire.sent) == before, 'a refused call sent something'
for clash in ({'target_ip': '1.2.3.4'}, {'mesh_device': True}, {'dedicated_controller': True}, {'osd_sync': True},
              {'announce_interfaces': ['eth1']}):
    try:
        mx_remote.Remote(open_connection=False, proxy=CFG, **clash)
    except ValueError:
        continue
    raise AssertionError(f'{clash} was taken with a proxy')
try:
    ProxyLink(CFG, UC, *([lambda *a: 0] * 4))
except ValueError:
    pass
else:
    raise AssertionError('a client whose uid is the uplink uid was taken')
for bad in ({'key': K[:31]}, {'key': 'zz' * 32}, {'uplink_uid': bytes(16)}):
    try:
        ProxyConfig(**{'controller': CTRL, 'key': K, 'uplink_uid': UC, **bad})
    except ValueError:
        continue
    raise AssertionError(f'{bad} was taken')
assert mx_remote.Remote(open_connection=False).proxy is None
# The uplink uid as the controller keeps it: 32 hex characters, its wire bytes.
assert ProxyConfig(controller=CTRL, key=K, uplink_uid=UC.hex() + '\n').uplink_uid == MxrDeviceUid(UC)
assert ProxyConfig(controller=CTRL, key=K, uplink_uid=str(MxrDeviceUid(UC))).uplink_uid == MxrDeviceUid(UC)
# A live pair from a 1.0.12 controller: its uplink-uid file, and the uid its
# hello carried, as this library writes it. A join under it succeeded.
assert ProxyConfig(controller=CTRL, key=K, uplink_uid='e8cd652b23e8635a3b715073efc8e055').uplink_uid \
    == MxrDeviceUid('2b65cde8.5a63e823.7350713b.55e0c8ef')
print('refused     : overlay syncs, HTTP and the options a proxy rules out')

# The probe loop runs the session's clock: this one was last heard at 1.0.
nonces.append(ND)
mx._probe_once()
assert calls.status[-1] == (ProxyStatus.LEASE_EXPIRED, None), 'the probe loop does not expire the lease'
print('probe       : the probe loop expires a silent session')

# ---- over real sockets: the one socket on the proxy port takes the answers
# to what it sends. A controller on 127.0.0.2 answers with the published frames.
import socket
async def loopback():
    port = 18813
    ctrl = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ctrl.bind(('127.0.0.2', port))
    ctrl.settimeout(3)
    cfg = ProxyConfig(controller='127.0.0.2', key=K, uplink_uid=UC, port=port)
    mx = mx_remote.Remote(open_connection=False, proxy=cfg)
    mx._uid = UD
    conn = ProxyConnection(callbacks=mx, config=cfg, local_ip='127.0.0.1')
    mx.conn = conn
    nonces.append(ND)
    await conn.start_srv()
    loop = asyncio.get_running_loop()
    def take():
        while True:
            data, addr = ctrl.recvfrom(2048)
            if data[20] == 0x59 and data[24] in (1, 3, 6):
                return data, addr
    data, addr = await loop.run_in_executor(None, take)
    assert data == JOIN and addr == ('127.0.0.1', port), (data.hex(), addr)
    ctrl.sendto(CHALLENGE, addr)
    data, _ = await loop.run_in_executor(None, take)
    assert data == PROOF, 'the PROOF over the socket differs'
    ctrl.sendto(RESULT0, addr)
    data, _ = await loop.run_in_executor(None, take)
    assert unseal(D2C, data)[1][20] == 0x00, 'no sealed hello after the join'
    ctrl.sendto(INFO_DATA, addr)
    for _ in range(50):
        if mx.proxy.mesh_uid is not None:
            break
        await asyncio.sleep(0.02)
    assert mx.proxy.joined and mx.proxy.mesh_uid == MxrDeviceUid(MESH)
    conn.close()
    while True:
        data, _ = await loop.run_in_executor(None, take)
        opened = unseal(D2C, data)
        if opened[1][20:22] == b'\x59\x00':
            break
    assert opened[1][24] == 5, 'no LEAVE on close'
    ctrl.close()
asyncio.run(asyncio.wait_for(loopback(), 15))
print('sockets     : joined over loopback, INFO taken, LEAVE on close')

print('ALL OK')
