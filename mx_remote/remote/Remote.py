##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

import logging
import asyncio
import aiofiles
import aiohttp
import os
from pathlib import Path
import time

from .ConnectionAsync import ConnectionAsync
from ..const import __version__
from .Device import Device
from ..Interface import ConnectionCallbacks, DeviceRegistry, MxrDeviceUid, BayLinks, BayBase, DeviceBase, MxrCallbacks
from ..proto.Constants import MXR_PROTOCOL_VERSION
from ..proto.FrameDiscover import FrameDiscover
from ..proto.Factory import process_mxr_frame
from ..proto.FrameBase import FrameBase
from ..proto.FrameHello import FrameHello
from ..Uid import MxrDeviceUid
from .State import State

import traceback

from ..const import MX_BCAST_UDP_IP, MX_BCAST_UDP_PORT, MX_MCAST_UDP_IP, MX_MCAST_UDP_PORT

_LOGGER = logging.getLogger(__name__)

class Remote(DeviceRegistry, ConnectionCallbacks):
    ''' Main component that handles the network connections and registration of remote devices '''

    def __init__(self, target_ip:str|None=None, port:int|None=None, http_session:aiohttp.ClientSession|None=None, open_connection:bool=True, callbacks:MxrCallbacks|None=None, name:str="MXR Python", local_ip:str|None=None, broadcast:bool|None=None) -> None:
        DeviceRegistry.__init__(self)
        ConnectionCallbacks.__init__(self)
        self._name = name
        self._close_session = False
        self._http_session = None
        self._callbacks = State(callbacks, http_session)
        self.remotes:dict[MxrDeviceUid,Device] = {}
        self._links = BayLinks(self)
        self._last_hello = 0
        self._tasks = set()
        self._uid:bytes|None = None
        self._local_ip = local_ip
        self._broadcast = broadcast
        self._target_ip = target_ip
        self._port = port
        self._discover_timeout = 0
        if open_connection:
            self.conn = ConnectionAsync(callbacks=self, target_ip=self.target_ip, port=self.port, local_ip=self._local_ip)
        else:
            self.conn = None

    @property
    def library_version(self) -> str:
        ''' version of the mx_remote library '''
        return __version__

    @property
    def protocol_version(self) -> int:
        ''' protocol version used by this library '''
        return MXR_PROTOCOL_VERSION

    @property
    def net_protocol_version_max(self) -> int:
        ''' highest protocol version used by devices on the network '''
        proto = 0
        for _, device in self.remotes.items():
            if (device.protocol > proto):
                proto = device.protocol
        return proto

    @property
    def net_protocol_version_min(self) -> int:
        ''' lowest protocol version used by devices on the network '''
        proto = MXR_PROTOCOL_VERSION
        for _, device in self.remotes.items():
            if (device.protocol < proto):
                proto = device.protocol
        return proto

    @property
    def target_ip(self):
        if self._target_ip is None:
            return MX_MCAST_UDP_IP if (self._broadcast is None or not self._broadcast) else MX_BCAST_UDP_IP
        return self._target_ip

    @property
    def local_ip(self) -> str:
        return self._local_ip

    @property
    def broadcast(self) -> bool:
        return ((self._broadcast is not None) and self._broadcast)

    @property
    def port(self):
        if self._port is None:
            return MX_MCAST_UDP_PORT if (self._broadcast is None or not self._broadcast) else MX_BCAST_UDP_PORT
        return self._port

    async def _load_uid(self) -> None:
        if self._uid is not None:
            return
        uid_path = Path.home().joinpath(".mxr-uid")
        try:
            async with aiofiles.open(uid_path, "rb") as f:
                self._uid = await f.read()
        except:
            _LOGGER.info(f"failed to read {uid_path}. creating new file")
            self._uid = os.urandom(16)
            async with aiofiles.open(uid_path, "wb") as f:
                await f.write(self._uid)

    @property
    def uid_raw(self) -> bytes:
        return self._uid

    @property
    def uid(self) -> MxrDeviceUid:
        return MxrDeviceUid(self.uid_raw)

    @property
    def name(self) -> str:
        return self._name

    @property
    def callbacks(self) -> MxrCallbacks:
        return self._callbacks.callbacks

    @property
    def http_session(self) -> aiohttp.ClientSession:
        ''' Active HTTP client session for API commands '''
        return self._callbacks.http_session

    async def update_config(self, callbacks:MxrCallbacks|None=None, name:str|None=None, target_ip:str|None=None, port:int|None=None, local_ip:str|None=None, broadcast:bool|None=None):
        if (callbacks is not None):
            self._callbacks = callbacks
        if (name is not None):
            self._name = name
        if (target_ip is not None) or (port is not None) or (local_ip is not None) or (broadcast is not None):
            changed = False
            if (target_ip is not None) and (self._target_ip != target_ip):
                _LOGGER.debug(f"updating target ip to {target_ip}")
                self._target_ip = target_ip
                changed = True
            if (port is not None) and (self._port != port):
                _LOGGER.debug(f"updating target port to {port}")
                self._port = port
                changed = True
            if (local_ip is not None) and (self._local_ip != local_ip):
                _LOGGER.debug(f"updating target ip to {local_ip}")
                self._local_ip = local_ip
                changed = True
            if (broadcast is not None) and (self._broadcast != broadcast):
                _LOGGER.debug(f"updating target ip to {broadcast}")
                self._broadcast = broadcast
                changed = True
            if changed:
                if (self.conn is not None):
                    _LOGGER.debug(f"closing connection")
                    self.conn.close()
                _LOGGER.debug(f"opening new mx_remote listener on target={self.target_ip} listener={self._local_ip}:{self.port}")
                self.conn = ConnectionAsync(callbacks=self, target_ip=self.target_ip, port=self.port, local_ip=self._local_ip)
                await self.conn.start_srv()

    def has_completed_devices(self) -> bool:
        for _, device in self.remotes.items():
            if device.configuration_complete:
                return True
        return False

    async def _background_probe(self) -> None:
        while not self._close_session:
            await asyncio.sleep(1)
            tx_discover = False
            if (not self.has_completed_devices()):
                tx_discover = True
            else:
                for _, device in self.remotes.items():
                    device.check_online()
                    if not device.check_configuration_complete_timeout():
                        tx_discover = True
            if tx_discover and ((time.time() - self._discover_timeout) >= 5):
                self.tx_discover()

    async def start_async(self) -> None:
        # start the server that listens for mx_remote frames from other devices
        await self._load_uid()
        await self.conn.start_srv()
        checker = asyncio.create_task(self._background_probe())
        self._tasks.add(checker)
        checker.add_done_callback(self._tasks.discard)

    async def close(self) -> None:
        # close all open connections
        _LOGGER.debug("closing mx_remote listener")
        if self.conn is not None:
            self.conn.close()
        if self._close_session:
            await self.http_session.close()

    def get_by_serial(self, serial:str) -> DeviceBase|None:
        # get the local cache for a device, given it's serial number
        for _, remote in self.remotes.items():
            if serial == remote.serial:
                return remote
        return None

    def get_by_uid(self, remote_id:str|MxrDeviceUid) -> DeviceBase|None:
        # get the local cache for a device, given it's unique id
        remote_id = MxrDeviceUid(remote_id)
        if remote_id in self.remotes.keys():
            return self.remotes[remote_id]
        if isinstance(remote_id, str):
            return self.get_by_serial(serial=remote_id)
        return None

    def get_by_stream_ip(self, ip:str, audio:bool=False) -> BayBase|None:
        for _, dev in self.remotes.items():
            if not dev.is_v2ip or dev.v2ip_sources is None or dev.first_input is None:
                continue
            if not audio and (dev.first_input.v2ip_source.video.ip == ip):
                return dev.first_input
            if audio and (dev.first_input.v2ip_source.audio.ip == ip):
                return dev.first_input
        return None
    
    def get_bay_by_portnum(self, remote_id:str|MxrDeviceUid, portnum:int) -> BayBase|None:
        # get the local cache for a bay, given the device's unique id and port number
        device = self.get_by_uid(remote_id=remote_id) if isinstance(remote_id, MxrDeviceUid) else self.get_by_serial(serial=remote_id)
        if device is None:
            return None
        return device.get_by_portnum(portnum)

    def get_bay_by_portname(self, remote_id:str|MxrDeviceUid, portname:str) -> BayBase|None:
        device = self.get_by_uid(remote_id=remote_id) if isinstance(remote_id, MxrDeviceUid) else self.get_by_serial(serial=remote_id)
        if device is None:
            return None
        return device.get_by_portname(portname=portname)

    @property
    def links(self) -> BayLinks:
        return self._links

    def transmit(self, data: bytes) -> int:
        return self.conn.transmit(data=data)

    def tx_discover(self) -> int:
        # transmit a discover frame. all remotes will send a hello frame as response
        pkt:FrameBase = FrameDiscover.construct(self)
        self._discover_timeout = time.time()
        _LOGGER.debug("discovering devices")
        return self.transmit(pkt.frame)

    def tx_hello(self):
        pkt:FrameBase = FrameHello.construct(self)
        _LOGGER.debug("sending hello")
        self._last_hello = time.time()
        return self.transmit(pkt.frame)

    def on_connection_made(self) -> None:
        # callback called after the server got started by ConnectionAsync
        self.tx_discover()
        self.tx_hello()

    def on_datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        # called when a udp frame was received
        try:
            frame = process_mxr_frame(self, data, addr)
            if frame is not None:
                _LOGGER.debug(f"rx {addr[0]}: {frame.header.opcode:02X}({len(frame)}) - {str(frame)}")
        except Exception as e:
            _LOGGER.warning(f"failed to decode frame {traceback.format_exc()}")
            raise
        try:
            if frame is not None:
                frame.process()
        except Exception as e:
            _LOGGER.warning(f"failed to process frame: {traceback.format_exc()}")
            raise

        if self.conn is not None:
            now = time.time()
            if (now - self._last_hello >= 30):
                self.tx_hello()

    def on_mxr_hello(self, hello_frame:FrameHello) -> Device:
        # hello frame received. register or update the local device cache
        d = self.get_by_uid(hello_frame.remote_id)
        if d is None:
            d = Device(self, hello_frame)
            self.remotes[hello_frame.remote_id] = d
        d.on_mxr_hello(hello_frame)
        return d
