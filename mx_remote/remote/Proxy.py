######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''A client joined to a OneIP controller's driver proxy.

The controller relays its mesh to one client on its uplink, by unicast on
PROXY_PORT, so that no mx_remote multicast or broadcast reaches the uplink:

- The client joins with the driver key K, which the controller's web interface
  shows: JOIN, CHALLENGE, PROOF, RESULT.
  - Both sides prove K.
  - A client takes RESULT 0 only with a valid controller proof, so a host
    posing as the controller gets nothing from it.
- After the join, every frame between the two goes in DATA, sealed with
  AES-256-GCM under a key per direction.
  - The keys are HKDF-SHA256 of K, salted with both nonces.
  - Each direction counts its frames from 1, and a receiver takes each counter
    once, within a 64-frame window.
- The controller relays every mesh frame to the client unchanged. It relays the
  client's frames onto the mesh as far as its allow-list permits.

ProxyLink keeps the session and touches no socket, so it runs on any clock and
any transport. ProxyConnection puts it on the network:
- the session, on PROXY_PORT;
- a receive-only listen on the mesh endpoints, which hears the controller's
  uplink hello when its address changes.

Layout and rules per the controller's docs/driver-proxy.md
(v2ip-routeros-manager), whose section 8 vectors tests/proxy.py checks.
'''

from __future__ import annotations
import asyncio
import hashlib
import hmac
import logging
import secrets
import struct
from dataclasses import dataclass, field
from typing import Callable
from ..const import MX_BCAST_UDP_PORT, MX_MCAST_UDP_IP, MX_MCAST_UDP_PORT
from ..proto.Constants import PROXY_OPCODE, PROXY_PORT, PROXY_VERSION, Endpoints, ProxyStatus, ProxySubOp
from ..proto.FrameProxy import (COUNTER_SIZE, HEADER_SIZE, NONCE_SIZE, PROOF_SIZE, TAG_SIZE, join_payload,
                                leave_payload, proof_payload, proxy_frame)
from ..Uid import MxrDeviceUid

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:     # the optional extra mx_remote[proxy]
    AESGCM = None

_LOGGER = logging.getLogger(__name__)

KEY_SIZE = 32
JOIN_TIMEOUT = 10.0
'''How long a join waits for CHALLENGE, and then for RESULT, in seconds: the
life of a controller's nonce.'''
BACKOFF_MIN = 10.0
BACKOFF_MAX = 60.0
'''A join that failed is tried again after 10 s, doubling up to 60 s, per
address; a join that succeeds resets it.'''
REPLAY_WINDOW = 64

def proxy_available() -> bool:
    '''Whether the optional extra mx_remote[proxy], which seals DATA, is
    installed.'''
    return (AESGCM is not None)

def driver_proof(key:bytes, nd:bytes, nc:bytes, ud:bytes, uc:bytes) -> bytes:
    '''PROOF's HMAC: HMAC-SHA256(K, "drv" ‖ Nd ‖ Nc ‖ Ud ‖ Uc).'''
    return hmac.new(key, b'drv' + nd + nc + ud + uc, hashlib.sha256).digest()

def controller_proof(key:bytes, nd:bytes, nc:bytes, ud:bytes, uc:bytes, lease:int) -> bytes:
    '''RESULT 0's HMAC: HMAC-SHA256(K, "ctl" ‖ Nd ‖ Nc ‖ Ud ‖ Uc ‖ lease),
    the lease a big-endian u16.'''
    return hmac.new(key, b'ctl' + nd + nc + ud + uc + lease.to_bytes(2, 'big'), hashlib.sha256).digest()

