##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
import struct

class FrameFirmwareVersion(FrameBase):
    def __init__(self, header:FrameHeader):
        super().__init__(header)
        self._type = self.payload[0]
        self._hash = struct.unpack('<L', self.payload[4:8])[0]
        self._timestamp = struct.unpack('<L', self.payload[8:12])[0]
        self._name = self.payload[12:].split(b'\0',1)[0].decode('ascii')

    @property
    def fw_type(self):
        return self._type

    @property
    def name(self):
        return self._name

    @property
    def hash(self):
        return self._hash

    @property
    def timestamp(self):
        return self._timestamp

    def __str__(self) -> str:
        return f"firmware version: type {self.fw_type}: '{self.name}' hash: {hex(self.hash)} timestamp: {self.timestamp}"

    def __repr__(self) -> str:
        return str(self)