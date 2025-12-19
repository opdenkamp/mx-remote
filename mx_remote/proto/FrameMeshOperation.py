##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
import warnings
from .FrameBase import FrameBase
from ..Interface import DeviceRegistry, DeviceBase, MxrDeviceUid
from enum import Enum

class MeshOperation(Enum):
    REGISTER = 0
    UNREGISTER = 1
    REPLACE = 2
    REGENERATE_ADDRESSES = 3
    REPORT_MASTER = 4
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
        if self.value == MeshOperation.REPORT_MASTER.value:
            return "report master"
        if self.value == MeshOperation.REPORT_MEMBERSHIP.value:
            return "report membership"
        return "unknown"

class FrameMeshOperation(FrameBase):
    ''' Mesh operation '''

    @staticmethod
    def construct(mxr:DeviceRegistry, operation:MeshOperation, target:DeviceBase, option:DeviceBase|None=None) -> FrameBase|None:
        payload = bytes([operation.value, 0, 0, 0]) + target.remote_id.byte_value
        if option is not None:
            payload += option.remote_id.byte_value
        else:
            payload += bytes([0 for _ in range(16)])
        return FrameBase.construct_base(mxr=mxr, opcode=0x3B, payload=payload)

    @cached_property
    def operation(self) -> MeshOperation|None:
        pl = self.payload_u8(0)
        if (pl is None):
            return None
        return MeshOperation(pl)

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        return self.payload_uuid(4)

    @cached_property
    def parameter(self) -> MxrDeviceUid|None:
        return self.payload_uuid(20)

    def process(self) -> None:
        if ((dev := self.remote_device) is not None):
            dev.on_mxr_update(self)

    def __str__(self) -> str:
        return f"Mesh operation: {str(self.operation)}"
