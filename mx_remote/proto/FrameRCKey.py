######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for remote control key press events.'''

from functools import cached_property
from .FrameBase import FrameBase
from .Constants import RCKey, decode_enum
from ..Interface import BayBase

# mxr_key_data wire layout:
#   0..2   u16 local_bay    mbay_port_id, a port on the transmitting device
#   2..4   u16 key          rc_key_t
#
# Units old enough to predate the widening of the bay id send it as one byte
# with the key at 1, three bytes in all. RC_KEY's protocol floor is 0x01 and was
# never raised alongside the widening, so a current unit stamps 0x01 on the wide
# form and the stamp cannot separate the two. The payload length can: 4 wide, 3
# narrow.
_WIDE_SIZE = 4

class FrameRCKey(FrameBase):
    ''' remote control key press or action '''
    @cached_property
    def _wide(self) -> bool:
        '''Whether the sender used the two-byte bay id.'''
        pl = self.payload
        return (pl is not None) and (len(pl) >= _WIDE_SIZE)

    @cached_property
    def bay(self) -> BayBase|None:
        '''Bay that received the key press.

        Reading a wide bay id one byte at a time is worse than an off-by-one:
        MBAY_PORT_ID_INVALID and MBAY_PORT_ID_NOT_ROUTED truncate to 255 and
        254, which are port numbers a bay can really have, so an unrouted bay
        resolves to a different real bay instead of to nothing.
        '''
        return self.payload_bay(device=self.remote_device, idx=0, u16=self._wide)

    @cached_property
    def key(self) -> RCKey|None:
        '''Remote control key that was pressed.'''
        return decode_enum(RCKey, self.payload_u16(idx=2 if self._wide else 1))

    def process(self) -> None:
        '''Update the local device cache with the key press event.'''
        if ((bay := self.bay) is not None) and ((key := self.key) is not None):
            bay.on_mxr_update(key)

    def __str__(self) -> str:
        return "{} key pressed: {}".format(str(self.bay), repr(self.key))
