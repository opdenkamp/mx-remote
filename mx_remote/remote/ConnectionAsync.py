##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

import asyncio
import logging
import os
import socket
import ipaddress
from typing import Coroutine, Tuple
from ..Interface import ConnectionCallbacks, mxr_valid_addresses

_LOGGER = logging.getLogger(__name__)

def is_posix_os() -> bool:
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
        self._tx_socket:socket.socket = None
        super().__init__()

    @property
    def tx_socket(self) -> socket.socket:
        return self._tx_socket

    @property
    def is_open(self) -> bool:
        return (self._transport is not None) and (not self._closed)

    @property
    def target_ip(self) -> str:
        return self._target_ip

    @property
    def port(self) -> str:
        return self._port

    @property
    def local_ip(self) -> str:
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

    def _create_rx_socket(self) -> socket.socket:
        _LOGGER.debug(f"open rx socket {self.target_ip}:{self.port}")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if is_posix_os():
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

        sock.bind(('', self.port))

        if self.is_multicast:
            sock.setsockopt(
                socket.IPPROTO_IP,
                socket.IP_ADD_MEMBERSHIP,
                socket.inet_aton(self.target_ip) + socket.inet_aton(self.local_ip)
            )
            _LOGGER.debug(f"rx multicast joined")
        else:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        return sock

    async def start_srv(self) -> Coroutine:
        _LOGGER.debug(f"starting service on {self.target_ip}:{self.port}")
        try:
            loop = asyncio.get_event_loop()
            self._closed = False
            self._tx_socket = self._create_tx_socket()
            return await loop.create_datagram_endpoint(
                    lambda: self, sock=self._create_rx_socket())
        except Exception as e:
            _LOGGER.warning(f"failed to start mx_remote service: {e}")
            raise

    def close(self) -> None:
        if self.is_open:
            _LOGGER.debug(f"closing {self.target_ip}:{self.port}")
            self._transport.close()
            self._closed = True

    def connection_made(self, transport:asyncio.DatagramTransport) -> None:
        _LOGGER.debug(f"listening on {self.target_ip}:{self.port} - {str(type(transport))}")
        self._transport = transport
        self._callbacks.on_connection_made()

    def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        self._callbacks.on_datagram_received(data, addr)

    def transmit(self, data: bytes) -> int:
        if self._closed:
            return 0

        _LOGGER.debug(f"tx to {self.target_ip}:{self.port} (mcast:{self.is_multicast})")
        return self.tx_socket.sendto(data, (self.target_ip, self.port))
