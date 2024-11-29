##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from .PDUState import PDUState
import struct
from typing import Any

class FramePDUState(FrameBase):
    ''' pdu state frame, sent every minute by devices on the network '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)
        self._state = PDUState(self)

    @property
    def state(self) -> PDUState:
        return self._state

    @property
    def current(self) -> float:
        # current (A)
        return round(struct.unpack('f', self.payload[0:4])[0], 2)

    @property
    def voltage(self) -> float:
        # voltage (V)
        return round(struct.unpack('f', self.payload[4:8])[0], 2)

    @property
    def power(self) -> float:
        # power consumption (W)
        return round(struct.unpack('f', self.payload[8:12])[0], 2)

    @property
    def dissipation(self) -> float:
        # power dissipation (W)
        return round(struct.unpack('f', self.payload[12:16])[0], 2)

    #@property
    #def power_factor(self) -> float:
    #    # power factor (NOT SUPPORTED)
    #    return round(struct.unpack('f', self.payload[16:20])[0], 2)

    @property
    def frequency(self) -> float:
        # AC frequency
        return round(struct.unpack('f', self.payload[20:24])[0], 2)

    def outlet_state(self, outlet):
        return self.payload[24 + outlet] if outlet < 8 else 0

    def process(self) -> None:
        # update the local cached state
        dev = self.mxr.get(self.remote_id)
        if dev is not None:
            dev.on_mxr_update_pdu(self.state)

    def __eq__(self, other:Any) -> bool:
        if not isinstance(other, FramePDUState):
            return False
        return (self.payload[0:16].append(self.payload[24:32])) == \
            (other.payload[0:16].append(other.payload[24:32]))

    def __ne__(self, other:Any) -> bool:
        return not self.__eq__(other)

