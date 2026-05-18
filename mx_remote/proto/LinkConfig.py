##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Link configuration protocol message parsing for MX Remote device connections.'''

from typing import List
from .FrameBase import FrameBase
from ..Interface import DeviceBase, BayBase
import struct

class LinkConfig:
    ''' Single link configuration '''
    def __init__(self, frame:FrameBase, payload:bytes):
        self.frame = frame
        self.payload = payload
        self._confirm:'LinkConfig|None' = None

    @property
    def remote_device(self) -> DeviceBase|None:
        '''Device instance of the device that sent this frame.'''
        return self.frame.remote_device

    @property
    def remote_port(self) -> int:
        '''Remote port number.'''
        return int(self.payload[0])

    @property
    def remote_bay(self) -> BayBase|None:
        '''Bay instance of the bay that sent this link configuration.'''
        dev = self.remote_device
        if dev is None:
            return None
        return dev.get_by_portnum(self.remote_port)

    @property
    def auto_config(self) -> bool:
        '''Auto-configuration enabled.'''
        return (int(self.payload[1]) == 1)

    @property
    def linked_serial(self) -> str:
        '''Serial number of the device linked to this bay, or empty if not linked.'''
        return self.payload[2:18].split(b'\0',1)[0].decode('ascii')

    @property
    def linked_bay_name(self) -> str:
        '''Name of the bay linked to this bay, or empty if not linked.'''
        return self.payload[18:34].split(b'\0',1)[0].decode('ascii')

    @property
    def features(self) -> int:
        '''Supported features bitmask for this link.'''
        return struct.unpack('<L', self.payload[34:38])[0]

    @property
    def is_linked(self) -> bool:
        '''Whether this bay is linked to another bay.'''
        return (len(self.linked_serial) != 0) and (len(self.linked_bay_name) != 0)

    @property
    def linked_device(self) -> DeviceBase|None:
        '''Device instance of the device linked to this bay.'''
        if not self.is_linked:
            return None
        return self.frame.mxr.get_by_serial(self.linked_serial)

    @property
    def linked_bay(self) -> BayBase|None:
        '''Bay instance of the bay linked to this bay.'''
        dev = self.linked_device
        if dev is None:
            return None
        return dev.get_by_portname(self.linked_bay_name)

    @property
    def bays(self) -> list[BayBase]:
        '''Both bays in this link, or only the remote bay if not linked.'''
        if (self.remote_bay is None):
            return []
        linked_bay = self.linked_bay
        if (linked_bay is not None):
            return [ self.remote_bay, linked_bay ]
        return [ self.remote_bay ]

    @property
    def connected(self) -> bool:
        '''Whether this link is confirmed from both sides.'''
        if not self.is_linked:
            return False
        return self._confirm is not None

    @property
    def online(self) -> bool:
        '''Whether this link is confirmed and both bays are online.'''
        if not self.is_linked:
            return False
        if self._confirm is None:
            return False
        return self.remote_bay is not None and \
            self.remote_bay.online and \
            self.linked_bay is not None and \
            self.linked_bay.online

    def is_linked_to(self, bay:BayBase) -> bool:
        '''Check whether the given bay is part of this link.'''
        if self.remote_bay == bay:
            return True
        linked_bay = self.linked_bay
        if linked_bay is None:
            return False
        return linked_bay == bay

    def other_bay(self, bay:BayBase) -> BayBase|None:
        '''Return the other bay in this link, given one of the two bays.'''
        if not self.is_linked:
            return None
        if self.remote_bay == bay:
            return self.linked_bay
        return self.remote_bay

    def process(self) -> None:
        '''Register or update this link in the local cache.'''
        bay = self.remote_bay
        if bay is None:
            return
        self.frame.mxr.links.update(bay=bay, linked_serial=self.linked_serial, linked_bay=self.linked_bay_name, features=self.features)

    def __str__(self) -> str:
        if not self.is_linked:
            return "{} not linked".format(str(self.remote_bay))
        return "{} link serial:{} remote bay:{} features:{}".format(str(self.remote_bay), self.linked_serial, self.linked_bay_name, str(self.features))
