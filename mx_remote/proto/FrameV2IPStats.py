##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Protocol frame for V2IP encoder/decoder statistics.'''

from functools import cached_property
import warnings
from .FrameBase import FrameBase
from .V2IPStats import V2IPRxStats, V2IPTxStats, V2IPDeviceStats
from ..Interface import DeviceBase, DeviceRegistry

class FrameV2IPStats(FrameBase):
    '''V2IP encoder/decoder statistics report.'''
    @staticmethod
    def construct(registry:DeviceRegistry, device:DeviceBase, enable:bool) -> FrameBase|None:
        '''Build a stats enable/disable request frame for transmission.'''
        payload = device.remote_id.byte_value
        payload += bytes([1]) if enable else bytes([0])
        return FrameBase.construct_base(mxr=registry, opcode=0x3F, payload=payload)

    @cached_property
    def is_request(self) -> bool:
        return (self.payload is not None) and (len(self.payload) == 17)

    @cached_property
    def stats_enabled(self) -> bool:
        pl = self.payload_bool(16)
        if (pl is None):
            return True
        return pl

    @cached_property
    def tx(self) -> V2IPTxStats:
        pl = self.payload_idx(start=0, end=20)
        if (pl is None):
            raise Exception("invalid FrameV2IPStats size")
        return V2IPTxStats(pl)

    @cached_property
    def tx_per_minute(self) -> V2IPTxStats:
        pl = self.payload_idx(start=20, end=40)
        if (pl is None):
            raise Exception("invalid FrameV2IPStats size")
        return V2IPTxStats(pl)

    @cached_property
    def rx(self) -> V2IPRxStats:
        pl = self.payload_idx(start=40, end=84)
        if (pl is None):
            raise Exception("invalid FrameV2IPStats size")
        return V2IPRxStats(pl)

    @cached_property
    def rx_per_minute(self) -> V2IPRxStats:
        pl = self.payload_idx(start=84, end=128)
        if (pl is None):
            raise Exception("invalid FrameV2IPStats size")
        return V2IPRxStats(pl)

    @cached_property
    def stats(self) -> V2IPDeviceStats:
        rv = V2IPDeviceStats()
        rv.tx = self.tx
        rv.tx_per_minute = self.tx_per_minute
        rv.rx = self.rx
        rv.rx_per_minute = self.rx_per_minute
        return rv

    def process(self) -> None:
        '''Update the local device cache with V2IP statistics.'''
        if (not self.is_request) and ((dev := self.remote_device) is not None):
            dev.on_mxr_update(self.stats)

    def __str__(self) -> str:
        if self.is_request:
            return f"{str(self.remote_device)} v2ip stats request: {self.stats_enabled}"
        return f"{str(self.remote_device)} v2ip stats: {self.stats}"
