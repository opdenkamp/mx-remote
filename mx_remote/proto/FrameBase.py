######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################

'''Base class and utilities for decoded MX Remote protocol frames.'''

from typing import Any
import logging
from functools import cached_property
import time
from .Constants import MXR_OPCODE_VERSIONS, MXR_PROTOCOL_VERSION, DeviceFeature
from .FrameHeader import FrameHeader
from ..Interface import DeviceBase, DeviceRegistry, BayBase
from ..Uid import MxrDeviceUid

_LOGGER = logging.getLogger(__name__)

MANAGEMENT_ONLY_SINCE = 0x2F
'''The protocol from which a unit takes a command for itself, or another unit's,
only from management.'''

def append_payload_str(payload:list[int], value:str, sz:int) -> list[int]:
    '''Append a fixed-size ASCII string to a payload byte list, zero-padded to sz.

    The wire fields are fixed width and carry no terminator of their own, so a
    value that fills the field completely is written without one - truncate to
    the field's own size rather than a constant, or the field overruns into its
    neighbour.'''
    encoded = value.encode('ascii', errors='replace')[0:sz]
    return payload + list(encoded) + [ 0 for _ in range(sz - len(encoded))]

class FrameBase:
    ''' Base class for decoded mx_remote frames '''
    def __init__(self, header:FrameHeader, timestamp:float|None=None) -> None:
        assert(isinstance(header, FrameHeader))
        self.header = header
        self.timestamp = timestamp if (timestamp is not None) else time.time()

    @staticmethod
    def opcode_protocol(opcode:int) -> int:
        '''Header protocol version to stamp on a frame carrying this opcode.

        A receiver drops any frame whose header protocol exceeds its own
        MXR_PROTOCOL_VERSION, so this field means the version the opcode needs,
        not the version this build is. Stamping MXR_PROTOCOL_VERSION instead
        cuts us off from every peer with a lower cap: a ProAmp8 caps at 0x22 and
        would drop our hello.

        Falls back to MXR_PROTOCOL_VERSION only for an opcode absent from the
        table, which means it is newer than the table.'''
        return MXR_OPCODE_VERSIONS.get(opcode, MXR_PROTOCOL_VERSION)

    @staticmethod
    def construct_base(mxr:DeviceRegistry, opcode:int, protocol:int|None=None, payload:bytes=bytes([]), size:int|None=None, target:Any=None) -> 'FrameBase|None':
        '''Construct a new frame for transmission with the given opcode and payload.

        Leave protocol unset unless the payload really does need a newer
        receiver than the opcode itself does; it then defaults to the opcode's
        own minimum from MXR_OPCODE_VERSIONS.

        Pass target for anything addressed at one device, so a frame it cannot
        receive is refused here rather than sent into silence.'''
        if (protocol is None):
            protocol = FrameBase.opcode_protocol(opcode)
        if not FrameBase.target_supports(mxr=mxr, target=target, opcode=opcode):
            return None
        header = FrameHeader.construct(mxr=mxr, opcode=opcode, protocol=protocol)
        if (header is None):
            return None
        rv = FrameBase(header)
        if (size is not None):
            if len(payload) > size:
                payload = payload[:size]
            elif len(payload) < size:
                payload += bytes([0 for _ in range(size - len(payload))])
        rv.payload = payload
        return rv

    @staticmethod
    def target_supports(mxr:DeviceRegistry, target:Any, opcode:int) -> bool:
        '''Whether a frame addressed at target can be received by it.

        Accepts what the constructFrame helpers are given: a device, a bay, a
        uid, or None for a broadcast, which has no single target and is always
        allowed.
        '''
        if (target is None):
            return True
        device = getattr(target, 'device', None) or (target if hasattr(target, 'supports_opcode') else None)
        if (device is None):
            device = mxr.get_by_uid(target) if isinstance(target, (str, bytes, MxrDeviceUid)) else None
        if (device is None) or not hasattr(device, 'supports_opcode'):
            return True
        if device.supports_opcode(opcode):
            return True
        _LOGGER.warning(
            f"not sending opcode {opcode:02X} to {device}: it advertises protocol "
            f"{device.protocol:02X} and the opcode needs {FrameBase.opcode_protocol(opcode):02X}")
        return False

    @property
    def mxr(self) -> DeviceRegistry:
        '''Remote instance.'''
        return self.header.mxr

    @property
    def address(self) -> str:
        '''Address that sent this frame.'''
        (addr, _) = self.header.addr
        return addr

    @property
    def protocol(self) -> int:
        '''Frame protocol version.'''
        return self.header.protocol

    @property
    def device_protocol(self) -> int:
        if ((dev := self.remote_device) is not None):
            return dev.protocol
        return self.protocol

    @property
    def remote_id(self) -> MxrDeviceUid:
        '''Unique id of the device that sent this frame.'''
        return self.header.remote_id

    @cached_property
    def remote_device(self) -> DeviceBase|None:
        '''Device instance for the device that sent this frame.'''
        return self.mxr.get_by_uid(self.remote_id)

    def manages(self, subject:DeviceBase|None) -> bool:
        '''Whether a unit takes a write about subject from this frame's sender,
        as a unit judges it: the sender announces MANAGER, or it is the
        controller the subject follows.

        Which controller that is comes from the mesh membership the subject
        reports. MESH_MASTER plays no part once it has, so a controller of
        another mesh, or one being replaced, is not management. Until it has,
        which is the case for as long as a broadcast period after this client
        starts, the controller's own announcement of MESH_MASTER stands in for
        it.'''
        if ((sender := self.remote_device) is None) or ((features := sender.features) is None):
            return False
        if DeviceFeature.MANAGER in features:
            return True
        master = subject.mesh_master_uid if (subject is not None) else None
        if (master is not None) and not master.empty:
            return (master == self.remote_id)
        return DeviceFeature.MESH_MASTER in features

    def takes_command(self, subject:DeviceBase|None) -> bool:
        '''Whether subject takes a routing, hide, mirror, filter or module
        command from this frame's sender: from management only since
        MANAGEMENT_ONLY_SINCE, and from any sender on firmware before it, which
        every released unit runs.'''
        if self.manages(subject):
            return True
        return (subject is not None) and (subject.protocol < MANAGEMENT_ONLY_SINCE)

    def command_subject(self, subject_uid:MxrDeviceUid|None) -> DeviceBase|None:
        '''The device a command naming subject_uid is about, as config_subject()
        finds it, except that a unit on released firmware takes one from any
        sender, as takes_command() says.'''
        if (subject_uid is None):
            return None
        if (subject_uid == self.remote_id):
            return self.remote_device
        if ((subject := self.mxr.get_by_uid(subject_uid)) is None):
            return None
        return subject if self.takes_command(subject) else None

    def config_subject(self, subject_uid:MxrDeviceUid|None) -> DeviceBase|None:
        '''The device a frame naming subject_uid is about, None when no unit
        would act on it.

        Equal to the sender it is a device describing itself. Different, it is
        a write for the device it names, which a unit takes only from a sender
        it treats as management. Anything else is dropped rather than filed
        against the sender, because a frame the network ignores must not move
        a record here. An unknown subject is dropped too: there is no record to
        move, and inventing one from a third party's description would create a
        device nothing has been heard from.'''
        if (subject_uid is None):
            return None
        if (subject_uid == self.remote_id):
            return self.remote_device
        if ((subject := self.mxr.get_by_uid(subject_uid)) is None):
            return None
        return subject if self.manages(subject) else None

    @property
    def payload(self) -> bytes|None:
        '''Frame payload bytes.'''
        return self.header.payload

    def payload_idx(self, start:int=0, end:int=-1) -> bytes|None:
        '''Return a slice of the payload from start to end.'''
        if (self.payload is None):
            return None
        l = len(self.payload)
        if (start >= l):
            return None
        if (end < start) or (end > l):
            end = l
        return self.payload[start:end]

    def payload_bay(self, device:DeviceBase|None, idx:int, u16:bool=False) -> BayBase|None:
        '''Look up a bay by port number extracted from the payload at idx.'''
        if (device is None):
            return None
        portnum = self.payload_u16(idx=idx) if u16 else self.payload_u8(idx=idx)
        if (portnum is None):
            return None
        return device.get_by_portnum(portnum)

    def payload_device(self, idx:int) -> DeviceBase|None:
        '''Look up a device by UUID extracted from the payload at idx.'''
        if (self.remote_device is None):
            return None
        return self.remote_device.registry.get_by_uid(self.payload_uuid(idx=idx))

    def payload_u8(self, idx:int) -> int|None:
        return self.header.payload_u8(idx=idx)

    def payload_bool(self, idx:int) -> bool|None:
        return self.header.payload_bool(idx=idx)

    def payload_u16(self, idx:int=0) -> int|None:
        return self.header.payload_u16(idx=idx)

    def payload_u32(self, idx:int=0) -> int|None:
        return self.header.payload_u32(idx=idx)

    def payload_str(self, idx:int, length:int=-1) -> str|None:
        return self.header.payload_str(idx=idx, length=length)

    def payload_uuid(self, idx:int=0) -> MxrDeviceUid|None:
        return self.header.payload_uuid(idx=idx)

    def payload_bytes(self, idx:int) -> bytes|None:
        return self.header.payload_bytes(idx=idx)

    @payload.setter
    def payload(self, val:bytes) -> None:
        self.header.payload = val

    @property
    def frame(self) -> bytes:
        return self.header.data

    def process(self) -> None:
        '''Update the local cache with the new data that was received in this frame.'''
        pass

    def uid_to_user_string(self, uid:str|MxrDeviceUid|bytes|None) -> str:
        '''Convert a device UID to a human-readable name via the device registry.'''
        if (uid is None):
            return '<none>'
        if not isinstance(uid, MxrDeviceUid):
            uid = MxrDeviceUid(uid)
        if (self.remote_device is None):
            return str(uid)
        return self.remote_device.registry.uid_to_user_string(uid)

    def __len__(self) -> int:
        '''Number of payload bytes.'''
        return self.header.payload_len

    def __str__(self) -> str:
        return f"generic frame opcode {self.header.opcode:X}"
