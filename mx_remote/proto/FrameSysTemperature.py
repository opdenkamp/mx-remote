##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import SystemTemperature

class FrameSysTemperature(FrameBase):
    ''' system temperature frame, sent every minute by devices on the network '''
    @cached_property
    def nb_sensors(self) -> int|None:
        # number of temperature sensor readings
        return self.payload_u8(0)

    @cached_property
    def temperature(self) -> SystemTemperature:
        # list of all readings in this frame
        rv = SystemTemperature([])
        ptr = 0
        if (self.nb_sensors is None):
            return rv
        while ptr < self.nb_sensors:
            ptr = ptr + 1
            pl = self.payload_u8(ptr)
            if (pl is not None):
                rv.append(pl)
        return rv

    def process(self) -> None:
        if ((dev := self.remote_device) is not None):
            dev.on_mxr_update(self.temperature)

    def __str__(self) -> str:
        return "temperature: {}".format(str(self.temperature))

