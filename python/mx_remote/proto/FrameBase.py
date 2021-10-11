from .FrameHeader import FrameHeader

class FrameBase:
    ''' Base class for decoded mx_remote frames '''
    def __init__(self, header:FrameHeader):
        self.header = header

    @property
    def mxr(self) -> 'mx_remote.Remote.Remote':
        # remote instance
        return self.header.mxr

    @property
    def address(self) -> str:
        # address that sent this frame
        (addr, _) = self.header.addr
        return addr

    @property
    def protocol(self) -> int:
        # frame protocol version
        return self.header.protocol

    @property
    def remote_id(self) -> str:
        # unique id of the device that sent this frame
        return self.header.remote_id

    @property
    def remote_device(self) -> 'mx_remote.remote.Device.Device':
        # device instance for the device that sent this frame
        return self.mxr.get(self.remote_id)

    @property
    def payload(self) -> bytes:
        # frame payload bytes
        return self.header.payload

    def process(self) -> None:
        # update the local cache with the new data that was received in this frame
        pass

    def __len__(self) -> int:
        # number of payload bytes
        return self.header.payload_len

    def __str__(self) -> str:
        return "unknown frame"