def _hkdf(ikm:bytes, salt:bytes, info:bytes, length:int=KEY_SIZE) -> bytes:
    '''HKDF-SHA256 (RFC 5869).'''
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    out, block = b'', b''
    for i in range(1, -(-length // 32) + 1):
        block = hmac.new(prk, block + info + bytes([i]), hashlib.sha256).digest()
        out += block
    return out[:length]

def session_keys(key:bytes, nd:bytes, nc:bytes, ud:bytes, uc:bytes) -> tuple[bytes, bytes]:
    '''The client-to-controller and controller-to-client keys of a session.'''
    salt = nd + nc
    return (_hkdf(key, salt, b'mxr-proxy' + ud + uc + b'd2c'),
            _hkdf(key, salt, b'mxr-proxy' + ud + uc + b'c2d'))

def seal(key:bytes, uid:bytes, counter:int, inner:bytes) -> bytes:
    '''A whole DATA datagram from uid carrying inner, one complete mx_remote
    frame. The header, sub-op and counter are the additional data.'''
    assert (AESGCM is not None), 'mx_remote[proxy] is not installed'
    ctr = counter.to_bytes(COUNTER_SIZE, 'big')
    header = proxy_frame(uid, bytes(1 + COUNTER_SIZE + len(inner) + TAG_SIZE))[:HEADER_SIZE]
    prefix = header + bytes([ProxySubOp.DATA]) + ctr
    return prefix + AESGCM(key).encrypt(bytes(4) + ctr, inner, prefix)

def unseal(key:bytes, datagram:bytes) -> tuple[int, bytes]|None:
    '''The counter and inner frame of a DATA datagram, None when it fails its
    check.'''
    assert (AESGCM is not None), 'mx_remote[proxy] is not installed'
    at = HEADER_SIZE + 1 + COUNTER_SIZE
    if (len(datagram) < (at + TAG_SIZE)):
        return None
    ctr = datagram[HEADER_SIZE + 1:at]
    try:
        inner = AESGCM(key).decrypt(bytes(4) + ctr, datagram[at:], datagram[:at])
    except Exception:
        return None
    return int.from_bytes(ctr, 'big'), inner

class ReplayWindow:
    '''The counters taken in a direction: each once, and none older than
    REPLAY_WINDOW behind the highest.'''
    def __init__(self) -> None:
        self.highest = 0
        self._seen = 0      # bit n: highest - n was taken

    def accept(self, counter:int) -> bool:
        if (counter < 1):
            return False
        if (counter > self.highest):
            shift = counter - self.highest
            self._seen = ((self._seen << shift) | 1) & ((1 << REPLAY_WINDOW) - 1)
            self.highest = counter
            return True
        back = self.highest - counter
        if (back >= REPLAY_WINDOW) or (self._seen & (1 << back)):
            return False
        self._seen |= (1 << back)
        return True

@dataclass(frozen=True)
class ProxyConfig:
    '''How to reach a controller's driver proxy: Remote(proxy=ProxyConfig(...)).

    controller is its uplink address, as on_proxy_found reported it or as
    configured; key the driver key its web interface shows, as 32 bytes or 64
    hex characters; uplink_uid the uid it announces on the uplink, which this
    client pins: only frames under it are taken. port is the proxy's UDP port
    at both ends, PROXY_PORT unless testing.'''
    controller:str
    key:bytes|str = field(repr=False)
    uplink_uid:MxrDeviceUid|bytes|str
    port:int = PROXY_PORT

    def __post_init__(self) -> None:
        key = bytes.fromhex(self.key) if isinstance(self.key, str) else bytes(self.key)
        if (len(key) != KEY_SIZE):
            raise ValueError(f'a driver key is {KEY_SIZE} bytes, or {2 * KEY_SIZE} hex characters')
        uid = self.uplink_uid if isinstance(self.uplink_uid, MxrDeviceUid) else MxrDeviceUid(self.uplink_uid)
        if uid.empty:
            raise ValueError('a controller uplink uid is required')
        object.__setattr__(self, 'key', key)
        object.__setattr__(self, 'uplink_uid', uid)

@dataclass
class _Session:
    address:str
    d2c:bytes
    c2d:bytes
    lease:int
    heard:float
    '''When a valid DATA from the controller last arrived.'''
    sent:int = 0
    window:ReplayWindow = field(default_factory=ReplayWindow)

@dataclass
class _Join:
    address:str
    nd:bytes
    since:float
    nc:bytes|None = None
    reports:bool = True
    '''Whether its outcome is reported: a join to the controller's own
    address. One to an address a hello only claims is tried quietly.'''

class ProxyLink:
    '''A client's session with a controller's driver proxy, without a socket.

    send(datagram, address) puts a datagram on the wire to address:PROXY_PORT
    and returns the bytes written. deliver(frame, address) hands on a mesh
    frame the controller relayed. report(status, lease) tells how the join
    stands, and joined() follows every join.'''

    def __init__(self, config:ProxyConfig, own_uid:bytes, send:Callable[[bytes, str], int],
                 deliver:Callable[[bytes, str], None], report:Callable[[ProxyStatus, int|None], None],
                 joined:Callable[[], None]) -> None:
        self._key:bytes = config.key            # type: ignore[assignment]
        self.uplink_uid:MxrDeviceUid = config.uplink_uid  # type: ignore[assignment]
        self._uc = self.uplink_uid.byte_value
        self._ud = bytes(own_uid)
        if (self._ud == self._uc):
            raise ValueError("this client's uid is the controller's uplink uid")
        self._send = send
        self._deliver = deliver
        self._report = report
        self._joined = joined
        self.address = config.controller
        '''The controller's uplink address, which every frame goes to.'''
        self.status:ProxyStatus|None = None
        '''The last status reported, None before the first.'''
        self.mesh_uid:MxrDeviceUid|None = None
        '''The controller's uid on its mesh, from INFO, None until it came.'''
        self.name:str|None = None
        self.serial:str|None = None
        self.version:str|None = None
        self._session:_Session|None = None
        self._join:_Join|None = None
        self._retry:dict[str, tuple[float, float]] = {}

    @property
    def joined(self) -> bool:
        return (self._session is not None)

    @property
    def lease(self) -> int|None:
        return None if (self._session is None) else self._session.lease

    # ---- sending

    def transmit(self, inner:bytes) -> int:
        '''Seal inner, a whole mx_remote frame, into DATA to the controller,
        returning len(inner) when it was written whole, 0 when not joined or
        when it was not.'''
        s = self._session
        if (s is None):
            return 0
        s.sent += 1
        datagram = seal(s.d2c, self._ud, s.sent, inner)
        return len(inner) if (self._send(datagram, s.address) == len(datagram)) else 0

    def leave(self) -> None:
        '''End the session, telling the controller.'''
        if (self._session is not None):
            self.transmit(proxy_frame(self._ud, leave_payload()))
            self._session = None
        self._join = None

    # ---- joining

    def _begin(self, address:str, now:float, reports:bool) -> None:
        nd = secrets.token_bytes(NONCE_SIZE)
        self._join = _Join(address=address, nd=nd, since=now, reports=reports)
        self._send(proxy_frame(self._ud, join_payload(nd)), address)

    def _backoff(self, address:str, now:float) -> None:
        delay = self._retry.get(address, (0.0, BACKOFF_MIN))[1]
        self._retry[address] = (now + delay, min(delay * 2, BACKOFF_MAX))

    def _may_join(self, address:str, now:float) -> bool:
        return (now >= self._retry.get(address, (0.0, BACKOFF_MIN))[0])

    def _fail(self, join:_Join, status:ProxyStatus, now:float) -> None:
        self._join = None
        self._backoff(join.address, now)
        if join.reports:
            self._set_status(status, None)

    def _set_status(self, status:ProxyStatus, lease:int|None) -> None:
        self.status = status
        self._report(status, lease)

    def tick(self, now:float) -> None:
        '''Time out a join, expire the lease, and start a join that is due.'''
        if (self._join is not None) and ((now - self._join.since) >= JOIN_TIMEOUT):
            self._fail(self._join, ProxyStatus.NO_ANSWER, now)
        s = self._session
        if (s is not None) and ((now - s.heard) >= s.lease):
            self._end(ProxyStatus.LEASE_EXPIRED, now)
        if (self._session is None) and (self._join is None) and self._may_join(self.address, now):
            self._begin(self.address, now, reports=True)

    # ---- receiving

    def _header(self, data:bytes) -> tuple[MxrDeviceUid, int, bytes]|None:
        '''The sender, opcode and payload of a whole mx_remote datagram.'''
        if (len(data) < HEADER_SIZE) or (data[0:2] != b'P8'):
            return None
        opcode, length = struct.unpack_from('<HH', data, 20)
        if (len(data) != (HEADER_SIZE + length)):
            return None
        return MxrDeviceUid(data[4:20]), opcode, data[HEADER_SIZE:]

    def on_datagram(self, data:bytes, address:str, now:float) -> None:
        '''A datagram to PROXY_PORT from address: the controller's PROXY
        frames, under its uplink uid. Anything else is dropped.'''
        parsed = self._header(data)
        if (parsed is None) or (parsed[0] != self.uplink_uid) or (parsed[1] != PROXY_OPCODE) or (len(parsed[2]) < 1):
            return
        p = parsed[2]
        op = p[0]
        if (op == ProxySubOp.CHALLENGE):
            self._on_challenge(p, address)
        elif (op == ProxySubOp.RESULT):
            self._on_result(p, address, now)
        elif (op == ProxySubOp.DATA):
            self._on_data(data, address, now)

    def _on_challenge(self, p:bytes, address:str) -> None:
        j = self._join
        if (j is None) or (j.address != address) or (j.nc is not None) or (len(p) < (1 + 2 * NONCE_SIZE)):
            return
        if not hmac.compare_digest(p[1:1 + NONCE_SIZE], j.nd):
            return
        j.nc = p[1 + NONCE_SIZE:1 + 2 * NONCE_SIZE]
        self._send(proxy_frame(self._ud, proof_payload(j.nd, j.nc, driver_proof(self._key, j.nd, j.nc,
                                                                                self._ud, self._uc))), address)

    def _on_result(self, p:bytes, address:str, now:float) -> None:
        if (len(p) < 4):
            return
        status, lease = p[1], int.from_bytes(p[2:4], 'big')
        j = self._join
        if (status == ProxyStatus.JOINED):
            if (j is None) or (j.address != address) or (j.nc is None) \
                    or (len(p) < (4 + 2 * NONCE_SIZE + PROOF_SIZE)):
                return
            nd, nc = p[4:4 + NONCE_SIZE], p[4 + NONCE_SIZE:4 + 2 * NONCE_SIZE]
            proof = p[4 + 2 * NONCE_SIZE:4 + 2 * NONCE_SIZE + PROOF_SIZE]
            if not (hmac.compare_digest(nd, j.nd) and hmac.compare_digest(nc, j.nc)
                    and hmac.compare_digest(proof, controller_proof(self._key, nd, nc, self._ud, self._uc, lease))):
                # Unproven: nothing a host posing as the controller sends moves
                # this client.
                return
            d2c, c2d = session_keys(self._key, nd, nc, self._ud, self._uc)
            self._session = _Session(address=address, d2c=d2c, c2d=c2d, lease=lease, heard=now)
            self._join = None
            self._retry.pop(address, None)
            self.address = address
            self._set_status(ProxyStatus.JOINED, lease)
            self._joined()
            return
        code = ProxyStatus(status) if (status in ProxyStatus._value2member_map_) else ProxyStatus.NOT_JOINED
        if (j is not None) and (j.address == address):
            self._fail(j, code, now)
            return
        s = self._session
        if (s is not None) and (s.address == address):
            # The controller holds no session for this client, as after its
            # restart, or will not keep it. Unproven, so at worst a forged one
            # costs a join.
            self._end(code, now)

    def _end(self, status:ProxyStatus, now:float) -> None:
        '''End the session, reporting why, and join again at once unless the
        address is backing off; tick() joins once it no longer is.'''
        self._session = None
        self._set_status(status, None)
        if (self._join is None) and self._may_join(self.address, now):
            self._begin(self.address, now, reports=True)

    def _on_data(self, datagram:bytes, address:str, now:float) -> None:
        s = self._session
        if (s is None) or (s.address != address):
            return
        opened = unseal(s.c2d, datagram)
        if (opened is None) or not s.window.accept(opened[0]):
            return
        s.heard = now
        inner = opened[1]
        parsed = self._header(inner)
        if (parsed is None):
            return
        if (parsed[1] != PROXY_OPCODE):
            self._deliver(inner, address)
            return
        # PROXY inside DATA: INFO and LEAVE from the controller, nothing else.
        if (parsed[0] != self.uplink_uid) or (len(parsed[2]) < 1):
            return
        p = parsed[2]
        if (p[0] == ProxySubOp.INFO) and (len(p) >= 2 + 16) and (p[1] == PROXY_VERSION):
            self.mesh_uid = MxrDeviceUid(p[2:18])
        elif (p[0] == ProxySubOp.LEAVE):
            self._end(ProxyStatus.LEFT, now)

    def on_passive(self, data:bytes, address:str, now:float) -> None:
        '''A datagram heard on a mesh endpoint. Only the controller's uplink
        hello is taken: it names the controller, and one from another address
        starts a join there, which replaces the session only once the
        controller proved the key at that address.'''
        parsed = self._header(data)
        if (parsed is None) or (parsed[0] != self.uplink_uid) or (parsed[1] != 0x00):
            return
        p = parsed[2]
        if (len(p) >= 50):
            def text(at:int) -> str:
                return p[at:at + 16].split(b'\0', 1)[0].decode('ascii', 'replace')
            self.name, self.serial, self.version = text(2), text(18), text(34)
        if (address != self.address) and (self._join is None) and self._may_join(address, now):
            self._begin(address, now, reports=False)

class _ProxySocket(asyncio.DatagramProtocol):
    '''The one socket on PROXY_PORT, which sends to the controller and takes
    its answers: the controller answers the port a client sends from.'''
    def __init__(self, owner:'ProxyConnection') -> None:
        self._owner = owner
        self.transport:asyncio.DatagramTransport|None = None

    def connection_made(self, transport:asyncio.BaseTransport) -> None:
        self.transport = transport     # type: ignore[assignment]

    def datagram_received(self, data:bytes, addr:tuple[str, int]) -> None:
        self._owner.on_proxy_datagram(data, addr)

class ProxyConnection:
    '''The transport of a client joined to a controller's driver proxy, in
    place of ConnectionAsync: every frame goes sealed to the controller, and
    every frame taken came from it.

    The mesh endpoints are opened to listen only, for the controller's uplink
    hello; nothing is sent there.'''

    def __init__(self, callbacks:'ProxyCallbacks', config:ProxyConfig, local_ip:str|None,
                 clock:Callable[[], float]|None=None) -> None:
        from .ConnectionAsync import _Endpoint
        import time
        self._callbacks = callbacks
        self._config = config
        self._local_ip = local_ip
        self._port = config.port
        self._clock = clock or time.time
        self._socket:_ProxySocket|None = None
        self._listen = [_Endpoint(self, MX_MCAST_UDP_IP, MX_MCAST_UDP_PORT, self.local_ip, Endpoints.MULTICAST),  # type: ignore[arg-type]
                        _Endpoint(self, '255.255.255.255', MX_BCAST_UDP_PORT, self.local_ip, Endpoints.BROADCAST)]  # type: ignore[arg-type]
        self.link:ProxyLink|None = None
        self._closed = True

    @property
    def local_ip(self) -> str|None:
        if not self._local_ip:
            from ..Interface import mxr_valid_addresses
            addresses = mxr_valid_addresses()
            self._local_ip = addresses[0] if addresses else None
        return self._local_ip

    @property
    def is_dual(self) -> bool:
        return False

    @property
    def is_open(self) -> bool:
        return not self._closed

    def reach(self) -> list[tuple[str|None, int]]:
        return []

    async def start_srv(self) -> None:
        '''Open the proxy socket and the listen on the mesh endpoints, then
        start joining.'''
        from .ConnectionAsync import arrival_for
        loop = asyncio.get_running_loop()
        try:
            _, protocol = await loop.create_datagram_endpoint(lambda: _ProxySocket(self),
                                                              local_addr=(self._local_ip or '0.0.0.0', self._port),
                                                              reuse_port=True)
            self._socket = protocol
            arrival = arrival_for(self._local_ip)
            for endpoint in self._listen:
                endpoint.arrival = arrival
                await endpoint.start()
        except Exception as e:
            _LOGGER.warning(f"failed to start the driver proxy client: {e}")
            self.close()
            raise
        uid = self._callbacks.uid_raw
        assert (uid is not None)
        self.link = ProxyLink(self._config, bytes(uid), self._send, self._deliver,
                              self._callbacks.on_proxy_status, self._callbacks.on_proxy_joined)
        self._closed = False
        self.link.tick(self._clock())
        self._callbacks.on_connection_made()

    def _send(self, datagram:bytes, address:str) -> int:
        if (self._socket is None) or (self._socket.transport is None):
            return 0
        self._socket.transport.sendto(datagram, (address, self._port))
        return len(datagram)

    def _deliver(self, frame:bytes, address:str) -> None:
        self._callbacks.on_datagram_received(frame, (address, self._port), None)

    def on_proxy_datagram(self, data:bytes, addr:tuple[str, int]) -> None:
        if (self.link is not None):
            self.link.on_datagram(data, addr[0], self._clock())

    def _received(self, data:bytes, addr:tuple[str, int], path:Endpoints) -> None:
        '''A datagram on a mesh endpoint, which only the link reads.'''
        if (self.link is not None):
            self.link.on_passive(data, addr[0], self._clock())

    def tick(self) -> None:
        if (self.link is not None) and not self._closed:
            self.link.tick(self._clock())

    def transmit(self, data:bytes, endpoints:Endpoints=Endpoints.MULTICAST) -> int:
        '''Seal a frame to the controller, returning len(data) when it went,
        0 while not joined, which a closed connection is not.'''
        if (self.link is None):
            return 0
        return self.link.transmit(data)

    def close(self) -> None:
        '''Leave the session and close every socket.'''
        if (self.link is not None) and not self._closed:
            self.link.leave()
        for endpoint in self._listen:
            endpoint.close()
        if (self._socket is not None) and (self._socket.transport is not None):
            self._socket.transport.close()
        self._socket = None
        self._closed = True

class ProxyCallbacks:
    '''What ProxyConnection needs of its owner, a Remote.'''
    uid_raw:bytes|None
    def on_connection_made(self) -> None: ...
    def on_datagram_received(self, data:bytes, addr:tuple[str, int], path:Endpoints|None=None) -> None: ...
    def on_proxy_status(self, status:ProxyStatus, lease:int|None) -> None: ...
    def on_proxy_joined(self) -> None: ...
