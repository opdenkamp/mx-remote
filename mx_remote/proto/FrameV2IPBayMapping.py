##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Protocol frame for V2IP bay-to-device UID mapping.'''

from functools import cached_property
from typing import override
from ..Interface import MxrDeviceUid
from .FrameBase import FrameBase

class FrameV2IPBayMapping(FrameBase):
    '''V2IP bay mapping associating bay indices with device UIDs.'''
    @cached_property
    def nb_bays(self) -> int:
        '''Number of bay mappings in this frame.'''
        val = self.payload_u16(0)
        if (val is None):
            return 0
        return (val >> 1)

    @cached_property
    def is_input(self) -> bool:
        '''Whether these are input bay mappings.'''
        # Wire format: firmware sets bit 0 to ((mode == MBAY_MODE_INPUT) ? 1 : 0),
        # so an input frame carries bit 0 = 1 (not 0).
        val = self.payload_u16(0)
        if (val is None):
            return False
        return (val & 1 == 1)

    @cached_property
    def is_output(self) -> bool:
        '''Whether these are output bay mappings.'''
        val = self.payload_u16(0)
        if (val is None):
            return False
        return (val & 1 == 0)

    @cached_property
    def first_bay_id(self) -> int|None:
        return self.payload_u16(2)

    @cached_property
    def bays(self) -> list[MxrDeviceUid]:
        '''List of device UIDs mapped to bay indices.'''
        rv = []
        for x in range(self.nb_bays):
            pl = self.payload_uuid(8 + (16 * x))
            if pl is None:
                break
            rv.append(pl)
        return rv

    @cached_property
    def bays_user_string(self) -> list[str]:
        rv = []
        for bay in self.bays:
            rv.append(self.uid_to_user_string(bay))
        return rv

    def bay(self, idx:int) -> MxrDeviceUid|None:
        if idx >= self.nb_bays:
            return None
        return self.payload_uuid(8 + (16 * idx))

    @override
    def process(self) -> None:
        '''Update the local device cache with bay-to-device mapping.'''
        if (self.remote_device is not None):
            self.remote_device.on_mxr_update(self)

    def __str__(self) -> str:
        return f"{str(self.remote_device)} {'input' if self.is_input else 'output'} bay mapping: {self.bays_user_string}"
