from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from .const import RCKey

class FrameRCKey(FrameBase):
    ''' power status changed of a device connected to a bay '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)
        self.dev = None

    @property
    def bay(self) -> 'mx_remote.remote.Bay.Bay':
        # bay that received the key press
        portnum = self.payload[0]
        dev = self.remote_device
        if dev is None:
            return
        return dev.get_by_portnum(portnum)

    @property
    def key(self) -> RCKey:
        # key that was received
        return RCKey((int(self.payload[2]) << 8) | int(self.payload[1]))

    def process(self) -> None:
        bay = self.bay
        if bay is not None:
            bay.on_key_pressed(self.key)

    def __str__(self) -> str:
        return "{} key pressed: {}".format(str(self.bay), repr(self.key))
