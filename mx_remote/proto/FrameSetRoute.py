######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for routing change requests (MX_SET_ROUTE, opcode 0x09).'''

from functools import cached_property
from .FrameBase import FrameBase

class FrameSetRoute(FrameBase):
    '''Routing change request payload: mxr_routing_change_request.

    Wire layout (mx_remote_proto.h:387):
        0..16  mxr_serial   serial      ASCII serial, NUL-padded
        16     mbay_port_id sink_bay    output bay to switch
        17     mbay_port_id source_bay  source bay to use
        18     uint8_t      no_power_on 1 = skip power-on commands
    '''

    @cached_property
    def serial(self) -> str | None:
        return self.payload_str(0, 16)

    @cached_property
    def sink_bay(self) -> int | None:
        return self.payload_u8(16)

    @cached_property
    def source_bay(self) -> int | None:
        return self.payload_u8(17)

    @cached_property
    def no_power_on(self) -> bool | None:
        return self.payload_bool(18)

    def __str__(self) -> str:
        return f"set route on {self.serial}: sink={self.sink_bay} source={self.source_bay} no_power_on={self.no_power_on}"
