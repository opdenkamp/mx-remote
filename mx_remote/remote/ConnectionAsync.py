######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Async UDP connection for MX Remote multicast/broadcast communication.'''

import asyncio
import logging
import os
import socket
import ipaddress
from typing import Tuple
from ..Interface import ConnectionCallbacks, mxr_valid_addresses

_LOGGER = logging.getLogger(__name__)

# Delivery is to a group today, but that is an implementation detail of the
# current firmware rather than a property of the protocol - do not build on it.
#
# A device has two endpoints, both group addresses: the multicast group and the
# interface broadcast address. MX_TX_ACTIVE sends to the multicast endpoint
# unconditionally and to the broadcast one when some peer needs broadcast, and
# MX_TX_DIRECT picks between the two. Nothing resolves a per-device address, so
# every frame currently reaches every listener. But mxr_transmit() already
# threads an mx_remote_devptr through the endpoint selection specifically so
# directed sends can be added without reshaping the transmit path, and the
# motivation is mesh scale: past some member count, having every unit process
# every frame stops paying.
#
# Two things follow, and both are already true here - keep them true:
#
#   - The rx socket binds INADDR_ANY rather than the group address, so a frame
#     addressed to this host's own address arrives alongside the group traffic.
#     Joining the group and nothing else would be correct today and would
#     silently stop seeing directed frames later.
#   - State has an active path behind it, not just overhearing. The device
#     cache is refreshed by transmitting SYS_DISCOVER (0x01) rather than only
#     by waiting for a hello - see Remote._background_probe(). Anything
#     populated purely by listening to traffic between two other devices
#     degrades quietly if directed sends arrive.
#
# Addressing in this protocol is by uid in the payload, never by IP: a frame
# reaching this socket is not necessarily addressed to us, and one addressed to
# us is not necessarily the only copy on the wire. Demultiplex on the uid.
#
# The active path is SYS_DISCOVER (0x01), and it is not per-opcode. A device
# receiving one answers with a hello immediately and then, after a deliberate
# jitter, runs _mxr_broadcast_all() - hello, mesh, bay config (0x26 rides inside
# it), signal status, link config, the bsp set including device config and EDID
# and net link, rc settings, topology, temperatures and firmware versions. One
# discover re-announces essentially everything this library caches.
#
# So do not go looking for a request form per opcode: 0x02, 0x26 and 0x3C have
# none and drop anything shorter than a full report. 0x26 is the trap - a
# zero-length frame passes its length guard, iterates nothing and answers
# nothing, so probing it looks like a device ignoring you rather than an opcode
# that was never a request.
#
# Three properties worth building against:
#   - The answer goes to the group, not to us. We overhear a broadcast our own
#     frame provoked, which is the case that makes the INADDR_ANY bind matter:
#     a client bound to the group address sees all of this and looks healthy.
#   - It is jittered on purpose, so a mesh does not answer in one millisecond.
#     No immediate reply is normal, not a timeout.
#   - It is expensive and mesh-wide. Remote._background_probe() rate-limits to
#     one every 5s and stops once every known device reports complete, which is
#     the right instinct - after that the device's own periodic broadcast timer
#     maintains the state unasked.
#
# One genuine omission remains: signal status (0x31) has a targeted request form
# of its own - an empty payload to ask everyone, or a 16-byte uid to ask one
# unit - and this library never sends it. Everything else is provoked at startup
# rather than merely overheard.

def is_posix_os() -> bool:
    '''Return True if the current OS is POSIX-compatible.'''
    return (os.name == 'posix')

class ConnectionAsync(asyncio.DatagramProtocol):
    ''' send and receive UDP data '''
    def __init__(self, callbacks:ConnectionCallbacks, target_ip:str, port:int, local_ip:str|None=None) -> None:
        self._transport = None
        self._callbacks = callbacks
        self._target_ip = target_ip
        self._local_ip = local_ip
        self._port = port
        self._closed = False
        self._tx_socket:socket.socket|None = None
        super().__init__()

    @property
    def tx_socket(self) -> socket.socket|None:
        return self._tx_socket

    @property
    def is_open(self) -> bool:
        return (self._transport is not None) and (not self._closed)

    @property
    def target_ip(self) -> str:
        return self._target_ip

    @property
    def port(self) -> int:
        return self._port

    @property
    def local_ip(self) -> str|None:
        if (self._local_ip is None) or (len(self._local_ip) == 0):
            addresses = mxr_valid_addresses()
            if len(addresses) > 0:
                self._local_ip = addresses[0]
        return self._local_ip

    @property
    def is_multicast(self) -> bool:
        return ipaddress.IPv4Address(self.target_ip).is_multicast

    def _create_tx_socket(self) -> socket.socket:
        local_ip = self.local_ip
        if local_ip is None:
            raise Exception("failed to find local ip address")
        _LOGGER.debug(f"open tx socket {local_ip}:{self.port}")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        if self.is_multicast:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 3)
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
            if (self.local_ip is None):
                sock.close()
                return None
            sock.setsockopt(
                socket.IPPROTO_IP,
                socket.IP_ADD_MEMBERSHIP,
                socket.inet_aton(self.target_ip) + socket.inet_aton(self.local_ip)
            )
            _LOGGER.debug(f"rx multicast joined")
        else:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        return sock

    async def start_srv(self) -> tuple[asyncio.DatagramTransport, 'ConnectionAsync']:
        '''Start the UDP datagram service and return the transport and protocol.'''
        _LOGGER.debug(f"starting service on {self.target_ip}:{self.port}")
        try:
            loop = asyncio.get_running_loop()
            self._closed = False
            self._tx_socket = self._create_tx_socket()
            return await loop.create_datagram_endpoint(
                    lambda: self, sock=self._create_rx_socket())
        except Exception as e:
            _LOGGER.warning(f"failed to start mx_remote service: {e}")
            raise

    def close(self) -> None:
        '''Close the connection and underlying transport.'''
        if self.is_open:
            _LOGGER.debug(f"closing {self.target_ip}:{self.port}")
            if (self._transport is not None):
                self._transport.close()
            if (self._tx_socket is not None):
                self._tx_socket.close()
                self._tx_socket = None
            self._closed = True

    def connection_made(self, transport:asyncio.DatagramTransport) -> None:
        '''Called when the datagram endpoint is established.'''
        _LOGGER.debug(f"listening on {self.target_ip}:{self.port} - {str(type(transport))}")
        self._transport = transport
        self._callbacks.on_connection_made()

    def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        '''Called when a UDP datagram is received; forwards to callbacks.'''
        self._callbacks.on_datagram_received(data, addr)

    def transmit(self, data: bytes) -> int:
        '''Send a UDP datagram to the target. Returns bytes sent, or 0 if closed.'''
        if self._closed or (self.tx_socket is None):
            return 0

        _LOGGER.debug(f"tx to {self.target_ip}:{self.port} (mcast:{self.is_multicast})")
        return self.tx_socket.sendto(data, (self.target_ip, self.port))
