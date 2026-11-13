######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Async UDP endpoints for MX Remote: the multicast group and the subnet broadcast.'''

import asyncio
import logging
import os
import socket
import struct
import sys
import ipaddress
from typing import Tuple
import netifaces
from ..compat import IP_PKTINFO
from ..Interface import ConnectionCallbacks, mxr_broadcast_address, mxr_valid_addresses
from ..const import MX_BCAST_UDP_PORT, MX_MCAST_UDP_IP, MX_MCAST_UDP_PORT
from ..proto.Constants import Endpoints

_LOGGER = logging.getLogger(__name__)

# Addressing is by uid in the payload, never by IP. A frame reaching this socket
# is not necessarily addressed to us, and one addressed to us is not necessarily
# the only copy on the wire. Demultiplex on the uid.
#
# A unit always runs two endpoints, the multicast group 224.8.8.8 on 8812 and
# the subnet broadcast address on 8811, and neither can be moved or disabled. A
# peer whose multicast fails is still reached by broadcast, so this client runs
# both as well. Which of them a frame leaves by is Remote.transmit()'s choice.
#
# Two things keep this correct if they are:
#
#   - Bind INADDR_ANY, not the group address, so a frame addressed to this host
#     arrives alongside the group traffic.
#   - Provoke state rather than waiting for it. SYS_DISCOVER (0x01) makes a
#     device answer with a hello and then re-broadcast everything cached here -
#     bay config, sources, signal status, links, device config, EDID, net link,
#     rc settings, topology, temperatures and firmware versions. There is no
#     per-opcode request form for those, and 0x26 in particular accepts a
#     zero-length frame and answers nothing, so probing it looks like a device
#     ignoring us.
#
# The answer to a discover goes to the group, is jittered so a mesh does not
# reply at once, and is expensive - Remote._background_probe() rate-limits it and
# stops once every device reports complete. After that a device repeats a frame
# in only a couple of periodic broadcasts after it changes, and resends
# everything only every few minutes. So a device first heard, or heard again
# after it went offline, is asked on its own with a discover whose payload is
# its 16-byte uid - see Remote._request_state().
#
# Signal status (0x31) is the one opcode with a targeted request form of its own,
# an empty payload or a 16-byte uid, which this library does not send.

# SO_REUSEADDR is what permits a second client on this host to bind these ports,
# on both sockets: measured on Linux 6.1 for the wildcard receive bind, the
# specific-address transmit bind, and both together. SO_REUSEPORT is set as well
# and is load-bearing on neither.
#
# It is also widely believed to cost multicast fan-out - that Linux hashes each
# datagram to one member of a reuseport group, multicast included. It does not.
# A reuseport group selects one member on the unicast path only; multicast and
# broadcast reach every bound socket whether the option is set or not.

def is_posix_os() -> bool:
    '''Return True if the current OS is POSIX-compatible.'''
    return (os.name == 'posix')

MULTICAST_TTL = 64
'''The TTL a unit sends on the discovery group with. Anything lower leaves a
unit more routed hops away hearing every unit but this client.'''

_READ_MAX = 65535
_PKTINFO_SIZE = 12
'''struct in_pktinfo: the int arrival interface index, then two addresses.'''

def index_holding(address:str) -> int:
    '''The kernel index of the interface holding address, loopback included.
    Raises OSError when no interface holds it.'''
    for name in netifaces.interfaces():
        if any(entry.get('addr') == address for entry in netifaces.ifaddresses(name).get(netifaces.AF_INET, [])):
            return socket.if_nametoindex(name)
    raise OSError(f"no interface holds {address}")

def arrival_for(local_ip:str|None) -> int|None:
    '''The index of the interface the caller selected by address, which is the
    only one datagrams are taken from. None when none is selected, and off
    Linux, where nothing reports the interface a datagram arrived on.

    The receive socket is bound to every address, so without this a
    multi-homed host hands it every broadcast and group frame on every other
    interface too. Filtering on the arrival interface needs no privilege,
    where SO_BINDTODEVICE needs CAP_NET_RAW on kernels before 5.7.'''
    if (not local_ip) or not sys.platform.startswith('linux'):
        return None
    return index_holding(local_ip)

def address_of(interface:str) -> str|None:
    """The current IPv4 address of interface, None while it has none or does
    not exist."""
    try:
        entries = netifaces.ifaddresses(interface).get(netifaces.AF_INET, [])
    except ValueError:
        return None
    return next((e['addr'] for e in entries if e.get('addr')), None)

