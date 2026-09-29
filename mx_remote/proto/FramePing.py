######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame asking one device to announce itself now.'''

from functools import cached_property
from ..compat import override
from .FrameBase import FrameBase
from ..Interface import DeviceBase, DeviceRegistry
from ..Uid import MxrDeviceUid

# Payload: the uid of the device asked, 16 bytes.
#
# A device on 0x2A pings a peer it suspects is gone, and takes it offline when
# no frame comes back within about 1.5s. Every receiver sees the ping; only the
# one it names answers, with a hello.

class FramePing(FrameBase):
    '''A request for one device to hello now.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:DeviceBase) -> FrameBase|None:
        '''Build a ping for target. None for a device below 0x2A, which drops it.'''
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x4A, payload=target.remote_id.byte_value)

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        '''The device asked to announce itself.'''
        return self.payload_uuid(0)

    @override
    def process(self) -> None:
        '''Hand a ping addressed to this client to the registry, which answers it.

        A ping for another device asks nothing of this one.'''
        if (self.target_uid is not None) and (self.target_uid == self.mxr.uid):
            self.mxr.on_mxr_update(self)

    def __str__(self) -> str:
        return f"ping {self.mxr.uid_to_user_string(self.target_uid)}"
