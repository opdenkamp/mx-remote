##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import BayBase, SignalStatus

class FrameSignalStatus(FrameBase):
    ''' signal status changed '''
    @cached_property
    def bay(self)  -> BayBase|None:
        return self.payload_bay(device=self.remote_device, idx=0)

    @cached_property
    def signal(self) -> bool|None:
        # signal detected
        return self.payload_bool(1)

    @cached_property
    def signal_type(self) -> str|None:
        # signal type description
        if len(self) <= 2:
            return None
        return self.payload_str(2)

    def process(self) -> None:
        # update the local cache
        if ((bay := self.bay) is None) or ((signal := self.signal) is None):
            return
        bay.on_mxr_update(SignalStatus(detected=signal, description=self.signal_type))

    def __str__(self) -> str:
        return f"signal status {str(self.bay)} - detected={self.signal} type={self.signal_type}"
