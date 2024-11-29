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
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    @property
    def bay(self)  -> BayBase:
        # bay on which the volume changed
        portnum = self.payload[0]
        dev = self.remote_device
        if dev is None:
            return
        return dev.get_by_portnum(portnum)

    @property
    def volume_left(self) -> int:
        # left channel volume %
        r = int(self.payload[1])
        if r > 100:
            return None
        return r

    @property
    def volume_right(self) -> int:
        # right channel volume %
        r = int(self.payload[2])
        if r > 100:
            return None
        return r

    @property
    def muted(self) -> MuteStatus:
        # mute status
        if len(self) < 4:
            return None
        return MuteStatus(self.payload[3])

    def process(self) -> None:
        # update the local cache
        bay = self.bay
        if bay is None:
            return
        muted = self.muted
        muted_left = muted.left if (muted is not None) else None
        muted_right = muted.right if (muted is not None) else None
        bay.on_mxr_volume_update(VolumeMuteStatus(self.volume_left, self.volume_right, muted_left, muted_right))

    def __str__(self) -> str:
        return f"volume bay:{str(self.bay)} volume:{self.volume_left}/{self.volume_right} muted:{self.muted}"
