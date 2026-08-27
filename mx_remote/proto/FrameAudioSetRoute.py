######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame requesting an audio routing change on a target device.'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import BayBase, DeviceBase

# mxr_audio_routing_change_request wire layout:
#   0..16    u8[16] serial      MXR_SERIAL_LEN, the device to switch
#   16..18   u16 sink_bay       mbay_port_id
#   18..20   u16 source_bay     mbay_port_id
#
# Note this addresses its target by SERIAL, not by uid - unlike the video
# routing request (0x09) and every V2IP opcode.

class FrameAudioSetRoute(FrameBase):
    '''A request for a device to route one of its audio sinks to a source.

    A command rather than state: the resulting route is reported back through
    MX_ROUTE (0x08), so nothing here is cached.
    '''
    @cached_property
    def target_serial(self) -> str|None:
        '''Serial of the device being asked to switch.'''
        return self.payload_str(0, 16)

    @cached_property
    def target_device(self) -> DeviceBase|None:
        '''Device being asked to switch, if it is known to us.'''
        if ((serial := self.target_serial) is None):
            return None
        return self.mxr.get_by_serial(serial)

    @cached_property
    def sink_bay(self) -> BayBase|None:
        '''Bay on the target device that should change source.'''
        return self.payload_bay(device=self.target_device, idx=16, u16=True)

    @cached_property
    def source_bay(self) -> BayBase|None:
        '''Bay on the target device that should become the source.'''
        return self.payload_bay(device=self.target_device, idx=18, u16=True)

    def process(self) -> None:
        '''No-op: the resulting route arrives separately as MX_ROUTE (0x08).'''
        pass

    def __str__(self) -> str:
        target = self.target_device if (self.target_device is not None) else self.target_serial
        return f"{target} audio route request: {self.sink_bay} <- {self.source_bay}"
