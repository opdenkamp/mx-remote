##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from .V2IPStats import V2IPRxStats, V2IPTxStats, V2IPDeviceStats
from ..Interface import DeviceBase, DeviceRegistry

class FrameV2IPStats(FrameBase):
    ''' V2IP encoder/decoder statistics '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    def construct(registry:DeviceRegistry, device:DeviceBase, enable:bool) -> FrameBase:
        payload = device.remote_id.byte_value
        payload += bytes([1]) if enable else bytes([0])
        frame:FrameBase = FrameBase.construct_frame(mxr=registry, opcode=0x3F)
        frame.payload = payload
        return frame

    @property
    def tx(self) -> V2IPTxStats:
        return V2IPTxStats(self.payload[0:20])

    @property
    def tx_per_minute(self) -> V2IPTxStats:
        return V2IPTxStats(self.payload[20:40])

    @property
    def rx(self) -> V2IPRxStats:
        return V2IPRxStats(self.payload[40:84])

    @property
    def rx_per_minute(self) -> V2IPRxStats:
        return V2IPRxStats(self.payload[84:128])

    @property
    def stats(self) -> V2IPDeviceStats:
        rv = V2IPDeviceStats()
        rv.tx = self.tx
        rv.tx_per_minute = self.tx_per_minute
        rv.rx = self.rx
        rv.rx_per_minute = self.rx_per_minute
        return rv

    def process(self) -> None:
        if self.remote_device is not None:
            self.remote_device.v2ip_stats = self.stats

    def __str__(self) -> str:
        return f"{str(self.remote_device)} v2ip stats: {self.stats}"
