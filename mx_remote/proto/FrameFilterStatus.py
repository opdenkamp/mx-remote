######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for bay source filter status.'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Uid import MxrDeviceUid
from ..Interface import FilteredDevices

class FrameFilterStatus(FrameBase):
    '''The source devices filtered out of a sink's picker: the sink's uid, then
    the filtered uids. A unit's report on its own sink, or management setting
    a sink's list; a unit takes it only as a whole number of uids.'''
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
        '''File the source filter list under the sink the frame names.'''
        if (len(self.payload or b'') % 16 != 0):
            return
        if ((dev := self.config_subject(self.target_uid)) is None):
            return
        if ((first_output := dev.first_output) is None):
            return
        first_output.on_mxr_update(self.filtered)

    def __str__(self) -> str:
        return f"bay filter status: {len(self.filtered)} sources filtered"
