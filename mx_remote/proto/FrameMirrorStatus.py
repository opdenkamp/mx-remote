######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for OneIP mirroring status between devices.'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import DeviceBase, BayMirrorStatus
from ..Uid import MxrDeviceUid, MxrBayUid

_MIRROR_SIZE = 32
'''The sink, then the sink it mirrors; a unit takes no other length.'''

_NO_MIRROR = MxrDeviceUid(bytes([0xFF] * 16))

class FrameMirrorStatus(FrameBase):
    '''Which sink a sink mirrors: a unit's report on its own sink, or management
    setting it. The sink is named in the first 16 bytes.'''
    @cached_property
    def target(self) -> MxrDeviceUid|None:
        '''UID of the mirroring target device.'''
        return self.payload_uuid(0)

    @cached_property
    def target_bay(self) -> BayMirrorStatus:
        '''Mirror status for the sender's first output bay.

        Wraps the master UID (offset 16, the device the sink follows). Empty
        when the sink mirrors nothing: a master of all zero or all 0xFF, or the
        sink itself.
        '''
        if (self.master is not None) and not self.master.empty \
                and (self.master != _NO_MIRROR) and (self.master != self.target):
            return BayMirrorStatus(MxrBayUid(self.master, 0))
        return BayMirrorStatus()

    @cached_property
    def is_own(self) -> bool:
        '''Whether the target is the device that sent this frame.'''
        return ((dev := self.remote_device) is not None) \
            and (dev.remote_id == self.target)

    @cached_property
    def master(self) -> MxrDeviceUid|None:
        '''UID of the mirror master device.'''
        return self.payload_uuid(16)

    @cached_property
    def master_dev(self) -> DeviceBase|None:
        '''Mirror master device instance.'''
        return self.mxr.get_by_uid(self.master)

    def process(self) -> None:
        '''File the mirroring status under the sink the frame names.'''
        if (len(self.payload or b'') != _MIRROR_SIZE):
            return
        if ((dev := self.config_subject(self.target)) is not None) \
                and ((first_out := dev.first_output) is not None):
            first_out.on_mxr_update(self.target_bay)

    def __str__(self) -> str:
        return f"{self.remote_device} mirroring status: {self.master_dev}"
