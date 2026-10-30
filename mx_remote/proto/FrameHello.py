######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for device advertisement (hello/discovery response).'''

from functools import cached_property
import warnings
from ..const import __version__
from .Constants import MXR_PROTOCOL_VERSION, DeviceFeature
from .FrameBase import FrameBase, append_payload_str
from ..Interface import DeviceRegistry
import struct
from typing import Any

HELLO_LEN = 54
'''The shortest hello a unit takes. A shorter one is ignored whole, and a longer
one read by its first this many bytes.'''

CLIENT_SERIAL = "P9SN00000000"
'''The serial this client advertises when the caller sets none.

A client is not a unit with a serial number, but the field is fixed-width and
every device fills it, so it carries a constant rather than a blank.'''

class FrameHello(FrameBase):
    '''Hello frame, sent by devices to advertise themselves on the network.'''
    @staticmethod
    def construct(mxr:DeviceRegistry) -> FrameBase|None:
        '''Build a hello frame for transmission to advertise this client.

        Never append a field to this payload. Receivers read a payload length as
        a minimum everywhere except the hello, which they check exactly, so a
        hello that grew is discarded rather than read up to the part they know.
        That costs more than the field: this is how the client stops being
        unknown, and a receiver that drops it never registers the sender and
        ignores everything that follows as coming from a stranger.

        It holds however many receivers are later fixed to accept a longer
        hello, because the ones already deployed are the ones deciding whether
        this client is seen at all. Nothing on the receive side needs the rule -
        FrameHello reads its fields by offset with no length gate, so a peer may
        grow its own.'''
        payload = [ (MXR_PROTOCOL_VERSION & 0xFF), ((MXR_PROTOCOL_VERSION >> 8) & 0xFF) ]
        payload = append_payload_str(payload=payload, value=mxr.name, sz=16)
        payload = append_payload_str(payload=payload, value=getattr(mxr, 'serial', CLIENT_SERIAL), sz=16)
        payload = append_payload_str(payload=payload, value=getattr(mxr, 'version', __version__), sz=16)
        features = FrameHello.announced_features(mxr)
        payload += [ (features >> 0) & 0xFF, (features >> 8) & 0xFF, (features >> 16) & 0xFF, (features >> 24) & 0xFF ]
        return FrameBase.construct_base(mxr=mxr, opcode=0, payload=bytes(payload))

    @staticmethod
    def announced_features(mxr:DeviceRegistry) -> DeviceFeature:
        '''The features this client's hello announces as of now.'''
        # A unit uses the scaling fields of a 0x3C write only from a sender
        # announcing CONFIG_INITIALISED, and this client zeroes every field it
        # does not set, which is what the bit promises.
        features = DeviceFeature.CONFIG_INITIALISED
        # A mesh takes a sender announcing MESH as a member and can hand it its
        # controller role; MANAGER is what a management application announces.
        features |= DeviceFeature.MESH if getattr(mxr, 'mesh_device', False) else DeviceFeature.MANAGER
        # Membership while it follows a controller, and the controller role
        # while that controller is itself and has bays mapped, as a unit
        # announces it.
        if ((controller := getattr(mxr, 'mesh_controller', None)) is not None):
            features |= DeviceFeature.MESH_MEMBER
            if (controller == mxr.uid) and getattr(mxr, 'mesh_bays_mapped', False):
                features |= DeviceFeature.MESH_MASTER
        # While it holds an overlay sync it also announces itself as the mesh's
        # overlay sync manager, which has the controller leave units' requests
        # for a new sync to it.
        if getattr(mxr, 'osd_sync_held', False):
            features |= DeviceFeature.OSD_SYNC
        # A peer heard by broadcast but not by multicast shows this client's
        # multicast fails, which a unit announces so its peers reach it by
        # broadcast too.
        if getattr(mxr, 'multicast_fault', False):
            features |= DeviceFeature.STATUS_MCAST_FAULT
        return features

    @cached_property
    def supported_protocol(self) -> int|None:
        '''Supported protocol version, which may be higher than this frame's protocol version.'''
        return self.payload_u16(0)

    @cached_property
    def device_name(self) -> str|None:
        '''Device name.'''
        return self.payload_str(2, 16)

    @cached_property
    def serial(self) -> str|None:
        '''Device serial number.'''
        return self.payload_str(18, 16)

    @cached_property
    def version(self) -> str|None:
        '''Firmware version string.'''
        return self.payload_str(34, 16)

    def _raw_field(self, idx:int) -> bytes:
        '''A 16-byte string field as its bytes, cut at the first NUL and
        otherwise untouched: all 16 when the value fills the field.'''
        return (self.payload or b'')[idx:idx+16].split(b'\0', 1)[0]

    @cached_property
    def raw_device_name(self) -> bytes:
        '''The name field as announced, up to its first NUL, never substituted
        or decoded.'''
        return self._raw_field(2)

    @cached_property
    def raw_serial(self) -> bytes:
        '''The serial field as announced, read as raw_device_name is.'''
        return self._raw_field(18)

    @cached_property
    def raw_version(self) -> bytes:
        '''The version field as announced, read as raw_device_name is.'''
        return self._raw_field(34)

    @cached_property
    def features(self) -> DeviceFeature|None:
        '''Supported features bitmask.'''
        if (self.payload is None) or (len(self.payload) < 54):
            return None
        return DeviceFeature(struct.unpack('<L', self.payload[50:54])[0])

    @property
    def whole(self) -> bool:
        '''Whether a unit takes this hello: one shorter than HELLO_LEN is
        ignored whole.'''
        return (len(self.payload or b'') >= HELLO_LEN)

    def process(self) -> None:
        '''Register or update this device in the local device cache.'''
        if self.whole:
            self.mxr.on_mxr_update(self)

    def __eq__(self, other: Any) -> bool:
        # The raw fields tell apart two names whose bytes outside ASCII decode
        # to the same replacement character.
        return isinstance(other, FrameHello) and \
                (self.protocol == other.protocol) and \
                (self.raw_device_name == other.raw_device_name) and \
                (self.raw_serial == other.raw_serial) and \
                (self.raw_version == other.raw_version) and \
                (self.features == other.features)

    def __ne__(self, other: Any) -> bool:
        return not (self == other)

    def __str__(self) -> str:
        return f"hello name:{self.device_name} serial:{self.serial} version:{self.version} features/status: {self.features} uid: {self.header.remote_id}"

def constructFrameHello(mxr:DeviceRegistry) -> FrameBase|None:
    warnings.warn("use FrameHello.construct() instead", DeprecationWarning)
    return FrameHello.construct(mxr=mxr)
