##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Protocol frame for V2IP mirroring status between devices.'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import DeviceBase, BayMirrorStatus
from ..Uid import MxrDeviceUid, MxrBayUid

class FrameMirrorStatus(FrameBase):
    '''Mirroring status indicating which device is the mirror master.'''
    @cached_property
    def target(self) -> MxrDeviceUid|None:
        '''UID of the mirroring target device.'''
        return self.payload_uuid(0)

    @cached_property
    def target_bay(self) -> BayMirrorStatus:
        '''Mirror status for the sender's first output bay.

        Wraps the master UID (offset 16, the device the sender follows).
        Empty when the sender is its own master, i.e. not mirroring.
        '''
        if (self.master is not None) and not self.master.empty \
                and (self.master != self.target):
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
        '''Update the local device cache with mirroring status (V2IP only).'''
        if (    (dev := self.remote_device) is not None) \
                and self.is_own \
                and ((first_out:= dev.first_output) is not None):
            first_out.on_mxr_update(self.target_bay)

    def __str__(self) -> str:
        return f"{self.remote_device} mirroring status: {self.master_dev}"
