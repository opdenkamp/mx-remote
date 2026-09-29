######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame carrying the time of a mesh.'''

from datetime import datetime, timezone
from functools import cached_property
from ..compat import override
from .FrameBase import FrameBase
from ..Interface import DeviceClock, DeviceRegistry

# Payload: seconds since 1970 UTC, u32.
#
# The mesh controller announces its clock with every periodic broadcast, once it
# has been set. A device takes the time only from the controller or a
# management application, and keeps its own clock where that is within 2s.

class FrameTime(FrameBase):
    '''The time a device announces for its mesh.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, when:datetime) -> FrameBase|None:
        '''Build the broadcast that sets the clock of every device hearing it.

        None for a time before 1970 or past what 32 bits of seconds hold, in 2106.
        A naive datetime is taken as local time.'''
        utc = int(when.timestamp())
        if not (0 <= utc <= 0xFFFFFFFF):
            return None
        return FrameBase.construct_base(mxr=mxr, opcode=0x4D, payload=utc.to_bytes(4, 'little'))

    @cached_property
    def utc(self) -> int|None:
        '''The announced time in seconds since 1970, None for a frame too short.'''
        return self.payload_u32(0)

    @override
    def process(self) -> None:
        '''Record the time against the device that announced it, with when it arrived.'''
        if ((utc := self.utc) is not None) and (self.remote_device is not None):
            self.remote_device.on_mxr_update(DeviceClock(utc=utc, received=self.timestamp))

    def __str__(self) -> str:
        if (self.utc is None):
            return "time <short>"
        return f"time {datetime.fromtimestamp(self.utc, timezone.utc).isoformat()}"
