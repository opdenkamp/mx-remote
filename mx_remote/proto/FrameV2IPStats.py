######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for V2IP encoder/decoder statistics.'''

from functools import cached_property
import warnings
from .FrameBase import FrameBase
from .V2IPStats import (V2IPRxStats, V2IPTxStats, V2IPDeviceStats, V2IPDecoderDetail,
    V2IP_DECODER_DETAIL_OFFSET, V2IP_DECODER_PROTOCOL, V2IP_STATS_COUNTERS_LEN,
    V2IP_STATS_FULL_LEN)
from ..Interface import DeviceBase, DeviceRegistry

class FrameV2IPStats(FrameBase):
    '''V2IP encoder/decoder statistics report.'''
    @staticmethod
    def construct(registry:DeviceRegistry, device:DeviceBase, enable:bool) -> FrameBase|None:
        '''Build a stats enable/disable request frame for transmission.

        There is no free-running mode: a device reports only while a
        subscription is live, and the subscription lapses 60s after this frame.
        Send it again inside the minute to keep the 1Hz reports coming.

        The 17-byte form is the only one a device acts on; any other length is
        ignored.'''
        payload = device.remote_id.byte_value
        payload += bytes([1]) if enable else bytes([0])
        return FrameBase.construct_base(mxr=registry, opcode=0x3F, payload=payload)

    @cached_property
    def is_request(self) -> bool:
        '''Whether this is the enable/disable request, which carries no counters.'''
        return (self.payload is not None) and (len(self.payload) == 17)

    @cached_property
    def is_report(self) -> bool:
        '''Whether the payload is long enough to hold the counter blocks.

        The length is the only thing separating the two forms this opcode
        carries: a request is a uid and a flag, far short of the counters.

        Everything between the two forms is a truncated report, and reading one
        raises: payload_idx clamps a slice to what arrived rather than failing,
        so each block below is handed a buffer too short and refuses it. That
        reaches str(self) as readily as process(), and the receive path renders
        every frame it decodes to its debug log before processing it.'''
        return (self.payload is not None) and (len(self.payload) >= V2IP_STATS_COUNTERS_LEN)

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
    def decoder(self) -> V2IPDecoderDetail|None:
        '''What the sink's decoder recovered, None from a sender that predates it.

        Recognised by the frame's stamp and its length together. The length
        says the payload is long enough to hold the block; the stamp says those
        bytes are that block rather than some later growth this client has no
        name for. A sender below V2IP_DECODER_PROTOCOL appended no such block,
        so reading its tail would invent a reason, a geometry and a fault word.
        Its counters are still read.

        Neither answers whether a reserved field has been spent: a firmware that
        gives the block's reserved byte a meaning still stamps this version and
        still sends 152 bytes.'''
        if (self.protocol < V2IP_DECODER_PROTOCOL):
            return None
        pl = self.payload_idx(start=V2IP_DECODER_DETAIL_OFFSET, end=V2IP_STATS_FULL_LEN)
        if (pl is None) or (len(pl) < (V2IP_STATS_FULL_LEN - V2IP_DECODER_DETAIL_OFFSET)):
            return None
        return V2IPDecoderDetail(pl)

    @cached_property
    def stats(self) -> V2IPDeviceStats:
        rv = V2IPDeviceStats()
        rv.tx = self.tx
        rv.tx_per_minute = self.tx_per_minute
        rv.rx = self.rx
        rv.rx_per_minute = self.rx_per_minute
        rv.decoder = self.decoder
        return rv

    def process(self) -> None:
        '''Update the local device cache with V2IP statistics.'''
        if self.is_report and ((dev := self.remote_device) is not None):
            dev.on_mxr_update(self.stats)

    def __str__(self) -> str:
        if self.is_request:
            return f"{str(self.remote_device)} v2ip stats request: {self.stats_enabled}"
        if not self.is_report:
            return f"{str(self.remote_device)} v2ip stats: {len(self)} bytes, too short to read"
        return f"{str(self.remote_device)} v2ip stats: {self.stats}"
