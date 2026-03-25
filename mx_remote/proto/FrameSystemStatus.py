##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################

from typing import override
from .FrameBase import FrameBase

class FrameSystemStatus(FrameBase):
    @override
    def process(self) -> None:
        if ((dev := self.remote_device) is not None):
            dev.on_mxr_update(self)

    @property
    def status(self) -> int|None:
        return self.payload_u16(idx=16)

    @property
    def message(self) -> str|None:
        return self.payload_str(idx=18)

    def __str__(self) -> str:
        return f"{str(self.remote_device)} system status: {self.status} / {self.message}"
