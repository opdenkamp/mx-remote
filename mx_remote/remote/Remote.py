######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Remote device discovery and management over UDP, by the multicast group and the subnet broadcast.'''

from functools import cached_property
import logging
import asyncio
from typing import Any
from ..compat import override
import aiofiles
import aiohttp
from collections import deque
import os
from pathlib import Path
import random
import time
import warnings
from datetime import datetime, timezone

from .ConnectionAsync import ConnectionAsync
from ..const import MXR_HELLO_INTERVAL_MIN, MXR_HELLO_INTERVAL_RAND, __version__
from .Device import Device
from .Tree import DeviceTree
from .AudioRoute import audio_path
from ..Interface import ConnectionCallbacks, DeviceRegistry, MxrDeviceUid, BayLinks, BayBase, DeviceBase, MxrCallbacks, AudioEndpoint, AudioHop, OneIPDeviceSettings, OneIPPowerSaveSchedule, OneIPPtpMessages, OsdSyncContent, OsdSyncReport, OsdSyncRequest, ThirdPartyVendor, MeshOperationMessage, MeshConfig, MeshReplaceable, MeshReplaceUnit, MeshSetting, MeshBay, MeshBays, OneIPStreamSources, DeviceTreeEntry, UnitStatus
from ..proto.Constants import MXR_PROTOCOL_VERSION, THIRD_PARTY_PAYLOAD_MAX, DeviceFeature, Endpoints, OsdSyncWhat, MESH_REPLACE_NAME_MAX, MESH_REPLACE_UNITS_MAX, MeshReplaceResult, UNIT_MAX_TEMPERATURES, MESH_BAYS_MAX, ControllerRole, CONTROLLER_PARTS_MAX, OSD_SETTINGS_ASKED, OSD_SYNC_RECORDS_MAX
from ..proto.FrameDiscover import FrameDiscover, constructFrameDiscover
from ..proto.Factory import process_mxr_frame
from ..proto.FrameHello import FrameHello, constructFrameHello
from ..proto.FramePing import FramePing
from ..proto.FrameReboot import FrameReboot
from ..proto.FrameFactoryReset import FrameFactoryReset
from ..proto.FrameThirdParty import FrameThirdParty
from ..proto.FrameMeshOperation import FrameMeshOperation
from ..proto.FrameMeshReplace import FrameMeshReplace, KIND_QUERY, KIND_UNITS, KIND_REQUEST, KIND_RESULT
from ..proto.FrameMeshConfig import (FrameMeshConfig, crc32, encode_bays, encode_settings, FLAG_COPY, KIND_BAYS,
                                     KIND_BAYS_REQUEST, KIND_DUMP, KIND_REQUEST as CONFIG_REQUEST, KIND_SET)
from .Mesh import MeshKeeper
from .Controller import ControllerPull, OwnController
from ..proto.FrameControllerState import FrameControllerState, KIND_DATA as STATE_DATA, KIND_REQUEST as STATE_REQUEST, StateHeader
from ..proto.FrameSetInstaller import FrameSetInstaller
from ..proto.FrameSetupStatus import FrameSetupStatus
from ..proto.FrameV2IPSources import FrameV2IPSources, ONEIP_SOURCE_LIST_MAX
from ..proto.FrameV2IPAudio import FrameV2IPAudio
from ..proto.FrameHello import CLIENT_SERIAL
from ..proto.FrameBase import FrameBase
from ..proto.FrameHeader import FrameHeader
from ..proto.FrameTime import FrameTime
from ..proto.FrameTimeZone import FrameTimeZone
from ..proto.FrameTopology import FrameTopology
from ..proto.FrameUpgradeFPGA import FrameUpgradeFPGA
from ..proto.FrameUnitStatus import FrameUnitStatus, UNIT_STATUS_MESSAGE_LEN
from ..proto.FrameV2IPDetectBays import FrameV2IPDetectBays
from ..proto.FrameV2IPPowerSave import FrameV2IPPowerSave
from ..proto.FrameV2IPPrivacy import FrameV2IPPrivacy
from ..proto.FrameV2IPSettingsAll import FrameV2IPSettingsAll
from ..proto.FrameV2IPOsdSync import FrameV2IPOsdSync
from .OsdSync import LogoServer, OsdSender, OSD_SYNC_ASK_WINDOW, PASS_GAP, osd_content_refusal
from ..proto.Constants import (ONEIP_DEVICE_SETTINGS_REPORTED_ONLY, ONEIP_DSCP_MAX, ONEIP_IR_PROFILE_MAX, ONEIP_PTP_DOMAIN_MAX, ONEIP_SINK_ROTATION_MAX,
                               OneIPPowerSaveLevel, OneIPPtpMode,
                               ONEIP_IR_PROFILE_NOT_SET, OneIPDeviceSetting)
from ..proto.Svd import SvdMap
from ..Uid import MxrDeviceUid
from .State import State

import traceback

from ..const import MX_MCAST_UDP_IP, MX_MCAST_UDP_PORT

_LOGGER = logging.getLogger(__name__)

# The opcodes a device accepts from a sender it has no record of: the
# announcement itself, and the discover asking for one. A unit drops a
# stranger's ping.
_ACCEPT_UNANNOUNCED = (0x00, 0x01)

MCAST_FAULT_GRACE = 60.0
'''How long a peer is heard before it counts towards a multicast fault, in
seconds.'''

_OPCODE_LIMIT = 0x59
'''The first opcode past a unit's table (MX_OP_NB). A frame at or above it has
no valid header to a unit, which drops it before it keeps its sender alive or
proves its path.'''

_THIS_CLIENT = object()
'''This client's place in the device tree, which holds it from the start, before
its uid is known.'''

_HELLO_BROADCAST = 30.0
'''Longest a unit leaves its hello off the broadcast endpoint, in seconds.'''

_DUPLICATE_WINDOW = 0.1
'''How long a datagram identical to one already received counts as its second
copy, in seconds. Short, because a key press carries nothing that tells two
presses apart.'''

_DUPLICATE_RING = 64
'''How many recent datagrams the duplicate check compares against.'''

def _for_every_unit(opcode:int, payload:bytes) -> bool:
    '''Whether a unit sends this frame to both endpoints whatever its peers
    need: a discover, reboot or factory reset of every unit - an empty payload,
    or the single byte 0xFF - the monitoring pulse, the bay detection and the
    video processor upgrade. One naming a unit goes as any other frame.

    The hello is not among them: it reaches the broadcast endpoint on a clock
    of its own.'''
    if (opcode == 0x01):    # SYS_DISCOVER
        return (len(payload) == 0)
    if opcode in (0x28, 0x3A):    # SYS_REBOOT, SYS_FACTORY_RESET
        return payload in (b'', b'\xff')
    return opcode in (0x21, 0x2B, 0x2C)    # V2IP_DETECT_BAYS, SYS_MONITORING_PULSE, V2IP_UPGRADE_FPGA

_BROKEN_PROTOCOL = 2
'''The header protocol a broken revision of one layout was stamped with, which
a unit drops.'''

# How long a discover to every device stands in for asking any one of them, in
# seconds. Each device answers it with everything it holds, after a jitter of up
# to a few seconds, so asking one again inside this window repeats an answer
# already on its way.
_DISCOVER_COVERS = 60

# How often a device that still owes part of its description is asked again,
# and how many times. Every unit resends everything every five minutes, so
# giving up costs at most that wait, where asking on would cost every unit a
# full resend each time.
_REASK_INTERVAL = 60
_REASK_TRIES = 3

# What this client had heard of a device before a frame from it: whether it had
# gone offline, and its reboot toggle as last announced.
_Heard = tuple[bool, bool]

def _heard(device:DeviceBase) -> _Heard:
    features = device.features
    return (not device.online,
            (features is not None) and (DeviceFeature.BOOT_BIT in features))

def _missed_state(before:_Heard|None, device:DeviceBase) -> bool:
    '''Whether a device just heard may hold state this client never received.

    A device repeats a frame only for a short while after it changes, so
    whatever it sent before this client first heard it, or while it was out of
    earshot, may not come again. before is None for a device this frame
    registered.

    Not asked: a device whose reboot toggle flipped, or that is about to reboot,
    because a booting device sends everything it holds; and a management client,
    which holds nothing to send.
    '''
    features = device.features
    if (features is None) or (DeviceFeature.MANAGER in features) \
            or (DeviceFeature.STATUS_REBOOTING in features):
        return False
    if (before is None):
        return True
    away, boot_bit = before
    return away and (boot_bit == (DeviceFeature.BOOT_BIT in features))

