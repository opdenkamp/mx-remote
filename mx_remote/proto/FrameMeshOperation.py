######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for mesh network operations (register, unregister, promote, etc.).'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import DeviceRegistry, DeviceBase, MxrDeviceUid
from enum import IntEnum
import logging

_LOGGER = logging.getLogger(__name__)
class MeshOperation(IntEnum):
    '''Mesh network operation types.'''
    REGISTER = 0
    UNREGISTER = 1
    REPLACE = 2
    REGENERATE_ADDRESSES = 3
    REPORT_CONTROLLER = 4
    PROMOTE_CONTROLLER = 5
    REPORT_MEMBERSHIP = 0xFF

    def __str__(self) -> str:
        if self.value == MeshOperation.REGISTER.value:
            return "register"
        if self.value == MeshOperation.UNREGISTER.value:
            return "unregister"
        if self.value == MeshOperation.REPLACE.value:
            return "replace"
        if self.value == MeshOperation.REGENERATE_ADDRESSES.value:
            return "regenerate addresses"
        if self.value == MeshOperation.REPORT_CONTROLLER.value:
            return "report controller"
        if self.value == MeshOperation.PROMOTE_CONTROLLER.value:
            return "promote controller"
        if self.value == MeshOperation.REPORT_MEMBERSHIP.value:
            return "report membership"
        return "unknown"

    def __repr__(self) -> str:
        return str(self)

class FrameMeshOperation(FrameBase):
    ''' Mesh operation '''

    @staticmethod
    def construct(mxr:DeviceRegistry, operation:MeshOperation, target:DeviceBase, option:DeviceBase|None=None) -> FrameBase|None:
        '''Build a mesh operation frame for transmission.'''
        payload = bytes([operation.value, 0, 0, 0]) + target.remote_id.byte_value
        if option is not None:
            payload += option.remote_id.byte_value
        else:
            payload += bytes([0 for _ in range(16)])
        return FrameBase.construct_base(mxr=mxr, opcode=0x3B, payload=payload)

    @cached_property
    def operation(self) -> MeshOperation|None:
        '''Mesh operation type.'''
        pl = self.payload_u8(0)
        if (pl is None):
            return None
        return MeshOperation(pl)

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        '''UID of the target device for the operation.'''
        return self.payload_uuid(4)

    @cached_property
    def parameter(self) -> MxrDeviceUid|None:
        '''Optional parameter UID (e.g. replacement device for REPLACE operation).'''
        return self.payload_uuid(20)

    def process(self) -> None:
        '''Update the local device cache with the mesh operation.'''
        _LOGGER.debug(f"mesh operation {str(self.operation)} by {str(self.remote_device)} target={self.uid_to_user_string(self.target_uid)} param={self.uid_to_user_string(self.parameter)}")
        if ((dev := self.remote_device) is not None):
            dev.on_mxr_update(self)

    def __str__(self) -> str:
        return f"Mesh operation: {str(self.operation)}"
