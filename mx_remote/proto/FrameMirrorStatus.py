##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import DeviceBase
from ..Uid import MxrDeviceUid

class FrameMirrorStatus(FrameBase):
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    @property
    def target(self) -> MxrDeviceUid:
        if len(self.payload) < 16:
            return None
        return MxrDeviceUid(self.payload[0:16])

    @property
    def is_own(self) -> bool:
        dev = self.remote_device
        if dev is None:
            return False
        return (dev.remote_id == self.target)

    @property
    def master(self) -> MxrDeviceUid:
        if len(self.payload) < 32:
            return None
        return MxrDeviceUid(self.payload[16:32])

    @property
    def master_dev(self) -> DeviceBase:
        return self.mxr.get_by_uid(self.master)

    def process(self) -> None:
        dev = self.remote_device
        if dev is None:
            return False
        if self.is_own and len(dev.outputs) > 0:
            first_out = dev.outputs[list(dev.outputs.keys())[0]]
            first_out.mirroring = self.master_dev

    def __str__(self) -> str:
        return f"{self.remote_device} mirroring status: {self.master_dev}"
