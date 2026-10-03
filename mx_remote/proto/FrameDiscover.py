######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for network device discovery.'''

import warnings
from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import DeviceRegistry
from ..Uid import MxrDeviceUid

# Payload: empty to ask every device, or the 16 byte uid of the one device
# asked. Any other length asks every device, which is also how a receiver that
# predates the uid form reads the uid form.

class FrameDiscover(FrameBase):
    '''Discovery frame that asks devices on the network to send their info.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:MxrDeviceUid|None=None) -> FrameBase|None:
        '''Build a discover asking every device, or only target.

        Not refused for a target that predates the uid form: it answers as if
        every device had been asked.'''
        payload = bytes([]) if (target is None) else target.byte_value
        return FrameBase.construct_base(mxr=mxr, opcode=1, protocol=1, payload=payload)

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        '''The one device asked, or None when every device is.'''
        if (self.payload is None) or (len(self.payload) != 16):
            return None
        return self.payload_uuid(0)

    def __str__(self) -> str:
        if (self.target_uid is None):
            return "discover devices"
        return f"discover {self.mxr.uid_to_user_string(self.target_uid)}"

def constructFrameDiscover(mxr:DeviceRegistry) -> FrameBase|None:
    warnings.warn("use FrameDiscover.construct() instead", DeprecationWarning)
    return FrameDiscover.construct(mxr=mxr)