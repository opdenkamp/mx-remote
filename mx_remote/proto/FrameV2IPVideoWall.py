######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for V2IP video wall window control.'''

from functools import cached_property
from .FrameBase import FrameBase
from .Constants import VideoWallOperation, video_wall_geometry_valid
from ..Interface import DeviceBase
from ..Uid import MxrDeviceUid

# vw_mesh_frame wire layout (little-endian, alignment 4, no ALIGN() attribute):
#   0..16    mxr_uid target      the addressed sink
#   16..18   u16 pos_x
#   18..20   u16 pos_y
#   20..22   u16 width
#   22..24   u16 height
#   24..26   u16 raster_w        horizontal active pixels the window was drawn against
#   26..28   u16 raster_h        vertical active pixels
#   28..29   u8  op              vw_mesh_op
#   29..32   padding, zeroed
#
# Owned by the v2ipwall module (github.com/opdenkamp/mod-v2ip-videowall,
# src/v2ip_videowall.h + src/vw_mesh.c), not by MatrixOS - MatrixOS only
# reserves the opcode number. The receiver accepts anything >= 32 bytes and
# ignores the remainder.
#
# SINGLE-SOURCED. This layout has one origin: the module source and its shipped
# disassembly (vw_set_remote at 0x1380), relayed here rather than derived. No
# second reference stands behind it, so a mistake in it would look exactly like
# a correct decode until a real wall misbehaved. Re-derive from the module repo,
# or from a captured frame, before trusting it against a bug report. Everything
# else in this package is checked against libP8/mx_remote directly.
_FRAME_SIZE = 32

class FrameV2IPVideoWall(FrameBase):
    '''A request to a sink to adopt a video wall window.

    This is a command, not state: it is only ever sent controller to sink, one
    frame per wall member, and there is no periodic broadcast and no ack on this
    opcode. A wall has no wire representation of its own - it is just a set of
    sinks each holding their own rectangle - so a controller configuring an
    N-member wall sends N independent frames.

    To read what a sink is currently showing, use V2IP_TILING (0x40). Note that
    only a STORE here writes the persisted setting: a 0x40 write to a sink with
    the v2ipwall module loaded is transient, because the module's reconciler
    pushes its own target window back within about a second.

    Every field is meaningful and none carries a validity marker, so this frame
    replaces rather than merges - the opposite of V2IP_DEVICE_CFG. A zero width
    or height is not "unset": it is the wire spelling of "clear the wall and
    show the full frame".
    '''
    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        '''UID of the sink this window is addressed to.'''
        return self.payload_uuid(0)

    @cached_property
    def target_device(self) -> DeviceBase|None:
        '''Sink this window is addressed to, if it is known to us.'''
        if ((uid := self.target_uid) is None):
            return None
        return self.mxr.get_by_uid(uid)

    @cached_property
    def operation(self) -> VideoWallOperation|None:
        '''What the sink is being asked to do with the window.'''
        if ((pl := self.payload_u8(28)) is None):
            return None
        try:
            return VideoWallOperation(pl)
        except ValueError:
            return None

    @cached_property
    def has_window(self) -> bool:
        '''Whether this frame carries geometry at all.

        A revert zeroes the window and raster and the receiver ignores those
        bytes, so their zeros must not be read as a clear.
        '''
        return (self.operation != VideoWallOperation.REVERT)

    @cached_property
    def position_x(self) -> int|None:
        '''Horizontal start position of the window, or None on a revert.'''
        return self.payload_u16(16) if self.has_window else None

    @cached_property
    def position_y(self) -> int|None:
        '''Vertical start position of the window, or None on a revert.'''
        return self.payload_u16(18) if self.has_window else None

    @cached_property
    def width(self) -> int|None:
        '''Window width, or None on a revert. Zero clears the wall.'''
        return self.payload_u16(20) if self.has_window else None

    @cached_property
    def height(self) -> int|None:
        '''Window height, or None on a revert. Zero clears the wall.'''
        return self.payload_u16(22) if self.has_window else None

    @cached_property
    def raster_width(self) -> int|None:
        '''Horizontal active pixels the window was authored against.

        The raster travels with the window because only the controller knows
        what the installer drew against; a sink deriving it from whatever it
        happens to be showing would store the window against the wrong picture.
        '''
        return self.payload_u16(24) if self.has_window else None

    @cached_property
    def raster_height(self) -> int|None:
        '''Vertical active pixels the window was authored against.'''
        return self.payload_u16(26) if self.has_window else None

    @cached_property
    def clears_wall(self) -> bool:
        '''Whether this window asks the sink to show the full frame again.'''
        return self.has_window and ((self.width == 0) or (self.height == 0))

    @cached_property
    def geometry_valid(self) -> bool:
        '''Whether the window satisfies the constraints a sink enforces.

        The controller checks this before transmitting, so a frame failing it
        came from somewhere else and the sink will refuse the window.
        '''
        if not self.has_window:
            return True
        if (self.position_x is None) or (self.width is None) or (self.height is None):
            return False
        return video_wall_geometry_valid(pos_x=self.position_x, width=self.width, height=self.height)

    def process(self) -> None:
        '''No-op: this opcode carries a command, not readable state.

        A sink's current window is reported through V2IP_TILING (0x40), and
        there is no ack here - the transmit only says the frame went out, not
        that the sink accepted the window or that it reached the screen. So
        there is nothing here that can be cached as a device's state.
        '''
        pass

    def __str__(self) -> str:
        target = self.target_device if (self.target_device is not None) else self.target_uid
        op = self.operation
        if not self.has_window:
            return f"{target} video wall: {op}"
        if self.clears_wall:
            return f"{target} video wall: {op} - cleared"
        geom = f"x={self.position_x} y={self.position_y} {self.width}x{self.height}"
        raster = f" of {self.raster_width}x{self.raster_height}"
        invalid = "" if self.geometry_valid else " (invalid geometry)"
        return f"{target} video wall: {op} - {geom}{raster}{invalid}"
