######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for device connect/disconnect status notifications.'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import BayBase, ConnectReport, ConnectStatus, P8ModelInfo
import ipaddress

_P8_MODEL_INFO_AT = 4
'''The long form's model_info, behind the port, the flag and two bytes of padding.'''
_P8_MODEL_INFO_SIZE = 92
_P8_TEXT_LEN = 16

class FrameConnectStatus(FrameBase):
    '''Device was connected or disconnected. For sources, this means an input signal was detected.'''
    @cached_property
    def bay(self) -> BayBase|None:
        '''Bay whose connect status changed.'''
        return self.payload_bay(device=self.remote_device, idx=0)

    @cached_property
    def connected(self) -> ConnectStatus:
        '''New connected / signal detect status.'''
        pl = self.payload_bool(1)
        if (pl is not None):
            return ConnectStatus.CONNECTED if pl else ConnectStatus.DISCONNECTED
        return ConnectStatus.UNKNOWN

    @cached_property
    def p8_device(self) -> P8ModelInfo|None:
        '''The Pulse-Eight device a connecting long frame names: vendor, model,
        board revision, serial and version, then the bay's mode and number on
        the device (4 bytes each), the loopback and HDMI flags, and the
        device's address, mask and gateway.'''
        if (self.connected != ConnectStatus.CONNECTED) or (self.payload is None) \
                or (len(self.payload) < _P8_MODEL_INFO_AT + _P8_MODEL_INFO_SIZE):
            return None
        m = self.payload[_P8_MODEL_INFO_AT:_P8_MODEL_INFO_AT + _P8_MODEL_INFO_SIZE]
        def text(at:int) -> str:
            return m[at:at + _P8_TEXT_LEN].split(b'\0', 1)[0].decode('ascii', errors='replace')
        def i32(at:int) -> int:
            return int.from_bytes(m[at:at + 4], 'little', signed=True)
        def ip(at:int) -> str:
            return str(ipaddress.IPv4Address(m[at:at + 4]))
        return P8ModelInfo(vendor=text(0), model=text(16), board_rev=m[32], serial=text(33),
                           version=text(49), remote_mode=i32(68), remote_bay=i32(72),
                           loopback=(m[76] != 0), hdmi=(m[77] != 0),
                           ip=ip(80), mask=ip(84), gateway=ip(88))

    def process(self) -> None:
        '''Update the local device cache with the connect status.'''
        bay = self.bay
        if (bay is not None):
            bay.on_mxr_update(ConnectReport(self.connected, self.p8_device))

    def __str__(self) -> str:
        return f"connect status {self.bay}: {self.connected}"
