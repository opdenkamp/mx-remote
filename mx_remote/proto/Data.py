##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

class MuteStatus:
    ''' mute left/right status '''
    def __init__(self, val:int):
        self._val = val

    @property
    def value(self) -> int:
        return self._val

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

class VolumeMuteStatus:
    ''' volume and mute status '''
    def __init__(self, volume_left:int, volume_right:int, muted_left:bool=None, muted_right:bool=None):
        self._volume_left = volume_left
        self._volume_right = volume_right
        self._muted_left = muted_left
        self._muted_right = muted_right

    @property
    def value(self) -> bytes:
        return bytes(bytearray([
            self.volume_left,
            self.volume_right,
            self.muted_value,
        ]))

    @property
    def muted_value(self) -> int:
        if not self.muted:
            return 0
        if self.muted_left and self.muted_right:
            return 3
        if self.muted_left:
            return 1
        return 2

    @property
    def volume(self) -> int:
        # combined left/right volume %
        vr = self._volume_right
        if vr is None:
            return self._volume_left if self._volume_left is not None else 0
        return int((vr + self._volume_left) / 2.0)

    @volume.setter
    def volume(self, volume:int) -> None:
        self.volume_left = volume
        if self._volume_right is not None:
            self.volume_right = volume

    @property
    def volume_left(self) -> int:
        # left channel volume
        return self._volume_left if (self._volume_left is not None) else self.volume

    @volume_left.setter
    def volume_left(self, volume:int) -> None:
        self._volume_left = volume

    @property
    def volume_right(self) -> int:
        # right channel volume
        return self._volume_right if (self._volume_right is not None) else self.volume

    @volume_right.setter
    def volume_right(self, volume:int) -> None:
        self._volume_right = volume

    @property
    def muted(self) -> bool:
        # combined mute left/right status
        if (self._muted_left is None) and (self._muted_right is None):
            return None
        return ((self._muted_left is not None) and self._muted_left) or \
            ((self._muted_right is not None) and self._muted_right)

    @muted.setter
    def muted(self, muted:bool) -> None:
        self.muted_left = muted
        if self._muted_right is not None:
            self.muted_right = muted

    @property
    def muted_left(self) -> bool:
        # left channel muted
        return self._muted_left if (self._muted_left is not None) else self.muted

    @muted_left.setter
    def muted_left(self, muted:bool) -> None:
        self._muted_left = muted

    @property
    def muted_right(self) -> bool:
        # right channel muted
        return self._muted_right if (self._muted_right is not None) else self.muted

    @muted_right.setter
    def muted_right(self, muted:bool) -> None:
        self._muted_right = muted

    def update(self, other:'VolumeMuteStatus') -> bool:
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

    def __str__(self) -> str:
        return f"volume left:{self.volume_left} right:{self.volume_right} muted:{self.muted}"