class Announcer:
    """A send-only socket on an interface other than the selected one, which
    announces this client there and takes nothing in.

    It follows the interface's current address: it rebinds when the address
    changes, and sends nothing while the interface has none. It is bound to an
    ephemeral port and never read, so nothing arriving on that interface
    reaches the registry."""

    def __init__(self, interface:str) -> None:
        self.interface = interface
        self._bound:tuple[str, socket.socket]|None = None

    def _socket_for(self, address:str) -> socket.socket:
        """The socket for address, rebound when the interface's address has
        changed since the last send."""
        if (self._bound is None) or (self._bound[0] != address):
            self.close()
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.bind((address, 0))
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            # Linux already sends multicast by the interface holding the bound
            # address; other systems route it by the group unless told.
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(address))
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, MULTICAST_TTL)
            self._bound = (address, sock)
        return self._bound[1]

    def announce(self, data:bytes, reach:list[tuple[str|None, int]]) -> int:
        """Write data to every place in reach by this interface: an address
        and port, or None for the interface's subnet broadcast address, on
        that port. Returns the bytes the last write took; 0, sending nothing,
        while the interface has no address."""
        if ((address := address_of(self.interface)) is None):
            self.close()
            return 0
        sock = self._socket_for(address)
        sent = 0
        for ip, port in reach:
            if (ip is None) and ((ip := mxr_broadcast_address(address)) is None):
                continue
            sent = sock.sendto(data, (ip, port))
        return sent

    def close(self) -> None:
        if (self._bound is not None):
            self._bound[1].close()
            self._bound = None

class _Endpoint(asyncio.DatagramProtocol):
    ''' one endpoint: a socket receiving on its port and one sending to its target '''
    def __init__(self, owner:'ConnectionAsync', target_ip:str, port:int, local_ip:str|None, path:Endpoints) -> None:
        self._owner = owner
        self._transport:asyncio.DatagramTransport|None = None
        self._target_ip = target_ip
        self._port = port
        self._local_ip = local_ip
        self._path = path
        self._tx_socket:socket.socket|None = None
        self._rx_socket:socket.socket|None = None
        self._loop:asyncio.AbstractEventLoop|None = None
        self.arrival:int|None = None
        '''The index of the one interface datagrams are taken from, None for
        any.'''
        super().__init__()

    @property
    def path(self) -> Endpoints:
        return self._path

    @property
    def target_ip(self) -> str:
        return self._target_ip

    @property
    def port(self) -> int:
        return self._port

    @property
    def is_multicast(self) -> bool:
        return ipaddress.IPv4Address(self.target_ip).is_multicast

    def _create_tx_socket(self) -> socket.socket:
        local_ip = self._local_ip
        if local_ip is None:
            raise Exception("failed to find local ip address")
        _LOGGER.debug(f"open tx socket {local_ip}:{self.port}")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        if self.is_multicast:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, MULTICAST_TTL)
        else:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        if is_posix_os():
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            sock.bind((local_ip, self.port))

        return sock

    def _create_rx_socket(self) -> socket.socket|None:
        _LOGGER.debug(f"open rx socket {self.target_ip}:{self.port}")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if is_posix_os():
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

        # INADDR_ANY rather than the group address: a directed frame addressed to
        # this host's own address then arrives alongside the group traffic. See
        # the note at the top of this module.
        sock.bind(('', self.port))

        if self.is_multicast:
            if (self._local_ip is None):
                sock.close()
                return None
            sock.setsockopt(
                socket.IPPROTO_IP,
                socket.IP_ADD_MEMBERSHIP,
                socket.inet_aton(self.target_ip) + socket.inet_aton(self._local_ip)
            )
            _LOGGER.debug(f"rx multicast joined")
        else:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        if (self.arrival is not None):
            sock.setsockopt(socket.IPPROTO_IP, IP_PKTINFO, 1)
        return sock

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._tx_socket = self._create_tx_socket()
        rx = self._create_rx_socket()
        if (self.arrival is None) or (rx is None):
            await loop.create_datagram_endpoint(lambda: self, sock=rx)
            return
        # Reading the arrival interface takes recvmsg(), which a datagram
        # transport does not offer.
        rx.setblocking(False)
        self._rx_socket, self._loop = rx, loop
        loop.add_reader(rx.fileno(), self._read)
        _LOGGER.debug(f"listening on {self.target_ip}:{self.port}, interface {self.arrival} only")

    def _read(self) -> None:
        '''Take every datagram waiting, dropping one that arrived on an
        interface other than the selected one, or whose arrival is unknown.'''
        sock = self._rx_socket
        while (sock is not None):
            try:
                data, ancillary, _, addr = sock.recvmsg(_READ_MAX, socket.CMSG_SPACE(_PKTINFO_SIZE))
            except (BlockingIOError, InterruptedError):
                return
            except OSError as e:
                _LOGGER.debug(f"receive on {self.target_ip}:{self.port} failed: {e}")
                return
            arrived = next((struct.unpack_from('=i', cdata)[0] for level, kind, cdata in ancillary
                            if (level == socket.IPPROTO_IP) and (kind == IP_PKTINFO)
                            and (len(cdata) >= _PKTINFO_SIZE)), 0)
            if (arrived == self.arrival):
                self._owner._received(data, addr, self._path)

    def close(self) -> None:
        if (self._transport is not None):
            self._transport.close()
            self._transport = None
        if (self._rx_socket is not None):
            if (self._loop is not None) and not self._loop.is_closed():
                self._loop.remove_reader(self._rx_socket.fileno())
            self._rx_socket.close()
            self._rx_socket = None
        if (self._tx_socket is not None):
            self._tx_socket.close()
            self._tx_socket = None

    def connection_made(self, transport:asyncio.BaseTransport) -> None:
        _LOGGER.debug(f"listening on {self.target_ip}:{self.port}")
        self._transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        self._owner._received(data, addr, self._path)

    def transmit(self, data: bytes) -> int:
        if (self._tx_socket is None):
            return 0
        return self._tx_socket.sendto(data, (self.target_ip, self.port))

