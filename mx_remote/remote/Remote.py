######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Remote device discovery and management over UDP multicast/broadcast.'''

from functools import cached_property
import logging
import asyncio
from typing import Any, override
import aiofiles
import aiohttp
import os
from pathlib import Path
import random
import time

from .ConnectionAsync import ConnectionAsync
from ..const import MXR_HELLO_INTERVAL_MIN, MXR_HELLO_INTERVAL_RAND, __version__
from .Device import Device
from ..Interface import ConnectionCallbacks, DeviceRegistry, MxrDeviceUid, BayLinks, BayBase, DeviceBase, MxrCallbacks, AudioEndpoint, mxr_broadcast_address
from ..proto.Constants import MXR_PROTOCOL_VERSION
from ..proto.FrameDiscover import constructFrameDiscover
from ..proto.Factory import process_mxr_frame
from ..proto.FrameHello import FrameHello, constructFrameHello
from ..proto.Svd import SvdMap
from ..Uid import MxrDeviceUid
from .State import State

import traceback

from ..const import MX_BCAST_UDP_PORT, MX_MCAST_UDP_IP, MX_MCAST_UDP_PORT

_LOGGER = logging.getLogger(__name__)

# The opcodes a device accepts from a sender it has no record of: the
# announcement itself, and the request for one.
_ACCEPT_UNANNOUNCED = (0x00, 0x01)

