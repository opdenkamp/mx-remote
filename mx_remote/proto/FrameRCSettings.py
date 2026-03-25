##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase

class FrameRCSettings(FrameBase):
    def process(self) -> None:
        pass

    def __str__(self) -> str:
        return f"{str(self.remote_device)} remote control settings"
