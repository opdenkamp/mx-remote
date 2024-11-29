##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import DeviceRegistry, DeviceBase, MxrDeviceUid
from enum import Enum

class MeshOperation(Enum):
    REGISTER = 0
    UNREGISTER = 1
    REPLACE = 2
    REGENERATE_ADDRESSES = 3
    PROMOTE_MASTER = 4
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
        if self.value == MeshOperation.PROMOTE_MASTER.value:
            return "promote master"
        if self.value == MeshOperation.REPORT_MEMBERSHIP.value:
            return "report membership"
        return "unknown"

class FrameMeshOperation(FrameBase):
    ''' Mesh operation '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    def construct(mxr:DeviceRegistry, operation:MeshOperation, target:DeviceBase, option:DeviceBase|None) -> FrameBase:
        payload = bytes([operation.value, 0, 0, 0]) + target.remote_id.byte_value
        if option is not None:
            payload += option.remote_id.byte_value
        else:
            payload += bytes([0 for _ in range(16)])
        return FrameBase.construct_frame(mxr=mxr, opcode=0x3B, payload=payload)

    @property
    def operation(self) -> MeshOperation:
        return MeshOperation(self.payload[0])

    @property
    def target_uid(self) -> MxrDeviceUid:
        return MxrDeviceUid(value=self.payload[4:20])

    @property
    def parameter(self) -> MxrDeviceUid:
        return MxrDeviceUid(value=self.payload[20:36])

    def process(self) -> None:
        if (self.operation == MeshOperation.REPORT_MEMBERSHIP):
            self.remote_device.mesh_master = self.target_uid

    def __str__(self) -> str:
        return f"Mesh operation: {str(self.operation)}"
