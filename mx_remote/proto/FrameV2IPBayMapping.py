##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2025 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
from typing import override
from ..Interface import MxrDeviceUid
from .FrameBase import FrameBase

class FrameV2IPBayMapping(FrameBase):
    @cached_property
    def nb_bays(self) -> int:
        val = self.payload_u16(0)
        if (val is None):
            return 0
        return (val >> 1)

    @cached_property
    def is_input(self) -> bool:
        val = self.payload_u16(0)
        if (val is None):
            return False
        return (val & 1 == 0)

    @cached_property
    def is_output(self) -> bool:
        val = self.payload_u16(0)
        if (val is None):
            return False
        return (val & 1 == 1)

    @cached_property
    def first_bay_id(self) -> int|None:
        return self.payload_u16(2)

    @cached_property
    def bays(self) -> list[MxrDeviceUid]:
        rv = []
        for x in range(self.nb_bays):
            pl = self.payload_uuid(8 + (16 * x))
            if pl is None:
                break
            rv.append(pl)
        return rv

    def bay(self, idx:int) -> MxrDeviceUid|None:
        if idx >= self.nb_bays:
            return None
        return self.payload_uuid(8 + (16 * idx))

    @override
    def process(self) -> None:
        if (self.remote_device is not None):
            self.remote_device.on_mxr_update(self)

    def __str__(self) -> str:
        return f"{str(self.remote_device)} {'input' if self.is_input else 'output'} bay mapping: {self.bays}"
