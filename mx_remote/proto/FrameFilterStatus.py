##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Protocol frame for bay source filter status.'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Uid import MxrDeviceUid
from ..Interface import FilteredDevices

class FrameFilterStatus(FrameBase):
    '''Bay filter status listing which source devices are filtered out.'''
    @cached_property
    def filtered(self) -> FilteredDevices:
        '''Set of filtered (hidden) source devices.'''
        if (self.payload is None):
            return FilteredDevices()
        return FilteredDevices(self.payload[16:])

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        '''UID of the target device.'''
        return self.payload_uuid(0)

    def process(self) -> None:
        '''Update the local device cache with the source filter list.'''
        if ((dev := self.remote_device) is None):
            return
        if ((first_output := dev.first_output) is None):
            return
        first_output.on_mxr_update(self.filtered)

    def __str__(self) -> str:
        return f"bay filter status: {len(self.filtered)} sources filtered"
