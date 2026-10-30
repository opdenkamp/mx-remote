######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for OneIP video wall tiling configuration.'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import DeviceBase, DeviceRegistry, MxrDeviceUid
import struct

class FrameV2IPTiling(FrameBase):
    '''OneIP tiling configuration for video wall setups.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:DeviceBase, pos_x:int, pos_y:int, width:int, height:int) -> FrameBase|None:
        '''Set the window target, a OneIP output, shows: the output, then the
        window's origin and size.'''
        payload = target.remote_id.byte_value + struct.pack('<4H', pos_x, pos_y, width, height)
        return FrameBase.construct_base(mxr=mxr, target=target, opcode=0x40, payload=payload)

    def process(self) -> None:
        '''No-op; tiling data is informational only.'''
        pass

    @cached_property
    def target_device(self) -> DeviceBase|None:
        '''Target device for tiling configuration.'''
        return self.mxr.get_by_uid(self.target_uid)

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        '''UID of the target device.'''
        return self.payload_uuid(0)

    @cached_property
    def position_x(self) -> int|None:
        '''Horizontal position in the tile grid.'''
        return self.payload_u16(16)

    @cached_property
    def position_y(self) -> int|None:
        '''Vertical position in the tile grid.'''
        return self.payload_u16(18)

    @cached_property
    def width(self) -> int|None:
        '''Tile width.'''
        return self.payload_u16(20)

    @cached_property
    def height(self) -> int|None:
        '''Tile height.'''
        return self.payload_u16(22)

    def __str__(self) -> str:
        return f"{str(self.target_device)} tiling configuration: x={self.position_x} y={self.position_y} width={self.width} height={self.height}"
