import asyncio
import logging
import socket
from .const import UDP_PORT
from typing import Tuple

class ConnectionAsync(asyncio.DatagramProtocol):
    ''' send and receive UDP data '''
    def __init__(self, mxr):
        self._transport = None
        self.mxr = mxr
        super().__init__()

    @property
    def target_ip(self):
        return self.mxr.target_ip

    async def start_srv(self):
        loop = asyncio.get_event_loop()
        return await loop.create_datagram_endpoint(
                lambda: self, local_addr=(self.target_ip, UDP_PORT))

    def close(self):
        if self._transport is not None:
            self._transport.close()

    def connection_made(self, transport):
        logging.info("listening on %s:%d - %s", self.target_ip, UDP_PORT, str(type(transport)))
        self._transport = transport
        self.mxr.on_connection_made()

    def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        self.mxr.on_datagram_received(data, addr)

    def transmit(self, data: bytes):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        return sock.sendto(data, (self.target_ip, UDP_PORT))