class ConnectionAsync:
    ''' send and receive UDP data, by both endpoints a unit has '''
    def __init__(self, callbacks:ConnectionCallbacks, local_ip:str|None=None, target_ip:str|None=None, port:int|None=None) -> None:
        '''Both endpoints a unit has on the interface at local_ip, or the first
        one found.

        target_ip replaces them with one endpoint on that address and port
        (8812 when unset), so a test or development setup runs on a scratch
        address rather than a live network. A client on one endpoint sends every
        frame by it and does not tell paths apart.

        On Linux, an interface selected by local_ip is the only one datagrams
        are taken from, so a device reachable only by another interface stays
        unknown; start_srv() fails when no interface holds the address.
        Elsewhere, broadcasts on every interface still arrive.'''
        self._callbacks = callbacks
        self._local_ip = local_ip
        self._selected = local_ip or None
        self._closed = True
        if (target_ip is not None):
            self._endpoints = [_Endpoint(self, target_ip, port or MX_MCAST_UDP_PORT, self.local_ip,
                                         Endpoints.MULTICAST if ipaddress.IPv4Address(target_ip).is_multicast
                                         else Endpoints.BROADCAST)]
            return
        self._endpoints = [_Endpoint(self, MX_MCAST_UDP_IP, MX_MCAST_UDP_PORT, self.local_ip, Endpoints.MULTICAST)]
        if ((broadcast := mxr_broadcast_address(self.local_ip)) is not None):
            self._endpoints.append(_Endpoint(self, broadcast, MX_BCAST_UDP_PORT, self.local_ip, Endpoints.BROADCAST))
        else:
            _LOGGER.warning("failed to determine the broadcast address, running the multicast endpoint alone")

    @property
    def endpoints(self) -> tuple[_Endpoint, ...]:
        return tuple(self._endpoints)

    @property
    def is_dual(self) -> bool:
        '''Whether both endpoints are open, and so paths are told apart.'''
        return (len(self._endpoints) == 2)

    @property
    def is_open(self) -> bool:
        return not self._closed

    @property
    def local_ip(self) -> str|None:
        if (self._local_ip is None) or (len(self._local_ip) == 0):
            addresses = mxr_valid_addresses()
            if len(addresses) > 0:
                self._local_ip = addresses[0]
        return self._local_ip

    async def start_srv(self) -> None:
        '''Open every endpoint, and report the connection made.'''
        _LOGGER.debug("starting service on " + ", ".join(f"{e.target_ip}:{e.port}" for e in self._endpoints))
        try:
            arrival = arrival_for(self._selected)
            for endpoint in self._endpoints:
                endpoint.arrival = arrival
                await endpoint.start()
        except Exception as e:
            _LOGGER.warning(f"failed to start mx_remote service: {e}")
            self.close()
            raise
        self._closed = False
        self._callbacks.on_connection_made()

    def close(self) -> None:
        '''Close every endpoint.'''
        for endpoint in self._endpoints:
            endpoint.close()
        self._closed = True

    def reach(self) -> list[tuple[str|None, int]]:
        '''Where a frame goes on an interface this client only announces
        itself on: the place each endpoint sends to, a broadcast as that
        interface's own subnet broadcast.'''
        return [(None if (e.path == Endpoints.BROADCAST) else e.target_ip, e.port) for e in self._endpoints]

    def _received(self, data: bytes, addr: Tuple[str, int], path:Endpoints) -> None:
        self._callbacks.on_datagram_received(data, addr, path if self.is_dual else None)

    def transmit(self, data: bytes, endpoints:Endpoints=Endpoints.MULTICAST) -> int:
        '''Send a datagram by endpoints, returning the bytes the first of them
        took, or 0 when closed. A client on one endpoint sends everything by it.'''
        if self._closed:
            return 0
        if not self.is_dual:
            return self._endpoints[0].transmit(data)
        sent = None
        for endpoint in self._endpoints:
            if (endpoint.path in endpoints):
                n = endpoint.transmit(data)
                sent = n if (sent is None) else sent
        return sent or 0
