from .FrameBase import FrameBase
from .FrameHeader import FrameHeader

import logging

class FramePowerChange(FrameBase):
    ''' power status changed of a device connected to a bay '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)
        self.dev = None

    @property
    def bay(self) -> 'mx_remote.remote.Bay.Bay':
        # bay that changed
        portnum = self.payload[0]
        dev = self.remote_device
        if dev is None:
            return
        return dev.get_by_portnum(portnum)

    @property
    def power(self) -> bool:
        # new power status
        return (self.payload[1] == 1)

    def process(self) -> None:
        bay = self.bay
        if bay is not None:
            bay.power_status = 'on' if self.power else 'off'

    def __str__(self):
        return "{} power status: {}".format(str(self.bay), str(self.power))