class Remote(DeviceRegistry, ConnectionCallbacks):
    ''' Main component that handles the network connections and registration of remote devices '''

    def __init__(self, target_ip:str|None=None, port:int|None=None, http_session:aiohttp.ClientSession|None=None, open_connection:bool=True, callbacks:MxrCallbacks|None=None, name:str="MXR Python", local_ip:str|None=None, broadcast:bool|None=None, addr_filter:str|None=None, uid_path:str|None=None) -> None:
        '''Initialise the remote controller.

        :param target_ip: multicast/broadcast IP to use, or None for the default
        :param port: UDP port to use, or None for the default
        :param http_session: shared aiohttp session for API calls, or None to create one
        :param open_connection: open the UDP connection immediately when True
        :param callbacks: event callbacks for device state changes
        :param name: human-readable name advertised on the network
        :param local_ip: local interface IP to bind to, or None for any
        :param broadcast: use broadcast instead of multicast when True
        :param addr_filter: only log frames from this IP address when set
        :param uid_path: file holding this client's uid, or None for ~/.mxr-uid.
            Give concurrent clients on one host separate paths - see _load_uid
        '''
        DeviceRegistry.__init__(self)
        ConnectionCallbacks.__init__(self)
        self._name = name
        self._closing = False
        self._own_session = (http_session is None)
        self._callbacks = State(callbacks, http_session)
        self.remotes:dict[MxrDeviceUid,Device] = {}
        self._links = BayLinks(self)
        self._hello_due = 0.0
        self._probe_failures = 0
        self._tasks:set[asyncio.Task[None]] = set()
        self._uid:bytes|None = None
        self._uid_path = uid_path
        self._local_ip = local_ip
        self._broadcast = broadcast
        self._target_ip = target_ip
        self._port = port
        self._discover_timeout = 0
        self._addr_filter = addr_filter
        self._svd = SvdMap()
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

    @cached_property
    def target_ip(self) -> str:
        if self._target_ip is None:
            if self._broadcast is None or not self._broadcast:
                return MX_MCAST_UDP_IP
            bcast = mxr_broadcast_address(self._local_ip)
            if bcast is not None:
                return bcast
            _LOGGER.warning("failed to determine broadcast address, using multicast")
            return MX_MCAST_UDP_IP
        return self._target_ip

    @property
    def local_ip(self) -> str|None:
        return self._local_ip

    @property
    def broadcast(self) -> bool:
        return ((self._broadcast is not None) and self._broadcast)

    @property
    def port(self) -> int:
        if self._port is None:
            return MX_MCAST_UDP_PORT if (self._broadcast is None or not self._broadcast) else MX_BCAST_UDP_PORT
        return self._port

    async def _load_uid(self) -> None:
        '''Load this client's uid, generating and persisting one if absent.

        The uid is this client's identity on the mesh: addressing is by uid in
        the payload, and process_frame() drops any frame whose remote_id is our
        own. Two clients sharing a uid are therefore one peer to every device,
        and each silently discards everything the other sends. Pass separate
        uid_path values to run concurrent clients from one account.
        '''
        if self._uid is not None:
            return
        uid_path = Path(self._uid_path) if (self._uid_path is not None) else Path.home().joinpath(".mxr-uid")
        try:
            async with aiofiles.open(uid_path, "rb") as f:
                self._uid = await f.read()
        except Exception:
            _LOGGER.info(f"failed to read {uid_path}. creating new file")
            self._uid = os.urandom(16)
            async with aiofiles.open(uid_path, "wb") as f:
                await f.write(self._uid)
        # clear cached uid so it gets recomputed with the loaded value
        vars(self).pop('uid', None)

    @property
    def uid_raw(self) -> bytes|None:
        return self._uid

    @cached_property
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

    @property
    def svd_map(self) -> SvdMap:
        return self._svd

    async def update_config(self, callbacks:MxrCallbacks|None=None, name:str|None=None, target_ip:str|None=None, port:int|None=None, local_ip:str|None=None, broadcast:bool|None=None) -> None:
        '''Update runtime configuration, reconnecting if network parameters changed.'''
        if (callbacks is not None):
            self._callbacks = State(callbacks, self.http_session)
        if (name is not None):
            self._name = name
        if (target_ip is not None) or (port is not None) or (local_ip is not None) or (broadcast is not None):
            changed = False
            if (target_ip is not None) and (self._target_ip != target_ip):
                _LOGGER.debug(f"updating target ip to {target_ip}")
                self._target_ip = target_ip
                del self.target_ip
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
        '''Return True if at least one registered device has completed configuration.'''
        for _, device in self.remotes.items():
            if device.configuration_complete:
                return True
        return False

    def _on_task_done(self, task:'asyncio.Task[None]') -> None:
        '''Drop a finished background task, and report it if something killed it.

        asyncio only surfaces an unretrieved task exception when the task object is
        garbage collected, which is a different moment and may never come, so a task
        that dies otherwise does so in silence. Retrieving it here is what makes any
        future background task fail loudly, including one whose own guard misses.
        '''
        self._tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if (exc is not None):
            _LOGGER.error(f"background task {task.get_name()} died: {exc!r}")

    async def _background_probe(self) -> None:
        while not self._closing:
            await asyncio.sleep(1)
            try:
                self._probe_once()
                self._probe_failures = 0
            except Exception as e:
                # A send raises on a closed or unreachable socket. Letting that
                # escape ends the task, and this loop is the only thing that
                # announces this client and drives discovery, so one transient
                # failure would silence it permanently.
                #
                # A disconnected interface fails every tick, so only the first
                # carries a traceback: a full one per second buries everything
                # else in the log, and the repeats say nothing the first did not.
                self._probe_failures += 1
                if (self._probe_failures == 1):
                    _LOGGER.warning(f"probe failed: {traceback.format_exc()}")
                else:
                    _LOGGER.debug(f"probe still failing ({self._probe_failures}): {e!r}")

    def _probe_once(self) -> None:
        '''One pass of the probe loop: announce if due, then discover if needed.'''
        if (time.time() >= self._hello_due):
            self.tx_hello()
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
        '''Start the server that listens for mx_remote frames from other devices.'''
        if (self.conn is None):
            raise Exception("connection not open")
        await self._load_uid()
        await self.conn.start_srv()
        # Announce before anything else can be sent. A device drops every frame
        # from a uid it has no record of, except hello and discover, so a
        # command issued between here and the probe loop's first pass would be
        # dropped by every peer that has not seen us - silently, since nothing
        # answers a frame it discarded.
        #
        # The discover behind it makes each peer hello back rather than waiting
        # out its own announce interval. It goes second so a peer has our
        # announce before it answers.
        self.tx_hello()
        self.tx_discover()
        checker = asyncio.create_task(self._background_probe())
        self._tasks.add(checker)
        checker.add_done_callback(self._on_task_done)

    async def stop_async(self) -> None:
        '''Stop the server and close all connections.'''
        await self.close()

    async def close(self) -> None:
        '''Close all open connections and cancel background tasks.'''
        _LOGGER.debug("closing mx_remote listener")
        self._closing = True
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self.conn is not None:
            self.conn.close()
        if self._own_session:
            await self.http_session.close()

    def get_by_serial(self, serial:str) -> DeviceBase|None:
        '''Get the cached device matching the given serial number, or None.'''
        for _, remote in self.remotes.items():
            if serial == remote.serial:
                return remote
        return None

    def get_by_uid(self, remote_id:str|MxrDeviceUid|None) -> DeviceBase|None:
        '''Get the cached device matching the given unique id, or None.'''
        if (remote_id is None):
            return None
        uid = MxrDeviceUid(remote_id)
        if uid in self.remotes.keys():
            return self.remotes[uid]
        if isinstance(remote_id, str):
            return self.get_by_serial(serial=remote_id)
        return None

    def uid_to_user_string(self, remote_id:str|MxrDeviceUid|bytes|None) -> str:
        if (remote_id is None):
            return '<none>'
        if not isinstance(remote_id, MxrDeviceUid):
            remote_id = MxrDeviceUid(remote_id)
        if remote_id in self.remotes.keys():
            return self.remotes[remote_id].serial
        return str(remote_id)

    def get_by_stream_ip(self, ip:str, audio:bool=False) -> BayBase|None:
        for _, dev in self.remotes.items():
            if not dev.is_v2ip or dev.v2ip_sources is None or dev.first_input is None:
                continue
            if not audio and (dev.first_input.v2ip_source is not None) and (dev.first_input.v2ip_source.video.ip == ip):
                return dev.first_input
            if audio and (dev.first_input.v2ip_source is not None) and (dev.first_input.v2ip_source.audio.ip == ip):
                return dev.first_input
        return None
    
    def get_bay_by_portnum(self, remote_id:str|MxrDeviceUid, portnum:int) -> BayBase|None:
        '''Get the cached bay for a device, given the device id and port number.'''
        device = self.get_by_uid(remote_id=remote_id) if isinstance(remote_id, MxrDeviceUid) else self.get_by_serial(serial=remote_id)
        if device is None:
            return None
        return device.get_by_portnum(portnum)

    def get_bay_by_portname(self, remote_id:str|MxrDeviceUid, portname:str) -> BayBase|None:
        device = self.get_by_uid(remote_id=remote_id) if isinstance(remote_id, MxrDeviceUid) else self.get_by_serial(serial=remote_id)
        if device is None:
            return None
        return device.get_by_portname(portname=portname)

    def get_audio_endpoint(self, device:MxrDeviceUid, id:int) -> AudioEndpoint|None:
        dev = self.get_by_uid(remote_id=device)
        if (dev is not None):
            return dev.audio_endpoint_by_id(id=id)
        return None

    @property
    def links(self) -> BayLinks:
        return self._links

    def transmit(self, data: bytes) -> int:
        '''Transmit raw data over the UDP connection. Returns bytes sent.'''
        if (self.conn is None):
            raise Exception("connection closed")
        return self.conn.transmit(data=data)

    def tx_discover(self) -> int:
        '''Transmit a discover frame. All remotes will respond with a hello frame.'''
        pkt = constructFrameDiscover(self)
        if (pkt is None):
            return 0
        self._discover_timeout = time.time()
        _LOGGER.debug("discovering devices")
        return self.transmit(pkt.frame)

    def _arm_hello(self) -> None:
        '''Schedule the next announcement, mirroring the firmware's hello timer.

        MatrixOS re-draws min 2.5s + random(0..2.5s) after each hello it sends,
        so a mesh of devices does not synchronise into bursts. The interval is
        re-drawn per send rather than fixed for the same reason.
        '''
        self._hello_due = time.time() + MXR_HELLO_INTERVAL_MIN \
            + (random.random() * MXR_HELLO_INTERVAL_RAND)

    def tx_hello(self) -> int:
        '''Transmit a hello frame to announce this device on the network.'''
        pkt = constructFrameHello(self)
        if (pkt is None):
            return 0
        _LOGGER.debug("sending hello")
        sent = self.transmit(pkt.frame)
        if (sent > 0):
            # Only a hello that went out buys the next interval. A send that wrote
            # nothing leaves _hello_due where it was, so the next probe tick tries
            # again, which is what firmware does - it resets hello_timeout only in
            # the success branch of mxr_transmit. Arming here on failure instead
            # would silence a client for a full interval every time a write failed,
            # and on an interface that never writes, permanently.
            self._arm_hello()
        return sent

    def on_connection_made(self) -> None:
        '''Callback invoked after ConnectionAsync has started the server.'''
        self.tx_hello()
        self.tx_discover()

    def process_frame(self, timestamp:float, data: bytes, addr: tuple[str, int]) -> None:
        '''Decode and process a received mx_remote frame.'''
        proc = False
        try:
            frame = process_mxr_frame(mxr=self, timestamp=timestamp, data=data, addr=addr)
            if (frame is not None) and (frame.header.protocol > MXR_PROTOCOL_VERSION):
                # The stamp is the version at which this opcode's payload last
                # changed, not the sender's version. Above ours means this
                # opcode's layout is newer than we know: the frames we would
                # decode into wrong state, and the ones devices drop before
                # dispatch.
                #
                # A release raises the stamp only where a layout moved, so this
                # silences those opcodes until the library is bumped, not the
                # mesh.
                _LOGGER.debug(f"rx {addr[0]}: opcode {frame.header.opcode:02X} needs protocol "
                              f"{frame.header.protocol:02X}, this build knows {MXR_PROTOCOL_VERSION:02X}")
                frame = None
            if (frame is not None) and (frame.header.remote_id != self.uid):
                # A device announces itself before it sends anything else, so a
                # frame from a uid with no record is one no device would act on.
                # Decode and report it - this library is also used to watch the
                # bus - but keep it out of the cache and the callbacks.
                #
                # Hello and discover are exempt: the hello is what makes a
                # sender known, so gating it leaves it unknown forever.
                proc = (frame.remote_device is not None) \
                    or (frame.header.opcode in _ACCEPT_UNANNOUNCED)
                if (self._addr_filter is None) or (addr[0] == self._addr_filter):
                    ts = f'[{timestamp}] ' if (self.conn is None) else ''
                    skipped = '' if proc else ' (sender has not announced)'
                    _LOGGER.debug(f"{ts}rx {addr[0]}: {frame.header.opcode:02X}({len(frame)}) - {str(frame)}{skipped}")
        except Exception:
            _LOGGER.warning(f"failed to decode frame {traceback.format_exc()}")
            raise
        try:
            if (frame is not None) and proc:
                frame.process()
        except Exception:
            _LOGGER.warning(f"failed to process frame: {traceback.format_exc()}")
            raise

    def on_datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        '''Called when a UDP frame was received.'''
        timestamp = time.time()
        self.process_frame(timestamp=timestamp, data=data, addr=addr)

    @override
    def on_mxr_update(self, data:Any) -> None:
        if isinstance(data, FrameHello):
            self._on_mxr_hello(data)

    def _on_mxr_hello(self, hello_frame:FrameHello) -> None:
        '''Hello frame received. Register or update the local device cache.'''
        d = self.get_by_uid(hello_frame.remote_id)
        if d is None:
            d = Device(self, hello_frame)
            self.remotes[hello_frame.remote_id] = d
        d.on_mxr_update(hello_frame)
