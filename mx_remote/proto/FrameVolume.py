##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from __future__ import annotations
from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from .Data import VolumeMuteStatus, MuteStatus
from ..Interface import BayBase

class FrameVolume(FrameBase):
    ''' bay volume change information frame '''
    @property
    def bay(self) -> BayBase|None:
        # bay on which the volume changed
        portnum = self.payload_u8(0)
        if (portnum is None):
            return None
        dev = self.remote_device
        if dev is None:
            return
        return dev.get_by_portnum(portnum)

    @property
    def volume_left(self) -> int|None:
        # left channel volume %
        r = self.payload_u8(1)
        if (r is None) or (r > 100):
            return None
        return r

    @property
    def volume_right(self) -> int|None:
        # right channel volume %
        r = self.payload_u8(2)
        if (r is None) or (r > 100):
            return None
        return r

    @property
    def muted(self) -> MuteStatus|None:
        # mute status
        r = self.payload_u8(3)
        if (r is None):
            return None
        return MuteStatus(r)

    def process(self) -> None:
        # update the local cache
        bay = self.bay
        if bay is None:
            return
        muted = self.muted
        muted_left = muted.left if (muted is not None) else None
        muted_right = muted.right if (muted is not None) else None
        bay.on_mxr_update(VolumeMuteStatus(self.volume_left, self.volume_right, muted_left, muted_right))

    def __str__(self) -> str:
        return f"volume bay:{str(self.bay)} volume:{self.volume_left}/{self.volume_right} muted:{self.muted}"
