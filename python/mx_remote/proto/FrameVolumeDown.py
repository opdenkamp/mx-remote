from .FrameBase import FrameBase
from .FrameHeader import FrameHeader

class FrameVolumeDown(FrameBase):
    ''' volume down pressed frame '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    @property
    def bay(self):
        portnum = self.payload[0]
        dev = self.remote_device
        if dev is None:
            return
        return dev.get_by_portnum(portnum)

    def process(self):
        pass

    def __str__(self):
        return "volume down bay:".format(str(self.bay))
