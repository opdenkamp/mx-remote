######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for remote control key press events.'''

from functools import cached_property
from .FrameBase import FrameBase
from .Constants import RCKey
from ..Interface import BayBase
class FrameRCKey(FrameBase):
    ''' remote control key press or action '''
    @cached_property
    def bay(self) -> BayBase|None:
        '''Bay that received the key press.'''
        return self.payload_bay(device=self.remote_device, idx=0, u16=(self.protocol >= 6))

    @cached_property
    def key(self) -> RCKey|None:
        '''Remote control key that was pressed.'''
        key = self.payload_u16(idx=2) if (self.device_protocol >= 6) else self.payload_u16(1)
        if (key is None):
            return None
        return RCKey(key)

    def process(self) -> None:
        '''Update the local device cache with the key press event.'''
        if ((bay := self.bay) is not None) and ((key := self.key) is not None):
            bay.on_mxr_update(key)

    def __str__(self) -> str:
        return "{} key pressed: {}".format(str(self.bay), repr(self.key))
