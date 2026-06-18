######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for bay status updates (signal, features, status flags).'''

from functools import cached_property
from .Constants import BayStatusMask, BayFeaturesMask
from .FrameBase import FrameBase
from ..Interface import BayBase, SignalStatus
import logging

_LOGGER = logging.getLogger(__name__)

class FrameBayStatus(FrameBase):
    '''Bay status report including signal type, status flags, and feature mask.'''
    @cached_property
    def bay(self) -> BayBase|None:
        '''Bay this status report applies to.'''
        return self.payload_bay(device=self.remote_device, idx=0)

    @cached_property
    def signal_type(self) -> str|None:
        '''Signal type description string.'''
        return self.payload_str(2, 16)

    @cached_property
    def status(self) -> BayStatusMask|None:
        '''Bay status flags bitmask.'''
        pl = self.payload_u32(20)
        if (pl is None):
            return None
        return BayStatusMask(pl)

    @cached_property
    def features(self) -> BayFeaturesMask|None:
        '''Bay features bitmask.'''
        pl = self.payload_u32(24)
        if pl is not None:
            return BayFeaturesMask(pl)
        return None

    def process(self) -> None:
        '''Update the local device cache with bay status, features, and signal info.'''
        if self.bay is None:
            _LOGGER.debug("bay not registered yet")
            return

        if (self.features is not None):
            self.bay.on_mxr_update(self.features)

        if (self.status is not None):
            self.bay.on_mxr_update(self.status)
            if BayStatusMask.SIGNAL_DETECTED not in self.status or not self.bay.device.is_v2ip:
                self.bay.on_mxr_update(SignalStatus(detected=BayStatusMask.SIGNAL_DETECTED in self.status, description=self.signal_type))

    def __str__(self) -> str:
        return f"bay status {self.bay} signal '{self.signal_type}' status {self.status} features {self.features}"
