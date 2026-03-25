##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import DeviceBase, MxrDeviceUid

class FrameV2IPTiling(FrameBase):
    def process(self) -> None:
        pass

    @cached_property
    def target_device(self) -> DeviceBase|None:
        return self.mxr.get_by_uid(self.target_uid)

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        return self.payload_uuid(0)

    @cached_property
    def position_x(self) -> int|None:
        return self.payload_u16(16)

    @cached_property
    def position_y(self) -> int|None:
        return self.payload_u16(18)

    @cached_property
    def width(self) -> int|None:
        return self.payload_u16(20)

    @cached_property
    def height(self) -> int|None:
        return self.payload_u16(22)

    def __str__(self) -> str:
        return f"{str(self.target_device)} tiling configuration: x={self.position_x} y={self.position_y} width={self.width} height={self.height}"
