##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import NetworkPortStatus, UtpLinkErrorStatus, UtpLinkSpeed, UtpCableStatus
import socket
import struct

class UtpCableStatusImpl(UtpCableStatus):
    def __init__(self, data):
        self._data = data

    @property
    def polarity(self) -> bool:
        return (self._data[0] == 1)

    @property
    def pair(self) -> int:
        return (self._data[1])

    @property
    def skew(self) -> int:
        return struct.unpack('<L', self._data[4:8])[0]

    @property
    def length(self) -> int:
        return struct.unpack('<L', self._data[8:12])[0]

    def __str__(self):
        return f"pair {self.pair} polarity {self.polarity} skew {self.skew}"

    def __repr__(self):
        return str(self)

class UtpLinkErrorStatusImpl(UtpLinkErrorStatus):
    def __init__(self, data):
        self._data = data

    @property
    def in_error(self) -> bool:
        return ((self._data & (1 << 0)) != 0)

    @property
    def in_fcs_error(self) -> bool:
        return ((self._data & (1 << 1)) != 0)

    @property
    def in_collision(self) -> bool:
        return ((self._data & (1 << 2)) != 0)

    @property
    def out_deferred(self) -> bool:
        return ((self._data & (1 << 3)) != 0)

    @property
    def out_excessive(self) -> bool:
        return ((self._data & (1 << 4)) != 0)

    @property
    def polarity_error(self) -> bool:
        return ((self._data & (1 << 5)) != 0)

    @property
    def skew_warning(self) -> bool:
        return ((self._data & (1 << 6)) != 0)

    @property
    def length_warning(self) -> bool:
        return ((self._data & (1 << 7)) != 0)

    def __str__(self) -> str:
        errs = ""
        if self.in_error:
            errs += "[rx errors]"
        if self.in_fcs_error:
            errs += "[rx fcs]"
        if self.in_collision:
            errs += "[rx collision]"
        if self.out_deferred:
            errs += "[tx deferred]"
        if self.out_excessive:
            errs += "[tx excessive]"
        if self.polarity_error:
            errs += "[polarity]"
        if self.skew_warning:
            errs += "[skew]"
        if self.length_warning:
            errs += "[length warning]"
        if errs == "":
            errs = "healthy"
        return errs

class NetworkPortStatusImpl(NetworkPortStatus):
    def __init__(self, data:bytes) -> None:
        self.data = data

    @cached_property
    def port(self) -> int:
        return int(self.data[0])

    @cached_property
    def errors(self) -> UtpLinkErrorStatus:
        return UtpLinkErrorStatusImpl(self.data[1])

    @cached_property
    def vct_status(self) -> list[str]:
        rv = []
        for x in range(4):
            if (self.data[2] & (1 << x) != 0):
                rv.append("WARNING")
            else:
                rv.append("healthy")
        return rv

    @cached_property
    def link_speed(self) -> UtpLinkSpeed:
        return UtpLinkSpeed(self.data[3] & 0x7)

    @cached_property
    def link_full_duplex(self) -> bool:
        return ((self.data[3] & (1 << 3)) != 0)

    @cached_property
    def name(self) -> str:
        return self.data[112:128].split(b'\0',1)[0].decode('ascii')

    @cached_property
    def ip(self) -> str:
        ip = int.from_bytes(self.data[132:136], "big")
        return socket.inet_ntoa(struct.pack('!L', ip))

    @cached_property
    def querier(self) -> str:
        ip = int.from_bytes(self.data[136:140], "big")
        return socket.inet_ntoa(struct.pack('!L', ip))

    @cached_property
    def cable_status(self) -> list[UtpCableStatus]:
        return [UtpCableStatusImpl(self.data[8:20]), UtpCableStatusImpl(self.data[20:32]), UtpCableStatusImpl(self.data[32:44]), UtpCableStatusImpl(self.data[44:56])]

    def __str__(self) -> str:
        return f"network status port {self.name} status: {self.errors} ip: {self.ip} vct: {self.vct_status} speed: {self.link_speed} full duplex: {self.link_full_duplex} cable: {str(self.cable_status)}"

class FrameNetworkStatus(FrameBase):
    @property
    def status(self) -> NetworkPortStatus|None:
        if (self.payload is None):
            return None
        return NetworkPortStatusImpl(data=self.payload)

    def process(self) -> None:
        dev = self.remote_device
        if (dev is not None) and (self.status is not None):
            dev.on_mxr_update(self.status)

    def __str__(self) -> str:
        return str(self.status)
