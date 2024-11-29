##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Uid import MxrDeviceUid

class FrameFilterStatus(FrameBase):
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    @property
    def filtered(self) -> list[MxrDeviceUid]:
        filtered = []
        data = self.payload[16:]
        while len(data) >= 16:
            filtered.append(MxrDeviceUid(data[0:16]))
            data = data[16:]
        return filtered

    @property
    def target_uid(self) -> MxrDeviceUid:
        return MxrDeviceUid(self.payload[0:16])

    def process(self) -> None:
        dev = self.remote_device
        if dev is None:
            return
        if len (dev.outputs) < 1:
            return
        first_out = dev.outputs[list(dev.outputs.keys())[0]]
        first_out.filtered = self.filtered

    def __str__(self) -> str:
        return f"bay filter status: {len(self.filtered)} sources filtered"
