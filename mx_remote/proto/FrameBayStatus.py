##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
from .Constants import BayStatusMask, BayFeaturesMask
from .FrameBase import FrameBase
from ..Interface import BayBase, SignalStatus
import logging

_LOGGER = logging.getLogger(__name__)

class FrameBayStatus(FrameBase):
    @cached_property
    def bay(self) -> BayBase|None:
        return self.payload_bay(device=self.remote_device, idx=0)

    @cached_property
    def signal_type(self) -> str|None:
        return self.payload_str(2, 16)

    @cached_property
    def status(self) -> BayStatusMask|None:
        pl = self.payload_u32(20)
        if (pl is None):
            return None
        return BayStatusMask(pl)

    @cached_property
    def features(self) -> BayFeaturesMask|None:
        pl = self.payload_u32(24)
        if pl is not None:
            return BayFeaturesMask(pl)
        return None

    def process(self) -> None:
        if self.bay is None:
            _LOGGER.debug("bay not registered yet")
            return

        if (self.features is not None):
            self.bay.on_mxr_update(self.features)

        if (self.status is not None):
            self.bay.on_mxr_update(self.status)
            if not self.status.signal_detected or not self.bay.device.is_v2ip:
                self.bay.on_mxr_update(SignalStatus(detected=self.status.signal_detected, description=self.signal_type))

    def __str__(self) -> str:
        return f"bay status {self.bay} signal '{self.signal_type}' status {self.status} features {self.features}"
