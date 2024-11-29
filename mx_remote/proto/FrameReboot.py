##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import DeviceBase, DeviceRegistry

class FrameReboot(FrameBase):
    ''' remote control key press or action '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    def construct(mxr:DeviceRegistry, target:DeviceBase) -> FrameBase:
        frame:FrameBase = FrameBase.construct_frame(mxr=mxr, opcode=0x28)
        frame.payload = target.remote_id.byte_value
        return frame

    def process(self) -> None:
        pass

    def __str__(self) -> str:
        return "reboot"
