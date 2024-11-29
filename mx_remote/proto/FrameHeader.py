##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from ..Uid import MxrDeviceUid
from ..Interface import DeviceRegistry

class FrameHeader:
    ''' Header of an mx_remote frame '''
    def __init__(self, mxr:DeviceRegistry, data: bytes, addr: tuple[str, int]):
        self._mxr = mxr
        self.data = data
        self.addr = addr
        if len(data) < 24:
            raise Exception(f'invalid mx_remote frame (length = {len(data)})')
        if (data[0] != 80) or (data[1] != 56):
            raise Exception(f'invalid mx_remote frame (header = {int(data[0])}:{int(data[1])})')

    def construct(mxr:DeviceRegistry, opcode:int, protocol:int=1) -> 'FrameHeader':
        # create a new mx_remote frame for transmission
        pkt = [80, 56, protocol, 0 ]
        pkt.extend(mxr.uid_raw)
        pkt.extend([(opcode & 0xFF), ((opcode >> 8) & 0xFF)])
        pkt.extend([0, 0])
        return FrameHeader(mxr, bytes(pkt), ("", 0))

    @property
    def mxr(self) -> DeviceRegistry:
        return self._mxr

    @property
    def protocol(self) -> int:
        # frame protocol version
        if len(self) < 4:
            return 255
        return (int(self.data[3]) << 8) | int(self.data[2])

    @property
    def remote_id(self) -> MxrDeviceUid:
        # unique id of the device that sent this frame
        return MxrDeviceUid(self.data[4:20])

    @property
    def remote_id_raw(self) -> bytes:
        # unique id of the device that sent this frame
        if len(self) < 20:
            return None
        return self.data[4:20]

    @property
    def opcode(self) -> int:
        # command opcode
        if len(self) < 22:
            return -1
        return (int(self.data[21]) << 8) | int(self.data[20])

    @property
    def payload_len(self) -> int:
        # number of payload bytes
        if len(self) < 24:
            return 0
        return (int(self.data[23]) << 8) | int(self.data[22])

    @property
    def payload(self) -> bytes:
        # frame payload bytes
        if len(self) < 25:
            return None
        return self.data[24:]

    @payload.setter
    def payload(self, val:bytes) -> None:
        data = list(self.data[0:24])
        if (val is None) or (len(val) == 0):
            data[22] = 0
            data[23] = 0
        else:
            l = len(val)
            data[22] = (l & 0xFF)
            data[23] = ((l >> 8) & 0xFF)
            data += val
        self.data = bytes(data)

    def __len__(self) -> int:
        # number of bytes in this frame
        return len(self.data)

    def __str__(self) -> str:
        return f"proto: {self.protocol} op: {self.opcode} len: {self.payload_len}"
