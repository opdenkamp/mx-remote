######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for remote control action events received by a bay.'''

from functools import cached_property
from .FrameBase import FrameBase
from .Constants import RCAction, decode_enum
from ..Interface import BayBase, DeviceRegistry
import logging

_LOGGER = logging.getLogger(__name__)

# mxr_action_data wire layout:
#   0..2   u16 local_bay    mbay_port_id, a port on the transmitting device
#   2..4   u16 action       rc_perform_action_t
#
# Units old enough to predate the widening of the bay id send it as one byte
# with the action at 1, three bytes in all. RC_ACTION's protocol floor is 0x01
# and was never raised alongside the widening, so a current unit stamps 0x01 on
# the wide form and the stamp cannot separate the two. The payload length can:
# 4 wide, 3 narrow.
_WIDE_SIZE = 4

class FrameRCAction(FrameBase):
    '''Remote control action received by a bay.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:BayBase, action:RCAction) -> FrameBase|None:
        '''Build an RC action frame for transmission.'''
        payload = target.device.remote_id.byte_value
        payload += bytes([(target.port & 0xFF), ((target.port >> 8) & 0xFF), (int(action.value) & 0xFF), ((int(action.value) >> 8) & 0xFF)])
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x0E, payload=payload)

    @cached_property
    def _wide(self) -> bool:
        '''Whether the sender used the two-byte bay id.'''
        pl = self.payload
        return (pl is not None) and (len(pl) >= _WIDE_SIZE)

    @cached_property
    def bay(self) -> BayBase|None:
        '''Bay that received the action.

        Reading a wide bay id one byte at a time is worse than an off-by-one:
        MBAY_PORT_ID_INVALID and MBAY_PORT_ID_NOT_ROUTED truncate to 255 and
        254, which are port numbers a bay can really have, so an unrouted bay
        resolves to a different real bay instead of to nothing.
        '''
        return self.payload_bay(device=self.remote_device, idx=0, u16=self._wide)

    @cached_property
    def action(self) -> RCAction|None:
        '''Remote control action type.'''
        return decode_enum(RCAction, self.payload_u16(idx=2 if self._wide else 1))

    def process(self) -> None:
        '''Update the local device cache with the RC action.'''
        if ((bay := self.bay) is not None) and ((action := self.action) is not None):
            bay.on_mxr_update(action)

    def __str__(self) -> str:
        return f"{self.bay} action receive: {self.action}"
