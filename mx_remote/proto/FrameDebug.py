##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2025 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase

class FrameDebug(FrameBase):
    def process(self) -> None:
        pass

    def __str__(self) -> str:
        return f"{str(self.remote_device)} debug command"
