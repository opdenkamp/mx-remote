######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for network topology information.'''

from functools import cached_property

from .FrameBase import FrameBase
from ..Uid import MxrDeviceUid
import struct

# Each entry is a uid and a u32 port mask, padded to 24 bytes.
_ENTRY_SIZE = 24

class TopologyEntry:
    '''Single entry in the topology map: a device's uid, and the mask of the
    sender's switch ports its MAC address was learnt on.'''
    def __init__(self, uid:MxrDeviceUid, mask:int):
        self.uid = uid
        self.mask = mask

    def __str__(self) -> str:
        return f"{self.uid} mask {self.mask}"

    def __repr__(self) -> str:
        return str(self)

class FrameTopology(FrameBase):
    '''Network topology data listing all known devices and their connectivity.'''
    @cached_property
    def topology(self) -> list[TopologyEntry]:
        '''List of topology entries parsed from the payload.'''
        topo = []
        data = self.payload
        if (data is None):
            return []
        while len(data) >= _ENTRY_SIZE:
            topo.append(TopologyEntry(MxrDeviceUid(data[0:16]), struct.unpack('<L', data[16:20])[0]))
            data = data[_ENTRY_SIZE:]
        return topo

    @cached_property
    def topology_user_string(self) -> list[str]:
        rv = []
        for topo in self.topology:
            rv.append(f'{self.uid_to_user_string(topo.uid)}:{topo.mask:X}')
        return rv

    def process(self) -> None:
        '''Update the local device cache with topology data.'''
        if ((dev := self.remote_device) is not None):
            dev.on_mxr_update(self)

    def __str__(self) -> str:
        return f"{self.remote_device} topology data: {self.topology_user_string}"
