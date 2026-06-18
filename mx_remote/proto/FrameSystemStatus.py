######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for device system status notifications.'''

from typing import override
from .FrameBase import FrameBase

class FrameSystemStatus(FrameBase):
    '''System status report from a device.'''
    @override
    def process(self) -> None:
        '''Update the local device cache with the system status.'''
        if ((dev := self.remote_device) is not None):
            dev.on_mxr_update(self)

    @property
    def status(self) -> int|None:
        '''Numeric status code.'''
        return self.payload_u16(idx=16)

    @property
    def message(self) -> str|None:
        '''Human-readable status message.'''
        return self.payload_str(idx=18)

    def __str__(self) -> str:
        return f"{str(self.remote_device)} system status: {self.status} / {self.message}"