class Remote(DeviceRegistry, ConnectionCallbacks):
    ''' Main component that handles the network connections and registration of remote devices '''

    def __init__(self, target_ip:str|None=None, port:int|None=None, http_session:aiohttp.ClientSession|None=None, open_connection:bool=True, callbacks:MxrCallbacks|None=None, name:str="MXR Python", local_ip:str|None=None, broadcast:bool|None=None, addr_filter:str|None=None, uid_path:str|None=None, logo_port:int|None=None, serial:str=CLIENT_SERIAL, version:str|None=None, mesh_device:bool=False, dedicated_controller:bool=False, osd_sync:bool=False) -> None:
        '''Initialise the remote controller.

        :param target_ip: for tests and development only: replaces both
            endpoints with one on this address, so a test runs on a scratch
            address rather than a live network. Leave it unset to run both
            endpoints a unit has.
        :param port: the port of the one endpoint target_ip opens, 8812 when
            unset. Ignored without target_ip.
        :param http_session: shared aiohttp session for API calls, or None to create one
        :param open_connection: open the UDP connection immediately when True
        :param callbacks: event callbacks for device state changes
        :param name: human-readable name advertised on the network
        :param local_ip: local interface IP to bind to, or None for any
        :param broadcast: deprecated and ignored: both endpoints always run
        :param addr_filter: only log frames from this IP address when set
        :param uid_path: file holding this client's uid, or None for ~/.mxr-uid.
            Give concurrent clients on one host separate paths - see _load_uid
        :param logo_port: TCP port to serve overlay sync logo images on, or None
            for a free one
        :param serial: serial number advertised on the network, at most 15
            bytes
        :param version: firmware version advertised on the network, at most 15
            bytes, or None for this library's version
        :param mesh_device: announce this client as a mesh device rather than a
            management application. A mesh takes a mesh device as a member and
            can hand it its controller role; units then take writes from it only
            while they follow it as their controller. Units count a mesh device
            without bays as a member only when its serial is P9SN00000000 or
            does not start P9SN0000.
        :param dedicated_controller: announce this client as a dedicated mesh
            controller, one without bays of its own such as a router: right
            after its hello to every unit, at most every 10 s, and at once when
            set_controller_role() changes it, it sends a CONTROLLER_STATE
            (0x58) hello, in a mesh or not. Its hello stays at the 54 bytes
            every unit takes. A OneIP unit at protocol 0x34 or later knows it as
            a dedicated controller once it has had one, and then takes the
            controller role from none while one it follows is online.
        :param osd_sync: take overlay syncs (0x53) as a unit does: the hello
            announces DeviceFeature.OSD_SYNC, for which a source sends this
            client a sync of its own, as to any unit that takes one. Without
            MANAGER next to it, as with mesh_device, that marks a unit copying
            overlays, not a manager answering requests for them.
            request_osd_sync() and request_osd_settings() ask for a sync and for
            its settings; the sync arrives at MxrCallbacks.on_osd_sync(), each
            setting at on_osd_sync_setting(). Fetching the logos is the
            caller's, from OsdSync.logo_url().
        '''
        DeviceRegistry.__init__(self)
        ConnectionCallbacks.__init__(self)
        if (broadcast is not None):
            warnings.warn("Remote(broadcast=...) is deprecated and ignored: both endpoints a unit has always run",
                          DeprecationWarning, stacklevel=2)
        self._name = name
        self._serial = serial
        self._version = version if (version is not None) else __version__
        self._mesh_device = mesh_device
        self._dedicated_controller = dedicated_controller
        self._osd_sync = osd_sync
        self._osd_sync_asked:float|None = None
        self._osd_settings_asked:deque[tuple[MxrDeviceUid, int]] = deque(maxlen=OSD_SETTINGS_ASKED)
        self._own_controller = OwnController()
        self._controller_pulls:list[ControllerPull] = []
        self._controller_allowed:MxrDeviceUid|None = None
        self._mesh_controller:MxrDeviceUid|None = None
        self._mesh_bays_mapped = False
        self._closing = False
        self._own_session = (http_session is None)
        self._callbacks = State(callbacks, http_session)
        self.remotes:dict[MxrDeviceUid,Device] = {}
        self._tree = DeviceTree(_THIS_CLIENT)
        self._links = BayLinks(self)
        self._hello_due = 0.0
        self._probe_failures = 0
        self._tasks:set[asyncio.Task[None]] = set()
        self._uid:bytes|None = None
        self._uid_path = uid_path
        self._local_ip = local_ip
        self._target_ip = target_ip
        self._port = port
        self._discover_timeout = 0
        # Per device still owing part of its description: how often it was
        # asked again, and when last.
        self._reasked:dict[MxrDeviceUid, tuple[int, float]] = {}
        self._state_request:MxrDeviceUid|None = None
        self._addr_filter = addr_filter
        self._svd = SvdMap()
        self._osd = OsdSender()
        self._mesh = MeshKeeper()
        self._osd_queued = asyncio.Event()
        self._logos = LogoServer()
        self._logo_port = logo_port
        # Whether some peer has to be reached by broadcast as well, whether this
        # client's own multicast fails, and when a hello last went to the
        # broadcast endpoint, None since the sockets opened.
        self._broadcast_needed = False
        self._multicast_fault = False
        self._endpoints_opened:float|None = None
        self._hello_on_broadcast:float|None = None
        # The digest and arrival time of each recent datagram.
        self._recent:deque[tuple[int, float]] = deque()
        if open_connection:
            self.conn:ConnectionAsync|None = ConnectionAsync(callbacks=self, local_ip=self._local_ip,
                                                             target_ip=self._target_ip, port=self._port)
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
        '''The address of the one endpoint a test setup named, else the
        multicast group, which is one of the two endpoints that run.'''
        return self._target_ip if (self._target_ip is not None) else MX_MCAST_UDP_IP

    @property
    def local_ip(self) -> str|None:
        return self._local_ip

    @property
    def broadcast(self) -> bool:
        '''Deprecated: always False. Both endpoints a unit has always run.'''
        warnings.warn("Remote.broadcast is deprecated: both endpoints a unit has always run",
                      DeprecationWarning, stacklevel=2)
        return False

    @property
    def port(self) -> int:
        return self._port if ((self._target_ip is not None) and (self._port is not None)) else MX_MCAST_UDP_PORT

    @property
    def paths_known(self) -> bool:
        '''Whether frames are told apart by the endpoint they arrived by, which
        only a client running both endpoints can do.'''
        return (self.conn is not None) and self.conn.is_dual

    @property
    def multicast_fault(self) -> bool:
        '''Whether this client's own multicast fails: a peer, not about to
        reboot, is heard by broadcast but not by multicast. The hello announces
        it as DeviceFeature.STATUS_MCAST_FAULT.'''
        return self._multicast_fault

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
    def serial(self) -> str:
        '''The serial number this client advertises.'''
        return self._serial

    @property
    def version(self) -> str:
        '''The firmware version this client advertises.'''
        return self._version

    @property
    def mesh_device(self) -> bool:
        '''Whether this client announces itself as a mesh device rather than a
        management application.'''
        return self._mesh_device

    @property
    def mesh_controller(self) -> MxrDeviceUid|None:
        '''The mesh controller this client announces it follows, None for none.'''
        return self._mesh_controller

    def set_mesh_controller(self, controller:MxrDeviceUid|None) -> None:
        '''Set the mesh controller this client announces it follows: None for
        none, and its own uid while it is the controller.

        The hello then announces mesh membership while there is one, and the
        mesh controller role while it is this client and set_mesh_bays_mapped()
        says it has bays. Only the announcement changes: membership reports, and
        the units that follow this client, are the caller's to keep in step. A
        change is announced at once rather than at the next scheduled hello.
        '''
        if (controller is not None):
            controller = MxrDeviceUid(controller)
            if controller.empty:
                controller = None
        if (controller == self._mesh_controller):
            return
        self._mesh_controller = controller
        self.tx_hello()

    @property
    def mesh_bays_mapped(self) -> bool:
        '''Whether the caller has mesh bays mapped, as set_mesh_bays_mapped()
        last said.'''
        return self._mesh_bays_mapped

    def set_mesh_bays_mapped(self, mapped:bool) -> None:
        '''Set whether the caller has mesh bays mapped: the inputs and outputs of
        the units in its mesh, which a controller keeps.

        A unit announces the mesh controller role only while it is its own
        controller and has bays mapped, so a freshly promoted controller with
        none does not, and neither does this client until this is set. A change
        to what the hello announces goes out at once.'''
        before = self.features
        self._mesh_bays_mapped = mapped
        if (self.features != before):
            self.tx_hello()

    @property
    def features(self) -> DeviceFeature:
        '''The features this client announces in its hello as of now, which is
        what a peer lists it with.'''
        return FrameHello.announced_features(self)

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
        '''Update runtime configuration, reconnecting if network parameters changed.

        broadcast is deprecated and ignored: both endpoints a unit has always run.'''
        if (broadcast is not None):
            warnings.warn("update_config(broadcast=...) is deprecated and ignored: both endpoints a unit has always run",
                          DeprecationWarning, stacklevel=2)
        if (callbacks is not None):
            self._callbacks = State(callbacks, self.http_session)
        if (name is not None):
            self._name = name
        if (target_ip is not None) or (port is not None) or (local_ip is not None):
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
            if changed:
                if (self.conn is not None):
                    _LOGGER.debug(f"closing connection")
                    self.conn.close()
                _LOGGER.debug(f"opening new mx_remote listener on {self._local_ip}")
                self.conn = ConnectionAsync(callbacks=self, local_ip=self._local_ip, target_ip=self._target_ip, port=self._port)
                # The first hello on new sockets goes to both endpoints.
                self._hello_on_broadcast = None
                self._own_controller.sent = None
                self._endpoints_opened = time.time()
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
        '''One pass of the probe loop: announce if due, ask a device again for
        what it still owes, and discover every device while none has answered.

        A discover to every device costs every unit a full resend, so it goes
        out at most once a minute, and only until a device answers: every unit
        heard that discover, and one still owing something is asked by name.'''
        fault_changed = self._judge_paths(time.time())
        if fault_changed or (time.time() >= self._hello_due):
            self.tx_hello()
        # Every registered device, whatever any of them has finished. A device
        # stops pinging whether or not it ever described itself, and this is the
        # only thing that notices: nothing arrives to mark a device gone, so a
        # pass skipped is a device that stays online in the registry for as long
        # as the client runs.
        for uid, device in self.remotes.items():
            device.check_online()
            if device.check_configuration_complete_timeout():
                if device.configuration_complete:
                    self._reasked.pop(uid, None)
            elif device.online:
                self._reask(uid)
        self._check_controller_pulls(time.time())
        self._forget_silent()
        if (len(self.remotes) == 0) and ((time.time() - self._discover_timeout) >= _DISCOVER_COVERS):
            self.tx_discover()

    def _reask(self, device:MxrDeviceUid) -> None:
        '''Ask a device again for its state, at most once a minute and
        _REASK_TRIES times until it has described itself.'''
        tries, last = self._reasked.get(device, (0, 0.0))
        if (tries >= _REASK_TRIES) or ((time.time() - last) < _REASK_INTERVAL):
            return
        if self._request_state(device):
            self._reasked[device] = (tries + 1, time.time())

    async def start_async(self) -> None:
        '''Start the server that listens for mx_remote frames from other devices.'''
        if (self.conn is None):
            raise Exception("connection not open")
        await self._load_uid()
        # The first hello on new sockets goes to both endpoints.
        self._hello_on_broadcast = None
        self._own_controller.sent = None
        self._endpoints_opened = time.time()
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
        for loop in (self._background_probe(), self._osd_loop()):
            task = asyncio.create_task(loop)
            self._tasks.add(task)
            task.add_done_callback(self._on_task_done)

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
        self._osd.drop()
        await self._logos.stop()
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
        uid = remote_id if isinstance(remote_id, MxrDeviceUid) else MxrDeviceUid(remote_id)
        if ((dev := self.remotes.get(uid)) is not None):
            return dev
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
            if not dev.is_oneip or dev.oneip_sources is None or dev.first_input is None:
                continue
            if not audio and (dev.first_input.oneip_source is not None) and (dev.first_input.oneip_source.video.ip == ip):
                return dev.first_input
            if audio and (dev.first_input.oneip_source is not None) and (dev.first_input.oneip_source.audio.ip == ip):
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

    @override
    def audio_route(self, sink:MxrDeviceUid, sink_endpoint:int, source:MxrDeviceUid,
                    source_endpoint:int) -> list[AudioHop]|None:
        '''The audio route from a source endpoint to a sink endpoint, hop by
        hop from the source, None when there is none.

        It is the route every unit finds for the request, from the two devices'
        endpoint tables alone, so the units a route is sent to all switch the
        same hops. It never passes through a third device; AudioRoute.audio_path
        says how it is searched.'''
        endpoints = {uid: eps for uid in (sink, source)
                     if ((dev := self.get_by_uid(uid)) is not None) and ((eps := dev.audio_endpoints) is not None)}
        return audio_path(endpoints, (sink, sink_endpoint), (source, source_endpoint))

    @override
    async def select_audio_endpoint_input(self, sink:MxrDeviceUid, sink_endpoint:int, source:MxrDeviceUid,
                                          source_endpoint:int) -> bool:
        '''Route a source endpoint to a sink endpoint, on one device or
        through several.

        The route is the one audio_route() finds. Each device owning the
        endpoint fed by one of its hops is sent the whole request, from the
        sink's end of the route, and switches its own hops. Refused, sending
        nothing, when there is no route. Once a device's frame is away, its
        audio_endpoints read its hops routed, and its reports are ignored for
        500 ms, as after every audio command.

        A unit on released firmware up to 4.4.2 routes only between its own
        endpoints, so a route reaching it from another unit is refused.'''
        hops = self.audio_route(sink, sink_endpoint, source, source_endpoint)
        if (hops is None):
            _LOGGER.warning(f"not routing audio endpoint {source}:{source_endpoint} to {sink}:{sink_endpoint}: "
                            "no reported route leads from the source to the sink")
            return False
        units:list[Device] = []
        for hop in reversed(hops):
            if all((unit.remote_id != hop.sink_device) for unit in units):
                if not isinstance((unit := self.get_by_uid(hop.sink_device)), Device):
                    return False
                units.append(unit)
        # Every unit's frame is built before the first goes out, so a route
        # one of them refuses sends nothing.
        frames:list[tuple[Device, bytes]] = []
        for unit in units:
            frame = FrameV2IPAudio.construct_select_input(mxr=self, sink=sink, sink_ep=sink_endpoint, source=source,
                                                          source_ep=source_endpoint, legacy=unit.audio_legacy,
                                                          addressee=unit.remote_id)
            if (frame is None):
                _LOGGER.warning(f"not routing audio endpoint {source}:{source_endpoint} to {sink}:{sink_endpoint}: "
                                f"{unit} routes only its own audio endpoints")
                return False
            frames.append((unit, frame.frame))
        for unit, data in frames:
            if (self.transmit(data, to=unit) != len(data)):
                return False
            unit.audio_commanded()
            for hop in hops:
                if (hop.sink_device == unit.remote_id) and (hop.source_device == unit.remote_id):
                    unit.hold_audio_route(sink=hop.sink, source=hop.source)
        return True

    @property
    def links(self) -> BayLinks:
        return self._links

    @override
    def transmit(self, data: bytes, to:DeviceBase|None=None) -> int:
        '''Transmit a frame over the UDP connection. Returns bytes sent.

        It leaves by the endpoints a unit picks: by the one to is heard by when
        it is for that device alone, to both when it is for every unit at once,
        and otherwise to the group, and to the broadcast address as well while
        some peer needs it. The hello goes to both at least every 30 s.'''
        if (self.conn is None):
            raise Exception("connection closed")
        return self.conn.transmit(data, self._endpoints_for(data, to, time.time()))

    def _endpoints_for(self, data:bytes, to:DeviceBase|None, now:float) -> Endpoints:
        '''The endpoints a frame leaves by, as a unit picks them.'''
        if isinstance(to, Device):
            return to.heard_path(now)
        opcode = int.from_bytes(data[20:22], 'little')
        if (opcode == 0x00):    # SYS_HELLO
            if (self._hello_on_broadcast is None) or ((now - self._hello_on_broadcast) >= _HELLO_BROADCAST) \
                    or self._broadcast_needed:
                self._hello_on_broadcast = now
                return Endpoints.BOTH
            return Endpoints.MULTICAST
        if self._broadcast_needed or _for_every_unit(opcode, data[24:]):
            return Endpoints.BOTH
        return Endpoints.MULTICAST

    def _is_duplicate(self, data:bytes, now:float) -> bool:
        '''Whether data repeats a datagram received within _DUPLICATE_WINDOW of
        now, recording it when it does not. A frame sent to both endpoints
        arrives once by each, and the first copy is the one acted on.'''
        digest = hash(data)
        while self._recent and ((now - self._recent[0][1]) >= _DUPLICATE_WINDOW):
            self._recent.popleft()
        if any(d == digest for d, _ in self._recent):
            return True
        if (len(self._recent) == _DUPLICATE_RING):
            self._recent.popleft()
        self._recent.append((digest, now))
        return False

    def _judge_paths(self, now:float) -> bool:
        '''Re-judge whether frames must reach some peer by broadcast too, and
        whether this client's own multicast fails, returning whether the second
        changed: a unit announces a change to its features at once. A peer
        counts towards the fault only after MCAST_FAULT_GRACE, from when it was
        first heard and, for every peer, from when this client opened its
        endpoints: a peer's broadcast copies can arrive before its first
        multicast frame, or before the switch forwards the group to this
        client.

        Every registered peer counts, one gone silent included, as a unit
        judges by every peer it knows. A client on one endpoint judges nothing,
        as it has no second one to fall back on.'''
        if (self.conn is None) or not self.conn.is_dual:
            return False
        peers = [d for d in self.remotes.values() if (d.remote_id != self.uid)]
        def flagged(d:Device, flag:DeviceFeature) -> bool:
            return (d.features is not None) and (flag in d.features)
        self._broadcast_needed = any(d.broadcast_only(now) or flagged(d, DeviceFeature.STATUS_MCAST_FAULT)
                                     for d in peers)
        def settled(d:Device) -> bool:
            since = d.first_heard if (self._endpoints_opened is None) else max(self._endpoints_opened, d.first_heard)
            return (now - since) >= MCAST_FAULT_GRACE
        fault = any(settled(d) and not flagged(d, DeviceFeature.STATUS_REBOOTING) and d.broadcast_only(now)
                    and d.heard_broadcast_lately(now) for d in peers)
        changed = (fault != self._multicast_fault)
        self._multicast_fault = fault
        return changed

    def tx_discover(self) -> int:
        '''Transmit a discover frame. All remotes will respond with a hello frame.'''
        pkt = constructFrameDiscover(self)
        if (pkt is None):
            return 0
        self._discover_timeout = time.time()
        _LOGGER.debug("discovering devices")
        return self.transmit(pkt.frame)

    def _request_state(self, device:MxrDeviceUid) -> bool:
        '''Ask one device for everything it holds, with a discover naming it.
        True when it was asked.

        Skipped while a discover to every device is recent enough to have
        covered it. A receiver that predates the named form answers it as a
        discover to every device, so each one asked costs the whole mesh's state
        on such a network.
        '''
        if ((time.time() - self._discover_timeout) < _DISCOVER_COVERS):
            return False
        pkt = FrameDiscover.construct(mxr=self, target=device)
        if (pkt is None):
            return False
        _LOGGER.debug(f"asking {self.uid_to_user_string(device)} for its state")
        self.transmit(pkt.frame)
        return True

    async def reboot_all(self) -> bool:
        '''Ask every unit to reboot, as a unit's own reboot of every unit does
        before it reboots itself: 0x28 with the single byte 0xFF, to both
        endpoints. True when all of it was written.

        A unit takes it only from its mesh controller or a management
        application.'''
        return self._send_to_all(FrameReboot.construct_all(mxr=self))

    async def reboot_mesh(self) -> bool:
        '''Ask every unit of the mesh to reboot, as a mesh controller's mesh
        reboot does before it reboots itself: 0x28 with no payload, to both
        endpoints. Otherwise as reboot_all().'''
        return self._send_to_all(FrameReboot.construct_all(mxr=self, mesh=True))

    async def factory_reset_all(self) -> bool:
        '''Ask every unit to factory-reset and reboot, as a unit's own factory
        reset of every unit does before it resets itself: 0x3A with the single
        byte 0xFF, to both endpoints. Otherwise as reboot_all().'''
        return self._send_to_all(FrameFactoryReset.construct_all(mxr=self))

    async def send_oneip_detect_bays(self) -> bool:
        '''Ask every unit to detect its bays, as a mesh controller's detect
        does: 0x21 with no payload, to both endpoints. True when all of it was
        written.

        Current firmware takes the frame and does nothing with it; it still
        counts as traffic from this client.'''
        return self._send_to_all(FrameV2IPDetectBays.construct(mxr=self))

    async def request_all_oneip_power_save(self, suspend:bool) -> bool:
        '''Ask every OneIP unit to enter power save, or to leave it: 0x41 with
        the flag alone, as a mesh controller sends it without a target. True
        when all of it was written.

        A unit takes it only from its mesh controller or a management
        application, and one that cannot power down ignores it.
        DeviceBase.request_oneip_power_save() asks one unit.'''
        return self._send_to_all(FrameV2IPPowerSave.construct_all(mxr=self, suspend=suspend))

    async def upgrade_all_video_processors(self) -> bool:
        '''Have every unit flash the latest video processor image it holds, as a
        mesh controller's upgrade does: 0x2C with no payload, to both endpoints.
        True when all of it was written.

        A unit takes it only from management, and flashes only when its running
        image differs: the frame carries no force.
        DeviceBase.upgrade_unit_video_processor() forces one unit.'''
        return self._send_to_all(FrameUpgradeFPGA.construct(mxr=self))

    async def send_unit_status(self, status:UnitStatus) -> bool:
        '''Report this client's own health and IP configuration to every
        device, as a unit does in its periodic broadcast and when they change.
        True when all of it was written.

        A mesh controller that runs no update checks of its own passes its
        members' upgrade flags on this way: a member acts on
        UnitFlag.FIRMWARE_UPGRADE and UnitFlag.VIDEO_PROCESSOR_UPGRADE gained in its
        controller's report by checking for the upgrade itself.

        Refused before anything is sent for more than UNIT_MAX_TEMPERATURES
        temperatures, and for a status message over 48 bytes or holding a
        NUL.'''
        if (len(status.temperatures) > UNIT_MAX_TEMPERATURES):
            _LOGGER.warning(f"not sending unit status: a unit reports at most {UNIT_MAX_TEMPERATURES} temperatures")
            return False
        message = status.status_message.encode('utf-8')
        if (len(message) > UNIT_STATUS_MESSAGE_LEN) or (b'\0' in message):
            _LOGGER.warning(f"not sending unit status: a status message is at most {UNIT_STATUS_MESSAGE_LEN} bytes, with no NUL")
            return False
        return self._send_to_all(FrameUnitStatus.construct(mxr=self, status=status))

    def _send_to_all(self, frame:FrameBase|None) -> bool:
        '''Send a frame to every device, True when all of it was written.'''
        if (frame is None):
            return False
        return (self.transmit(frame.frame) == len(frame.frame))

    async def set_all_oneip_device_settings(self, settings:OneIPDeviceSettings) -> bool:
        '''Change settings on every OneIP device of the mesh with one frame.

        settings carries the settings behind their bits in valid, as a device
        reports them. Each device applies those it has and ignores the rest,
        and none below protocol 0x2A applies any. A setting only a device
        reports about itself, a profile, PTP mode, PTP domain or power save
        level out of range, a PTP DSCP above ONEIP_DSCP_MAX, a stream TTL outside
        1 to 255, a rotation above ONEIP_SINK_ROTATION_MAX and a power save time
        that is not a time of day are refused here, since every device would
        ignore them. Each device takes a rotation only by its own step.

        Nothing is cached: each device that applies a change reports its
        settings, and its oneip_settings reads that.
        '''
        valid = settings.valid
        why = None
        if (int(valid) == 0):
            why = 'no setting is carried'
        elif (valid & ONEIP_DEVICE_SETTINGS_REPORTED_ONLY):
            why = 'a setting only a device reports is carried'
        elif (OneIPDeviceSetting.IR_PROFILE in valid) and not (0 <= (settings.ir_profile or 0) < ONEIP_IR_PROFILE_MAX):
            why = 'no such infrared profile'
        elif (OneIPDeviceSetting.IR_PROFILE_SINK in valid) \
                and not (ONEIP_IR_PROFILE_NOT_SET <= (settings.ir_profile_sink or 0) < ONEIP_IR_PROFILE_MAX):
            why = 'no such output infrared profile'
        elif (OneIPDeviceSetting.AUTO_POWER_SAVE in valid) and not (0 <= (settings.auto_power_save or 0) <= 0xFFFF):
            why = 'more idle minutes than the field holds'
        elif (OneIPDeviceSetting.POWER_SAVE_SCHEDULE in valid) \
                and not (settings.power_save_schedule or OneIPPowerSaveSchedule()).is_valid():
            why = 'a power save time is not a time of day'
        elif (OneIPDeviceSetting.PTP_MODE in valid) \
                and not (OneIPPtpMode.OFF <= (settings.ptp_mode or 0) <= OneIPPtpMode.AUTO):
            why = 'no such PTP mode'
        elif (OneIPDeviceSetting.PTP_DOMAIN in valid) \
                and not (0 <= (settings.ptp_domain or 0) <= ONEIP_PTP_DOMAIN_MAX):
            why = 'no such PTP domain'
        elif (OneIPDeviceSetting.PTP_PRIORITY1 in valid) and not (0 <= (settings.ptp_priority1 or 0) <= 0xFF):
            why = 'a PTP priority1 the field cannot hold'
        elif (OneIPDeviceSetting.POWER_SAVE_LEVEL in valid) \
                and not (OneIPPowerSaveLevel.NONE <= (settings.power_save_level or 0) <= OneIPPowerSaveLevel.OFF):
            why = 'no such power save level'
        elif (OneIPDeviceSetting.PTP_DSCP in valid) \
                and not (0 <= (settings.ptp_messages or OneIPPtpMessages()).dscp <= ONEIP_DSCP_MAX):
            why = 'a PTP DSCP above 63'
        elif (OneIPDeviceSetting.STREAM_TTL in valid) \
                and not (1 <= (settings.ptp_messages or OneIPPtpMessages()).stream_ttl <= 0xFF):
            why = 'a stream TTL outside 1 to 255'
        elif (OneIPDeviceSetting.SINK_ROTATION in valid) \
                and not (0 <= (settings.ptp_messages or OneIPPtpMessages()).sink_rotation <= ONEIP_SINK_ROTATION_MAX):
            why = f'a rotation above {ONEIP_SINK_ROTATION_MAX} degrees'
        if (why is not None):
            _LOGGER.warning(f"not changing the settings of every OneIP device: {why}")
            return False
        return self._send_to_all(FrameV2IPSettingsAll.construct(mxr=self, settings=settings))

    async def set_all_oneip_power_save(self, enabled:bool) -> bool:
        '''Switch power save on or off on every OneIP device of the mesh with
        one frame, written as Device.set_oneip_power_save() writes it.
        Otherwise as set_all_oneip_device_settings().'''
        return await self.set_all_oneip_device_settings(OneIPDeviceSettings.power_save_switch(enabled))

    async def request_all_oneip_privacy(self) -> bool:
        '''Ask every OneIP source unit of the mesh how its streams are
        encrypted, as Device.request_oneip_privacy() asks one. A unit below
        protocol 0x30 ignores it.'''
        return self._send_to_all(FrameV2IPPrivacy.construct_request(mxr=self, target=None, target_uid=None))

    async def send_third_party(self, vendor:ThirdPartyVendor, payload:bytes) -> bool:
        '''Send an application's own message to every device, under vendor.
        True when all of it was written.

        Every other client of this library that has heard this one announce
        itself receives it at MxrCallbacks.on_third_party_message(); this client
        does not, and neither does one sharing its uid. No unit is meant to read
        it. Nothing acknowledges it, so an application that needs to know it
        arrived has to have its peers answer.

        A payload over THIRD_PARTY_PAYLOAD_MAX bytes is refused.'''
        if (len(payload) > THIRD_PARTY_PAYLOAD_MAX):
            _LOGGER.warning(f"not sending a third-party message: {len(payload)} bytes, "
                            f"the most is {THIRD_PARTY_PAYLOAD_MAX}")
            return False
        return self._send_to_all(FrameThirdParty.construct(mxr=self, vendor=vendor, payload=payload))

    async def send_mesh_operation(self, operation:MeshOperationMessage) -> bool:
        '''Send a mesh operation to every device. True when all of it was
        written.

        A unit takes the operations that change a mesh from its controller or a
        management application. Nothing acknowledges them: a unit that took one
        reports the mesh controller it follows from then on, which mesh_master
        reads.'''
        return self._send_to_all(FrameMeshOperation.construct_message(mxr=self, message=operation))

    async def send_oneip_source_list(self, sources:list[OneIPStreamSources]) -> bool:
        '''Send the mesh's whole list of OneIP sources, as the mesh controller
        does. True when every frame was written.

        Each entry names a source unit by its uid and its video, audio and
        ancillary stream addresses. A unit named in the list, hearing it from
        the controller it follows, registers every unit listed and unregisters
        every source unit that is not, so the list must always be complete. A
        unit takes it from a sender that announces itself as the mesh master;
        see set_mesh_controller().

        A list longer than one frame goes out in pages that each say where they
        start and how long the whole list is. Refused for an entry without a
        uid, and for a list longer than ONEIP_SOURCE_LIST_MAX entries, which the
        pages cannot number.'''
        if any(source.uid is None for source in sources):
            _LOGGER.warning("not sending the OneIP source list: an entry names no source uid")
            return False
        if ((frames := FrameV2IPSources.construct(mxr=self, sources=sources)) is None):
            _LOGGER.warning(f"not sending the OneIP source list: {len(sources)} entries, "
                            f"the most is {ONEIP_SOURCE_LIST_MAX}")
            return False
        return all(self._send_to_all(frame) for frame in frames)

    # ---- replacing a unit of a mesh (0x56) ----

    async def query_mesh_replaceable(self) -> bool:
        '''Ask every device which units this client can replace. True when the
        query was written, or was not due.

        Every controller answers with its offline units, and every member whose
        controller is offline with that controller; mesh_replaceable then reads
        them. A unit lists none until its controller has been up 120 s, and a
        device without the mesh module answers nothing. A call within 2 s of
        the last sends nothing, as a unit asks no more often: the answers to
        the last are still arriving.'''
        if not self._mesh.query_due(time.time()):
            return True
        return self._send_to_all(FrameMeshReplace.construct_query(mxr=self))

    @property
    def mesh_replaceable(self) -> list[MeshReplaceable]:
        '''The units this client can ask to replace, each with the device that
        listed it, as listed in the last 30 s. A unit several members list
        appears once.'''
        return self._mesh.replaceable(time.time())

    async def request_mesh_replace(self, lister:DeviceBase, unit:MxrDeviceUid) -> bool:
        '''Ask lister to replace unit with this client: the device takes over
        the unit's bays, their names and routes, and its kept settings. True
        when the request was written; the device answers at
        MxrCallbacks.on_mesh_replace_answered().

        Asking a member to replace its offline controller makes it send the
        controller's kept settings to this client, at
        MxrCallbacks.on_mesh_config_received(). Taking over is then this
        client's own: promoting itself to controller in place of the old one,
        and having the members replace it (send_mesh_operation()).

        Refused here for what the device would refuse: lister has not listed
        unit in the last 30 s, this client follows a mesh controller, its
        serial is a default one, or it lacks a ONEIP_SOURCE, ONEIP_SINK or
        MULTIVIEWER feature unit has.'''
        listed = self._mesh.listed(lister.remote_id, unit, time.time())
        needed = DeviceFeature.ONEIP_SOURCE | DeviceFeature.ONEIP_SINK | DeviceFeature.MULTIVIEWER
        why = None
        if (self._mesh_controller is not None):
            why = 'a unit in a mesh replaces no other'
        elif self._serial.startswith('P9SN0000') and (self._serial != CLIENT_SERIAL):
            why = 'a unit on a default serial replaces no other'
        elif (listed is None):
            why = 'the device has not listed it in the last 30 s'
        elif (DeviceFeature(int(listed.features)) & needed) & ~FrameHello.announced_features(self):
            why = 'this client lacks a feature of the unit'
        if (why is not None):
            _LOGGER.warning(f"not asking {lister} to replace {unit}: {why}")
            return False
        frame = FrameMeshReplace.construct_target(mxr=self, kind=KIND_REQUEST, unit=unit, to=lister)
        if (frame is None) or (self.transmit(frame.frame, to=lister) != len(frame.frame)):
            return False
        self._mesh.pending = (lister.remote_id, unit)
        return True

    async def send_mesh_replaceable(self, to:DeviceBase, offline_controller:bool,
                                    units:list[MeshReplaceUnit]|tuple[MeshReplaceUnit, ...]) -> bool:
        '''Answer a unit's query with the units this client, as controller, can
        have replaced, or with its offline controller, as a member. True when
        every frame was written.

        A controller lists a unit while it has bays on the controller, is not
        the controller, and is offline. An empty list is sent all the same, so
        the unit knows this client has none. Refused for more than
        MESH_REPLACE_UNITS_MAX units, and for a bay name over
        MESH_REPLACE_NAME_MAX bytes.'''
        why = None
        if (len(units) > MESH_REPLACE_UNITS_MAX):
            why = f'a controller lists at most {MESH_REPLACE_UNITS_MAX} units'
        elif any(len(name.encode('utf-8')) > MESH_REPLACE_NAME_MAX
                 for u in units for name in (u.input_name, u.output_name)):
            why = f"a replaceable unit's bay name is at most {MESH_REPLACE_NAME_MAX} bytes"
        if (why is not None):
            _LOGGER.warning(f"not listing replaceable units to {to}: {why}")
            return False
        frames = FrameMeshReplace.construct_units(mxr=self, units=units, offline_controller=offline_controller, to=to)
        return bool(frames) and all(self.transmit(f.frame, to=to) == len(f.frame) for f in frames)

    async def send_mesh_replace_result(self, to:DeviceBase, unit:MxrDeviceUid, result:MeshReplaceResult|int) -> bool:
        '''Answer to's request to replace unit with it. True when it was
        written.'''
        frame = FrameMeshReplace.construct_target(mxr=self, kind=KIND_RESULT, unit=unit, result=result, to=to)
        return (frame is not None) and (self.transmit(frame.frame, to=to) == len(frame.frame))

    # ---- the settings a mesh keeps of its units (0x57) ----

    def mesh_config(self, subject:MxrDeviceUid) -> MeshConfig|None:
        '''The kept settings of subject, as a device last sent them whole to
        this client, None until one has. Ask for them with
        request_mesh_config(); a unit's announced length and crc32 are its
        mesh_config_digest.'''
        return self._mesh.configs.get(subject)

    async def request_mesh_config(self, holder:DeviceBase, subject:MxrDeviceUid) -> bool:
        '''Ask holder for the kept settings of subject: its own when subject is
        holder, otherwise the copy it keeps. A controller keeps one of every
        member, and a member one of its controller. True when the request was
        written; they arrive at MxrCallbacks.on_mesh_config_received(), and
        mesh_config() reads them. A device keeping no copy answers nothing.'''
        frame = FrameMeshConfig.construct_request(mxr=self, subject=subject, to=holder)
        return (frame is not None) and (self.transmit(frame.frame, to=holder) == len(frame.frame))

    def _encoded_settings(self, settings:list[MeshSetting]|tuple[MeshSetting, ...], what:str) -> bytes|None:
        '''Settings to send, None after a warning for what no unit takes.'''
        if ((encoded := encode_settings(settings)) is None):
            _LOGGER.warning(f"not sending {what}: kept settings are names and values of at most 255 bytes, "
                            f"with no NUL, of at most 1984 bytes together")
        return encoded

    async def send_mesh_config_hello(self, settings:list[MeshSetting]|tuple[MeshSetting, ...]) -> bool:
        '''Announce the length and crc32 of this client's own kept settings to
        every device. True when it was written.

        A unit announces its own every 60 s while it is in a mesh, and 2 s after
        one of them changes. Its controller, or a member whose controller this
        client is, then asks for them when they differ from its copy. Refused
        while this client follows no mesh controller, as a unit in no mesh
        announces none, and for settings no unit takes.'''
        if (self._mesh_controller is None):
            _LOGGER.warning("not announcing kept settings: a unit in no mesh announces none")
            return False
        if ((encoded := self._encoded_settings(settings, 'a kept settings hello')) is None):
            return False
        return self._send_to_all(FrameMeshConfig.construct_hello(mxr=self, own=self.uid, encoded=encoded))

    async def send_mesh_config(self, to:DeviceBase, subject:MxrDeviceUid,
                               settings:list[MeshSetting]|tuple[MeshSetting, ...]) -> bool:
        '''Send to the kept settings of subject, as the answer to its request:
        this client's own when subject is this client, otherwise the copy it
        keeps. True when every frame was written. Refused for settings no unit
        takes.'''
        if ((encoded := self._encoded_settings(settings, f'kept settings to {to}')) is None):
            return False
        flags = 0 if (subject == self.uid) else FLAG_COPY
        frames = FrameMeshConfig.construct_pages(mxr=self, kind=KIND_DUMP, flags=flags, subject=subject,
                                                 encoded=encoded, to=to)
        return bool(frames) and all(self.transmit(f.frame, to=to) == len(f.frame) for f in frames)

    async def send_mesh_config_set(self, member:DeviceBase, settings:list[MeshSetting]|tuple[MeshSetting, ...]) -> bool:
        '''Have a member of the mesh this client controls take settings as its
        kept settings: it sets every one named, resets every other kept one to
        its default, and answers with the settings it then has. A member whose
        settings changed restarts 3 s later. True when every frame was written.

        Refused unless the member has reported this client as its controller,
        the one sender a unit takes them from, and for settings no unit
        takes.'''
        master = member.mesh_master_uid
        if (master is None) or (master != self.uid):
            why = "the member has not reported its controller" if (master is None) \
                else 'a unit takes kept settings only from its controller'
            _LOGGER.warning(f"not setting the kept settings of {member}: {why}")
            return False
        if ((encoded := self._encoded_settings(settings, f'kept settings to {member}')) is None):
            return False
        frames = FrameMeshConfig.construct_pages(mxr=self, kind=KIND_SET, flags=0, subject=member.remote_id,
                                                 encoded=encoded, to=member)
        return bool(frames) and all(self.transmit(f.frame, to=member) == len(f.frame) for f in frames)

    # ---- a controller's numbering (0x57) ----

    def mesh_bays(self, subject:MxrDeviceUid) -> MeshBays|None:
        '''The numbering of controller subject, as a device last sent it whole,
        None until one has.'''
        return self._mesh.bays.get(subject)

    async def request_mesh_bays(self, holder:DeviceBase, subject:MxrDeviceUid) -> bool:
        '''Ask holder for the numbering of controller subject: which unit owns
        each of its bays, so a device taking over from it numbers them the
        same. A controller answers for itself with its own; a member with the
        copy it keeps of its controller's, also once that controller is
        offline. True when the request was written; it arrives at
        MxrCallbacks.on_mesh_bays_received(), and mesh_bays() reads it. A
        device keeping none, or whose mesh module predates the request,
        answers nothing.'''
        frame = FrameMeshConfig.construct_bays_request(mxr=self, subject=subject, to=holder)
        return (frame is not None) and (self.transmit(frame.frame, to=holder) == len(frame.frame))

    async def send_mesh_bays(self, to:DeviceBase, subject:MxrDeviceUid,
                             bays:list[MeshBay]|tuple[MeshBay, ...]) -> bool:
        '''Send to the numbering of controller subject, as the answer to its
        request: this client's own when subject is this client, otherwise the
        copy it keeps. True when every frame was written. Refused for more than
        MESH_BAYS_MAX bays.'''
        if (len(bays) > MESH_BAYS_MAX):
            _LOGGER.warning(f"not sending a numbering to {to}: it holds at most {MESH_BAYS_MAX} bays")
            return False
        flags = 0 if (subject == self.uid) else FLAG_COPY
        frames = FrameMeshConfig.construct_pages(mxr=self, kind=KIND_BAYS, flags=flags, subject=subject,
                                                 encoded=encode_bays(bays), to=to)
        return bool(frames) and all(self.transmit(f.frame, to=to) == len(f.frame) for f in frames)

    async def set_mesh_setup_completed(self, completed:bool) -> bool:
        '''Mark the setup of every unit that hears it completed, or not.

        A unit takes it only from its mesh controller or a management
        application, and shows it in its next announcement.'''
        return self._send_to_all(FrameSetupStatus.construct(mxr=self, completed=completed))

    async def set_mesh_installer(self, installer:int) -> bool:
        '''Set the installer id of every unit that hears it, 16 bits.

        A unit takes it only from its mesh controller or a management
        application. A controller also carries the id in its controller report,
        which MeshOperationMessage.report_controller() builds.'''
        if not (0 <= installer <= 0xFFFF):
            _LOGGER.warning(f"not setting installer id {installer}: it must fit 16 bits")
            return False
        return self._send_to_all(FrameSetInstaller.construct(mxr=self, installer=installer))

    async def set_mesh_time_zone(self, zone:str, rule:str) -> bool:
        '''Set the time zone of every device that hears it.

        zone is an IANA name such as Europe/Amsterdam and rule the POSIX TZ rule
        the devices keep time by, such as CET-1CEST,M3.5.0,M10.5.0/3. A device
        applies the rule and shows the name. Neither may be empty, hold a NUL,
        or be longer than its field on the wire leaves room for;
        clear_mesh_time_zone() sends both empty.

        The mesh controller takes it too, and announces it from then on with
        every periodic broadcast. A device takes it only from a management
        application or the controller, and this client announces itself as a
        management application.
        '''
        frame = FrameTimeZone.construct(mxr=self, zone=zone, rule=rule)
        if (frame is None):
            _LOGGER.warning(f"not setting time zone {zone!r} {rule!r}: empty, holding a NUL, or too long")
            return False
        return self._send_to_all(frame)

    async def clear_mesh_time_zone(self) -> bool:
        '''Clear the time zone of every device that hears it, which then keeps
        UTC. Sent, received and announced as set_mesh_time_zone() with an empty
        name and rule.'''
        return self._send_to_all(FrameTimeZone.construct_clear(mxr=self))

    async def set_mesh_time(self, when:datetime|None=None) -> bool:
        '''Set the clock of every device that hears it to when, or to now.

        A device keeps its own clock where that is within 2s of when. It takes
        the time only from a management application or the controller; see
        set_mesh_time_zone(). A time before 1970 or past 2106, which 32 bits of
        seconds do not hold, is refused.
        '''
        frame = FrameTime.construct(mxr=self, when=(when if (when is not None) else datetime.now(timezone.utc)))
        if (frame is None):
            _LOGGER.warning(f"not setting the mesh time to {when}: it does not fit the frame")
            return False
        return self._send_to_all(frame)

    def _arm_hello(self) -> None:
        '''Schedule the next announcement, mirroring the firmware's hello timer.

        MatrixOS re-draws min 2.5s + random(0..2.5s) after each hello it sends,
        so a mesh of devices does not synchronise into bursts. The interval is
        re-drawn per send rather than fixed for the same reason.

        MatrixOS stretches that to 20-30s once every device it knows is on 0x2A.
        This client keeps the short interval: a peer below 0x2A takes it offline
        15s after its last hello.
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
            # again, which is what firmware does - it re-arms its own timer only
            # after a send succeeds. Arming here on failure instead
            # would silence a client for a full interval every time a write failed,
            # and on an interface that never writes, permanently.
            self._arm_hello()
            self._announce_controller(time.time(), False)
        return sent

    def _announce_controller(self, now:float, now_due:bool) -> None:
        '''A dedicated controller's CONTROLLER_STATE hello, which follows its
        hello to every unit at most every 10 s, and goes at once when
        now_due.'''
        if not self._dedicated_controller:
            return
        if not now_due and not self._own_controller.due(now):
            return
        self._own_controller.sent = now
        self._send_to_all(FrameControllerState.construct_hello(mxr=self, hello=self._own_controller.hello()))

    def set_controller_role(self, role:ControllerRole|int, primary:MxrDeviceUid|None=None) -> bool:
        '''Set the role and the primary this client's CONTROLLER_STATE hello
        carries as a dedicated controller, and send it at once when they
        changed. It starts as ControllerRole.NONE with no primary. Refused,
        returning False, unless this client was made with
        dedicated_controller.'''
        if not self._dedicated_controller:
            _LOGGER.warning("not setting the controller role: only a dedicated controller sends a controller hello")
            return False
        own = self._own_controller
        if (own.role != role) or (own.primary != primary):
            own.role, own.primary = role, primary
            self._announce_controller(time.time(), True)
        return True

    def set_controller_parts(self, generation:int, parts:list[tuple[int, bytes]]) -> bool:
        '''Set the parts of this client's state, as a dedicated controller:
        each part number with its bytes. The hello then lists each part's
        length and crc32 under generation, and goes at once when either
        changed. A request from another dedicated controller of this client's
        mesh, or the one allow_controller_state() names, is answered from them,
        for this generation only. It starts with no parts and generation 0.

        Refused, returning False, unless this client was made with
        dedicated_controller, and for more than CONTROLLER_PARTS_MAX parts, a
        part listed twice, or a part number outside 0 to 255.'''
        if not self._dedicated_controller:
            _LOGGER.warning("not setting the controller parts: only a dedicated controller serves them")
            return False
        numbers = [part for part, _ in parts]
        if (len(parts) > CONTROLLER_PARTS_MAX) or (len(set(numbers)) != len(numbers)) \
                or any(not (0 <= part <= 0xFF) for part in numbers):
            _LOGGER.warning(f"not setting the controller parts: at most {CONTROLLER_PARTS_MAX}, "
                            f"each numbered 0 to 255 once")
            return False
        held = [(part, bytes(data), crc32(bytes(data))) for part, data in parts]
        own = self._own_controller
        if (own.generation != generation) or (own.parts != held):
            own.generation, own.parts = generation, held
            self._announce_controller(time.time(), True)
        return True

    def allow_controller_state(self, uid:MxrDeviceUid|None) -> None:
        '''Also take CONTROLLER_STATE requests and data from uid, a dedicated
        controller of no mesh of this client's: one this client is replacing a
        router of its mesh with. None takes them only from this client's mesh
        again.'''
        self._controller_allowed = uid

    def _takes_controller_state(self, dev:DeviceBase) -> bool:
        '''Whether a CONTROLLER_STATE request or data is taken from dev: a
        dedicated controller, one that sent a hello, of this client's own mesh,
        so one whose controller is this client's controller or which is that
        controller; or the one allow_controller_state() named.'''
        if (dev.controller_hello is None):
            return False
        if (self._controller_allowed == dev.remote_id):
            return True
        controller = self._mesh_controller
        return (controller is not None) and ((dev.remote_id == controller) or (dev.mesh_master_uid == controller))

    async def pull_controller_part(self, device:DeviceBase, part:int, generation:int, length:int, crc:int) -> bool:
        '''Pull part of device's state generation, which its hello lists with
        length and crc, in place of a pull of the same part under way. It asks
        for windows of up to 8192 bytes, each from the first byte it does not
        have, and again from there when no data arrives for 2 s. The part
        arrives at MxrCallbacks.on_controller_part_received() once whole and
        its crc32 matches, or the pull ends at on_controller_part_failed():
        for a generation no longer held, a part other than the one asked, the
        device going offline, or ten asks without progress. Pulls of other
        parts, or of other devices, run alongside.

        Data is taken only from a dedicated controller of this client's mesh,
        or the one allow_controller_state() names. Refused, returning False,
        for a device that is offline; True once the first request was
        written.'''
        if not device.online:
            _LOGGER.warning(f"not pulling part {part} of {device}: it is offline")
            return False
        self._controller_pulls = [p for p in self._controller_pulls
                                  if not ((p.device.remote_id == device.remote_id) and (p.part == part))]
        if (length == 0):
            if (crc == crc32(b'')):
                self.callbacks.on_controller_part_received(device, part, generation, b'')
            else:
                self.callbacks.on_controller_part_failed(device, part, generation)
            return True
        pull = ControllerPull(device, part, generation, length, crc, time.time())
        self._controller_pulls.append(pull)
        return self._ask_controller(device, pull.ask(time.time()))

    def _ask_controller(self, device:DeviceBase, header:StateHeader, data:bytes=b'') -> bool:
        '''Send a request, or data, to one dedicated controller.'''
        frame = FrameControllerState.construct(mxr=self, header=header, data=data, to=device)
        return (frame is not None) and (self.transmit(frame.frame, to=device) == len(frame.frame))

    def _on_controller_state(self, frame:FrameControllerState) -> None:
        '''Answer a request from the parts this client holds, and take data
        into the pull of its part, each only from a sender
        _takes_controller_state() takes.'''
        if ((dev := self.remotes.get(frame.remote_id)) is None) or ((header := frame.state_header) is None) \
                or not self._takes_controller_state(dev):
            return
        if (header.kind == STATE_REQUEST):
            if self._dedicated_controller:
                for answer, data in self._own_controller.answer(header):
                    self._ask_controller(dev, answer, data)
            return
        pull = next((p for p in self._controller_pulls
                     if (p.device.remote_id == dev.remote_id) and (p.part == header.part)), None)
        if (pull is None):
            return
        asks:list[StateHeader] = []
        done = pull.take(header, frame.data, time.time(), asks)
        for ask in asks:
            self._ask_controller(dev, ask)
        if (done is not None):
            self._end_controller_pull(pull, done)

    def _end_controller_pull(self, pull:ControllerPull, received:bool) -> None:
        self._controller_pulls.remove(pull)
        if received:
            self.callbacks.on_controller_part_received(pull.device, pull.part, pull.generation, bytes(pull.data))
        else:
            self.callbacks.on_controller_part_failed(pull.device, pull.part, pull.generation)

    def _check_controller_pulls(self, now:float) -> None:
        '''Ask again for a pull that has waited 2 s for data, and give up on one
        whose device went offline, or after ten asks without progress.'''
        for pull in list(self._controller_pulls):
            asks:list[StateHeader] = []
            done = False if not pull.device.online else pull.retry(now, asks)
            for ask in asks:
                self._ask_controller(pull.device, ask)
            if (done is not None):
                self._end_controller_pull(pull, done)

    def on_connection_made(self) -> None:
        '''Callback invoked after ConnectionAsync has started the server.'''
        self.tx_hello()
        self.tx_discover()

    def process_frame(self, timestamp:float, data: bytes, addr: tuple[str, int], path:Endpoints|None=None) -> None:
        '''Decode and process a received mx_remote frame.

        A device that may hold state this client missed is left in
        _state_request rather than asked here, so replaying a capture sends
        nothing; on_datagram_received does the asking.

        path is the endpoint it arrived by, when two are open. A known sender
        is then recorded as heard by that path, which is what decides whether
        frames must reach it by broadcast too. A frame from a known sender that
        is still alive keeps it so, whatever it carries; once it has gone silent
        long enough to count as offline, only a hello brings it back. Both
        happen before the duplicate check, so the copy that loses the race still
        proves its path, and neither for an opcode past a unit's table. A
        datagram repeating one received within _DUPLICATE_WINDOW is dropped.'''
        proc = False
        self._state_request = None
        try:
            frame = process_mxr_frame(mxr=self, timestamp=timestamp, data=data, addr=addr)
            # An opcode this library decodes nothing of still has a header,
            # which is what a unit keeps its sender alive by.
            header:FrameHeader|None = frame.header if (frame is not None) else FrameHeader(self, data, addr)
            if (header is not None) and (header.protocol > MXR_PROTOCOL_VERSION):
                # The stamp is the version at which this opcode's payload last
                # changed, not the sender's version. Above ours means this
                # opcode's layout is newer than we know: the frames we would
                # decode into wrong state, and the ones devices drop before
                # dispatch.
                #
                # A release raises the stamp only where a layout moved, so this
                # silences those opcodes until the library is bumped, not the
                # mesh.
                _LOGGER.debug(f"rx {addr[0]}: opcode {header.opcode:02X} needs protocol "
                              f"{header.protocol:02X}, this build knows {MXR_PROTOCOL_VERSION:02X}")
                frame = header = None
            if (header is not None) and ((len(data) != 24 + header.payload_len)
                                         or (header.protocol == _BROKEN_PROTOCOL)):
                # A unit drops a datagram whose length is not the header's
                # exactly, and a frame stamped with the version a broken
                # revision once stamped.
                _LOGGER.debug(f"rx {addr[0]}: opcode {header.opcode:02X} dropped: {len(data)} bytes "
                              f"declaring {header.payload_len}, stamped {header.protocol:02X}")
                frame = header = None
            if (header is not None) and (header.remote_id != self.uid):
                # An opcode past a unit's table is no valid header to it, so it
                # touches neither.
                known = self.remotes.get(header.remote_id)
                if (known is not None) and (header.opcode < _OPCODE_LIMIT):
                    if (path is not None):
                        known.heard_on(path, timestamp)
                    known.keep_alive()
                if (path is not None) and self._is_duplicate(data, timestamp):
                    frame = None
            if (frame is not None) and (frame.header.remote_id != self.uid):
                # A device announces itself before it sends anything else, so a
                # frame from a uid with no record is one no device would act on.
                # Decode and report it - this library is also used to watch the
                # bus - but keep it out of the cache and the callbacks.
                #
                # Hello and discover are exempt: the hello is what makes a
                # sender known, so gating it leaves it unknown forever, and a
                # discover is how a stranger asks to be told. A unit drops a
                # stranger's ping.
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
                known = self.remotes.get(frame.remote_id)
                before = None if (known is None) else _heard(known)
                frame.process()
                device = self.remotes.get(frame.remote_id)
                if (device is not None) and _missed_state(before, device):
                    self._state_request = frame.remote_id
        except Exception:
            _LOGGER.warning(f"failed to process frame: {traceback.format_exc()}")
            raise

    @override
    def on_datagram_received(self, data: bytes, addr: tuple[str, int], path:Endpoints|None=None) -> None:
        '''Called when a UDP frame was received, by path when two endpoints are
        open.'''
        timestamp = time.time()
        self.process_frame(timestamp=timestamp, data=data, addr=addr, path=path)
        if (self._state_request is not None):
            self._request_state(self._state_request)
        if self._judge_paths(timestamp):
            self.tx_hello()

    # ---- overlay sync ----

    @property
    def osd_sync_held(self) -> bool:
        '''Whether this client holds an overlay sync, and so announces itself as
        the mesh's overlay sync manager.'''
        return self._osd.holds

    async def send_osd_sync(self, content:OsdSyncContent) -> int|None:
        '''Have every unit copy content, and keep it in place, returning the
        sync's number, or None when it was refused or did not go out.

        Units take a sync from the mesh controller or a management application,
        which this client announces itself as. Each unit fetches the images
        from a server this client runs, then asks for the settings, which this
        client answers until the content is replaced or clear_osd_sync(). Meanwhile
        it announces itself as the mesh's overlay sync manager, so a unit waking
        from power save takes this content too, rather than the controller's.
        The controller can still send its own over it; the last sync a unit
        took is what it shows. Each unit's osd_sync_report says how it went.

        Refused for content a unit would refuse: copying nothing, more than
        OSD_SYNC_RECORDS_MAX settings, a caption font over OSD_SYNC_FONT_MAX or
        text over OSD_SYNC_TEXT_MAX bytes, a logo other than -1 to 4, or an image
        that is not a PNG within OSD_SYNC_IMAGE_MAX bytes and
        OSD_SYNC_IMAGE_WIDTH_MAX by OSD_SYNC_IMAGE_HEIGHT_MAX pixels, shown at
        over OSD_SYNC_PERCENT_MAX percent. Refused content leaves the held sync as
        it was; content that fails to go out leaves none held.
        '''
        if not await self._store_osd_sync(content, 'sending'):
            return None
        seq = self._tx_osd_sync(MxrDeviceUid(bytes(16)), None, None)
        if (seq is None):
            await self.clear_osd_sync()
        return seq

    async def keep_osd_sync(self, content:OsdSyncContent) -> bool:
        '''Keep content in place as send_osd_sync() does, serving its images
        and answering units' requests for its settings, without having any
        unit copy it now: a mesh controller holding the sync its units already
        took from another source, to send a unit that joins with
        resend_osd_sync(). Refused as send_osd_sync() is.'''
        return await self._store_osd_sync(content, 'keeping')

    async def _store_osd_sync(self, content:OsdSyncContent, what:str) -> bool:
        '''Hold content and serve its images, announcing the overlay sync
        manager when none was held. False after a warning for content a unit
        would refuse, which leaves the held sync as it was, and for a logo
        server that did not start, which leaves none held.'''
        if ((why := osd_content_refusal(content)) is not None):
            _LOGGER.warning(f"not {what} an overlay sync: {why}")
            return False
        http_port = 0
        if (content.images is not None):
            try:
                await self._logos.start(self._logo_port or 0)
            except OSError as e:
                _LOGGER.warning(f"not {what} an overlay sync: the logo server did not start: {e}")
                await self.clear_osd_sync()
                return False
            self._logos.images = tuple(image.png for image in content.images)
            http_port = self._logos.port
        was_held = self._osd.holds
        self._osd.hold(content, http_port)
        # Announced first, so the controller has stood back by the time a unit
        # deferring this sync wakes and asks for it.
        if not was_held:
            self.tx_hello()
        return True

    @property
    def takes_osd_sync(self) -> bool:
        '''Whether this client takes overlay syncs as a unit does, as
        Remote(osd_sync=True) says, and so announces DeviceFeature.OSD_SYNC
        always.'''
        return self._osd_sync

    async def request_osd_sync(self, what:OsdSyncWhat) -> bool:
        '''Ask for an overlay sync of this client's own, copying what, as a unit
        does once it can take one: the controller, or a management application
        standing in for it, answers with a sync naming this client, which
        arrives at MxrCallbacks.on_osd_sync() under its sender. For 10 s after,
        a sync naming this client is read from any device, as the one
        answering may be a controller its units no longer follow.

        The request goes to every unit, as a unit's does; only the controller
        acts on it. A controller without a decoder runs no overlays and
        answers nothing. True when it was written.'''
        self._osd_sync_asked = time.time()
        return self._send_to_all(FrameV2IPOsdSync.construct_request(
            mxr=self, target=self.uid, seq=0, what=what, missing=bytes(16), source=MxrDeviceUid(bytes(16))))

    async def request_osd_settings(self, source:DeviceBase, seq:int, what:OsdSyncWhat, missing:list[int]) -> bool:
        '''Ask source for settings missing, each below the sync's records, of
        its sync seq, as a unit taking that sync does. The source answers each
        one with a setting naming this client, which arrives at
        MxrCallbacks.on_osd_sync_setting() under source, and is read for the
        last OSD_SETTINGS_ASKED syncs asked about.

        A source sends at most a few settings at a time and drops nothing it
        was asked for, but a frame can be lost: a unit asks again for those
        still missing a second after the last one came. One whose seq is no
        longer its latest answers with a new sync copying what; a what of none
        asks for nothing new.

        Refused, returning False, for a setting index of OSD_SYNC_RECORDS_MAX
        or more. True when it was written.'''
        bits = bytearray(16)
        for index in missing:
            if not (0 <= index < OSD_SYNC_RECORDS_MAX):
                _LOGGER.warning(f"not asking {source} for overlay settings: an index is below {OSD_SYNC_RECORDS_MAX}")
                return False
            bits[index // 8] |= 1 << (index % 8)
        key = (source.remote_id, seq)
        if (key in self._osd_settings_asked):
            self._osd_settings_asked.remove(key)
        self._osd_settings_asked.append(key)
        frame = FrameV2IPOsdSync.construct_request(mxr=self, target=self.uid, seq=seq, what=what, missing=bytes(bits),
                                                   source=source.remote_id, to=source)
        return (frame is not None) and (self.transmit(frame.frame, to=source) == len(frame.frame))

    async def send_osd_report(self, source:DeviceBase, report:OsdSyncReport) -> bool:
        '''Report to source how this client gets on with taking its sync
        report.seq, as a unit does at each stage: taking, done or failed. The
        source lists it among the units that took the sync. The reason is cut
        to 63 bytes. True when it was written.'''
        frame = FrameV2IPOsdSync.construct_report(mxr=self, target=self.uid, report=report, to=source)
        return (frame is not None) and (self.transmit(frame.frame, to=source) == len(frame.frame))

    @override
    def osd_sync_asked(self, at:float) -> bool:
        return (self._osd_sync_asked is not None) and ((at - self._osd_sync_asked) < OSD_SYNC_ASK_WINDOW)

    @override
    def osd_settings_asked(self, source:MxrDeviceUid, seq:int) -> bool:
        return (source, seq) in self._osd_settings_asked

    async def resend_osd_sync(self, device:DeviceBase) -> int|None:
        '''Have one unit copy the held sync again, returning the new sync's
        number. As send_osd_sync().

        Refused while no sync is held, and for a unit that does not announce
        DeviceFeature.OSD_SYNC, as one that does not take overlay syncs.'''
        if (device.features is None) or (DeviceFeature.OSD_SYNC not in device.features):
            _LOGGER.warning(f"not resending an overlay sync to {device}: it takes none")
            return None
        if not self._osd.holds:
            _LOGGER.warning(f"not resending an overlay sync to {device}: none is held")
            return None
        return self._tx_osd_sync(device.remote_id, None, device)

    async def clear_osd_sync(self) -> None:
        '''Stop holding the sync this client sent, and hand the overlay sync
        manager's part back to the controller. Units keep what they took; one
        still taking it fails, as its requests go unanswered.'''
        await self._logos.stop()
        if self._osd.drop():
            self.tx_hello()

    def _tx_osd_sync(self, target:MxrDeviceUid, what:OsdSyncWhat|None, to:DeviceBase|None) -> int|None:
        '''Number and send a new sync of the held content.'''
        if ((sync := self._osd.new_sync(what)) is None):
            return None
        seq, what, http_port, records, slots = sync
        frame = FrameV2IPOsdSync.construct_sync(mxr=self, target=target, seq=seq, what=what, http_port=http_port,
                                                records=records, slots=slots, to=to)
        if (frame is None) or (self.transmit(frame.frame, to=to) != len(frame.frame)):
            return None
        return seq

    def _answer_osd_request(self, request:OsdSyncRequest) -> None:
        '''Answer a unit's overlay sync request: queue the settings it lacks, or
        send it a new sync of its own.'''
        what = self._osd.answer(request)
        if (self._osd.queued > 0):
            self._osd_queued.set()
        if (what is not None) and ((unit := self.get_by_uid(request.target)) is not None):
            self._tx_osd_sync(request.target, what, unit)

    def _osd_pass(self) -> int:
        '''Send the next few settings units asked for, returning how many.'''
        sent = 0
        for unit, seq, index, records, entry in self._osd.next_pass():
            frame = FrameV2IPOsdSync.construct_setting(mxr=self, target=unit, seq=seq, index=index,
                                                       records=records, entry=entry, to=self.get_by_uid(unit))
            if (frame is not None):
                self.transmit(frame.frame, to=self.get_by_uid(unit))
                sent += 1
        return sent

    async def _osd_loop(self) -> None:
        '''Send settings as units ask for them, until the client is closing.'''
        while not self._closing:
            try:
                if (self._osd_pass() > 0):
                    await asyncio.sleep(PASS_GAP)
                    continue
            except Exception:
                _LOGGER.warning(f"overlay sync pass failed: {traceback.format_exc()}")
            self._osd_queued.clear()
            if (self._osd.queued == 0):
                try:
                    await asyncio.wait_for(self._osd_queued.wait(), timeout=1)
                except asyncio.TimeoutError:
                    pass

    @override
    def on_mxr_update(self, data:Any) -> None:
        if isinstance(data, OsdSyncRequest):
            self._answer_osd_request(data)
        elif isinstance(data, FrameMeshReplace):
            self._on_mesh_replace(data)
        elif isinstance(data, FrameMeshConfig):
            self._on_mesh_config(data)
        elif isinstance(data, FrameControllerState):
            self._on_controller_state(data)
        elif isinstance(data, FrameHello):
            self._on_mxr_hello(data)
        elif isinstance(data, FrameTopology):
            self._on_mxr_topology(data)
        elif isinstance(data, (FramePing, FrameDiscover)):
            # Announcing is driven by a clock, and these are the frames that add
            # a hello to it. A device that pings hears nothing back within about
            # 1.5s before it takes this client offline, and one that discovers
            # drops this client's frames until it has had a hello; the next
            # scheduled one can be seconds away.
            self.tx_hello()

    def _on_mesh_replace(self, frame:FrameMeshReplace) -> None:
        '''Keep a list, and hand a query, request or answer to the callbacks. An
        answer is handed on only when it names the unit of this client's last
        request.'''
        if ((dev := self.remotes.get(frame.remote_id)) is None):
            return
        kind = frame.kind
        if (kind == KIND_QUERY):
            self.callbacks.on_mesh_replace_queried(dev)
        elif (kind == KIND_UNITS):
            self.callbacks.on_mesh_replace_units_received(dev, self._mesh.take_units(dev.remote_id, frame,
                                                                                    frame.timestamp))
        elif (kind == KIND_REQUEST) and (frame.unit is not None):
            self.callbacks.on_mesh_replace_requested(dev, frame.unit)
        elif (kind == KIND_RESULT) and (frame.unit is not None) and (frame.result is not None) \
                and self._mesh.answered(frame.unit):
            self.callbacks.on_mesh_replace_answered(dev, frame.unit, frame.result)

    def _on_mesh_config(self, frame:FrameMeshConfig) -> None:
        '''Hand a request to the callbacks, and put settings together. A dump is
        kept and handed on once whole; a set is handed on only when it names
        this client and comes from the controller this client follows, the one
        sender a unit takes it from.'''
        if ((dev := self.remotes.get(frame.remote_id)) is None) or (frame.subject is None):
            return
        if (frame.kind == CONFIG_REQUEST):
            self.callbacks.on_mesh_config_requested(dev, frame.subject)
        elif (frame.kind == KIND_BAYS_REQUEST):
            self.callbacks.on_mesh_bays_requested(dev, frame.subject)
        elif (frame.kind == KIND_BAYS):
            if ((bays := self._mesh.take_bays(dev.remote_id, frame)) is not None):
                self.callbacks.on_mesh_bays_received(dev, bays)
        elif (frame.kind in (KIND_DUMP, KIND_SET)):
            if ((settings := self._mesh.take_settings(dev.remote_id, frame)) is None):
                return
            if (frame.kind == KIND_DUMP) and ((config := self._mesh.configs.get(frame.subject)) is not None):
                self.callbacks.on_mesh_config_received(dev, config)
            elif (frame.kind == KIND_SET) and (frame.subject == self.uid) \
                    and (dev.remote_id == self._mesh_controller):
                self.callbacks.on_mesh_config_set_requested(dev, settings)

    def _on_mxr_hello(self, hello_frame:FrameHello) -> None:
        '''Hello frame received. Register or update the local device cache.'''
        d = self.get_by_uid(hello_frame.remote_id)
        if d is None:
            d = Device(self, hello_frame)
            self.remotes[hello_frame.remote_id] = d
            self._tree.add(hello_frame.remote_id)
        d.on_mxr_update(hello_frame)

    def _on_mxr_topology(self, frame:FrameTopology) -> None:
        '''Reshape the device tree by a topology list, as a unit does with one
        differing byte for byte from the sender's last.'''
        if ((d := self.remotes.get(frame.remote_id)) is None) or not d.note_topology(frame.payload or b''):
            return
        self._tree.apply_topology(frame.remote_id, [self._tree_key(e.uid) for e in frame.topology])

    def _tree_key(self, uid:MxrDeviceUid) -> object:
        '''The key a device sits under in the tree, which for this client is
        _THIS_CLIENT.'''
        return _THIS_CLIENT if (uid == self.uid) else uid

    @property
    def device_tree(self) -> list[DeviceTreeEntry]:
        '''Every device heard from and this client, as a unit keeps its
        registry: a tree, walked depth first, a parent before its children.

        This client heads the root, and each device joins the end of it when
        first heard. A device another one's topology report lists moves to the
        end of that one's children, unless it is below it already, and back to
        the end of the root once a later report leaves it out. Only a report
        differing byte for byte from that device's last reshapes the tree, and
        only for devices registered by then; a device not registered is skipped.
        A device the sender sits below, the sender itself included, stays where
        it is. A forgotten device's children move to the end of its parent's.'''
        return [DeviceTreeEntry(self.uid if (key is _THIS_CLIENT) else key, depth) # type: ignore[arg-type]
                for key, depth in self._tree.walk()]

    def _forget_silent(self) -> None:
        '''Forget every device silent long enough for a unit to forget it, with
        the links it reported. One heard again registers anew, at the end of
        the root.'''
        for uid in [uid for uid, d in self.remotes.items() if d.forgotten]:
            device = self.remotes.pop(uid)
            self._tree.remove(uid)
            self._links.forget_device(uid)
            self._reasked.pop(uid, None)
            self.callbacks.on_device_unregistered(device)

# The V2IP spelling of a Remote method, from before the rename to OneIP.
from ..deprecated import alias_members as _alias_members
_alias_members(Remote, 'set_all_v2ip_device_settings')
