##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Protocol frame for device advertisement (hello/discovery response).'''

from functools import cached_property
import warnings
from ..const import __version__
from .Constants import MXR_PROTOCOL_VERSION, DeviceFeature
from .FrameBase import FrameBase, append_payload_str
from ..Interface import DeviceRegistry
import struct
from typing import Any

class FrameHello(FrameBase):
    '''Hello frame, sent by devices to advertise themselves on the network.'''
    @staticmethod
    def construct(mxr:DeviceRegistry) -> FrameBase|None:
        '''Build a hello frame for transmission to advertise this client.'''
        payload = [ (MXR_PROTOCOL_VERSION & 0xFF), ((MXR_PROTOCOL_VERSION >> 8) & 0xFF) ]
        payload = append_payload_str(payload=payload, value=mxr.name, sz=16)
        payload = append_payload_str(payload=payload, value="P9SN00000000", sz=16)
        payload = append_payload_str(payload=payload, value=__version__, sz=16)
        features = DeviceFeature.MANAGER
        payload += [ (features >> 0) & 0xFF, (features >> 8) & 0xFF, (features >> 16) & 0xFF, (features >> 24) & 0xFF ]
        return FrameBase.construct_base(mxr=mxr, opcode=0, payload=bytes(payload))

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

    @cached_property
    def features(self) -> DeviceFeature|None:
        '''Supported features bitmask.'''
        if (self.payload is None) or (len(self.payload) < 54):
            return None
        return DeviceFeature(struct.unpack('<L', self.payload[50:54])[0])

    def process(self) -> None:
        '''Register or update this device in the local device cache.'''
        self.mxr.on_mxr_update(self)

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, FrameHello) and \
                (self.protocol == other.protocol) and \
                (self.device_name == other.device_name) and \
                (self.serial == other.serial) and \
                (self.version == other.version) and \
                (self.features == other.features)

    def __ne__(self, other: Any) -> bool:
        return not isinstance(other, FrameHello) or \
                (self.protocol != other.protocol) or \
                (self.device_name != other.device_name) or \
                (self.serial != other.serial) or \
                (self.version != other.version) or \
                (self.features != other.features)

    def __str__(self) -> str:
        return f"hello name:{self.device_name} serial:{self.serial} version:{self.version} features/status: {self.features} uid: {self.header.remote_id}"

def constructFrameHello(mxr:DeviceRegistry) -> FrameBase|None:
    warnings.warn("use FrameHello.construct() instead", DeprecationWarning)
    return FrameHello.construct(mxr=mxr)
