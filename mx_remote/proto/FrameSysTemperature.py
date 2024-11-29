##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from typing import Any

class FrameSysTemperature(FrameBase):
    ''' system temperature frame, sent every minute by devices on the network '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    @property
    def nb_sensors(self) -> int:
        # number of temperature sensor readings
        return int(self.payload[0])

    @property
    def temperature(self) -> list[int]:
        # list of all readings in this frame
        rv = []
        ptr = 0
        while ptr < self.nb_sensors:
            ptr = ptr + 1
            rv.append(int(self.payload[ptr]))
        return rv

    def process(self) -> None:
        # update the local cache
        dev = self.mxr.get_by_uid(self.remote_id)
        if dev is not None:
            dev.on_mxr_temperature(self)

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, FrameSysTemperature) and \
                (self.nb_sensors == other.nb_sensors) and \
                (self.temperature == other.temperature)

    def __ne__(self, other: Any) -> bool:
        return not isinstance(other, FrameSysTemperature) or \
                (self.nb_sensors != other.nb_sensors) or \
                (self.temperature != other.temperature)

    def __str__(self) -> str:
        return "temperature: {}".format(str(self.temperature))

