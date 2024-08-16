from __future__ import annotations
from .FrameBase import FrameBase
from .FrameHeader import FrameHeader

class VolumeMuteStatus:
    ''' volume and mute status '''
    def __init__(self, volume_left:int, volume_right:int, muted_left:bool=None, muted_right:bool=None):
        self._volume_left = volume_left
        self._volume_right = volume_right
        self._muted_left = muted_left
        self._muted_right = muted_right

    @property
    def volume(self) -> int:
        # combined left/right volume %
        vr = self._volume_right
        if vr is None:
            return self._volume_left
        return int((vr + self._volume_left) / 2.0)

    @property
    def volume_left(self) -> int:
        # left channel volume
        return self._volume_left if (self._volume_left is not None) else self.volume

    @property
    def volume_right(self) -> int:
        # right channel volume
        return self._volume_right if (self._volume_right is not None) else self.volume

    @property
    def muted(self) -> bool:
        # combined mute left/right status
        if (self._muted_left is None) and (self._muted_right is None):
            return None
        return ((self._muted_left is not None) and self._muted_left) or \
            ((self._muted_right is not None) and self._muted_right)

    @property
    def muted_left(self) -> bool:
        # left channel muted
        return self._muted_left if (self._muted_left is not None) else self.muted

    @property
    def muted_right(self) -> bool:
        # right channel muted
        return self._muted_right if (self._muted_right is not None) else self.muted

    def update(self, other:VolumeMuteStatus) -> bool:
        changed = False
        if other._volume_left is not None:
            changed = changed or (self._volume_left is None) or (self._volume_left != other._volume_left)
            self._volume_left = other._volume_left
        if other._volume_right is not None:
            changed = changed or (self._volume_right is None) or (self._volume_right != other._volume_right)
            self._volume_right = other._volume_right
        if other._muted_left is not None:
            changed = changed or (self._muted_left is None) or (self._muted_left != other._muted_left)
            self._muted_left = other._muted_left
        if other._muted_right is not None:
            changed = changed or (self._muted_right is None) or (self._muted_right != other._muted_right)
            self._muted_right = other._muted_right
        return changed

class MuteStatus:
    ''' mute left/right status '''
    def __init__(self, val:int):
        self._val = val

    @property
    def left(self) -> bool:
        # left channel muted
        return ((self._val & (1 << 0)) != 0)

    @property
    def right(self) -> bool:
        # right channel muted
        return ((self._val & (1 << 1)) != 0)

    @property
    def muted(self) -> bool:
        # left or right channel muted (or both)
        return (self._val != 0)

    def __str__(self) -> str:
        return f"left:{self.left} right:{self.right}"

class FrameVolume(FrameBase):
    ''' bay volume change information frame '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    @property
    def bay(self)  -> 'mx_remote.remote.Bay.Bay':
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
