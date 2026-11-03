######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for a OneIP output's tiling window.'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import DeviceBase, DeviceRegistry, MxrDeviceUid
import struct

class FrameV2IPTiling(FrameBase):
    '''The window of the decoded source picture a OneIP output crops out
    and scales up, for a video wall, in pixels.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:DeviceBase, pos_x:int, pos_y:int, width:int, height:int) -> FrameBase|None:
        '''Set the window target, a OneIP output, shows: the output, then the
        window's origin and size.'''
        payload = target.remote_id.byte_value + struct.pack('<4H', pos_x, pos_y, width, height)
        return FrameBase.construct_base(mxr=mxr, target=target, opcode=0x40, payload=payload)

    def process(self) -> None:
        '''No-op: the output keeps a window only in memory and may refuse one
        silently, so a write says nothing about what it shows.'''
        pass

    @cached_property
    def target_device(self) -> DeviceBase|None:
        '''The output the window is for.'''
        return self.mxr.get_by_uid(self.target_uid)

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        '''UID of the output the window is for.'''
        return self.payload_uuid(0)

    @cached_property
    def position_x(self) -> int|None:
        '''The window's left edge, in pixels.'''
        return self.payload_u16(16)

    @cached_property
    def position_y(self) -> int|None:
        '''The window's top edge, in pixels.'''
        return self.payload_u16(18)

    @cached_property
    def width(self) -> int|None:
        '''The window's width in pixels; 0 shows the whole picture.'''
        return self.payload_u16(20)

    @cached_property
    def height(self) -> int|None:
        '''The window's height in pixels; 0 shows the whole picture.'''
        return self.payload_u16(22)

    def __str__(self) -> str:
        return f"{str(self.target_device)} tiling configuration: x={self.position_x} y={self.position_y} width={self.width} height={self.height}"
