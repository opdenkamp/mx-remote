######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for mesh network operations (register, unregister, promote, etc.).'''

from functools import cached_property
from .FrameBase import FrameBase
from .Constants import decode_enum
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

# mxr_mesh_operation is ALIGN(8): u8 operation at 0, three bytes of padding to
# the uid alignment, target uid at 4, parameter uid at 20, and four bytes of
# tail padding out to 40.
_WIRE_SIZE = 40

# Two protocol versions do different jobs on this opcode.
#
# _ACCEPT is what a receiver requires before acting on the frame at all. It sits
# below this opcode's entry in MXR_OPCODE_VERSIONS, because that entry was
# raised later, when REPORT_CONTROLLER gained an installer id in the second
# parameter word. Admitting on the table entry would ignore every device
# between the two.
#
# _INSTALLER is that later version. It selects one trailing field rather than a
# layout, which is the only place in this protocol where the stamp picks a
# field.
#
# Sends stamp the table entry, so they reach _INSTALLER and above. No device
# caps between the two, so nothing is lost by that.
_ACCEPT_PROTOCOL = 0x1A
_INSTALLER_PROTOCOL = 0x1D

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
        # 40, not the 36 bytes the fields occupy: mxr_mesh_operation is an
        # 8-aligned struct, so it is 40 bytes wide and the receiver refuses
        # anything shorter than its own sizeof before reading the operation.
        # A frame short by the four trailing pad bytes is dropped in silence.
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x3B, payload=payload, size=_WIRE_SIZE)

    @cached_property
    def acceptable(self) -> bool:
        '''Whether a receiver would act on this frame at all.

        A frame failing either gate is one no device on the mesh acted on, so
        reading an operation out of it invents mesh state rather than tracking
        it. A short payload is the dangerous one: the operation byte can still
        be read from it, and the uid behind it cannot.
        '''
        pl = self.payload
        return (pl is not None) and (len(pl) >= _WIRE_SIZE) \
            and (self.protocol >= _ACCEPT_PROTOCOL)

    @cached_property
    def operation(self) -> MeshOperation|None:
        '''Mesh operation type, or None when no receiver would have acted.'''
        if not self.acceptable:
            return None
        pl = self.payload_u8(0)
        if (pl is None):
            return None
        return decode_enum(MeshOperation, pl)

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
