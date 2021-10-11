from typing import Tuple

class FrameHeader:
    ''' Header of an mx_remote frame '''
    def __init__(self, mxr:'mx_remote.Remote.Remote', data: bytes, addr: Tuple[str, int]):
        self.mxr = mxr
        self.data = data
        self.addr = addr
        p8hdr = data[0:2].decode('ascii')
        if p8hdr != 'P8':
            raise Exception('invalid mx_remote frame')

    @property
    def protocol(self) -> int:
        # frame protocol version
        if len(self) < 4:
            return 255
        return (int(self.data[3]) << 8) | int(self.data[2])

    @property
    def remote_id(self) -> str:
        # unique id of the device that sent this frame
        if len(self) < 20:
            return 'Unknown'
        return ''.join('%02x'%i for i in reversed(self.data[4:8])) + \
                ''.join('%02x'%i for i in reversed(self.data[8:12])) + \
                ''.join('%02x'%i for i in reversed(self.data[12:16])) + \
                ''.join('%02x'%i for i in reversed(self.data[16:20]))

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
            return 255
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

    def __len__(self) -> int:
        # number of bytes in this frame
        return len(self.data)

    def __str__(self) -> str:
        return "proto: {} op: {} len: {}".format(str(self.protocol), str(self.opcode), str(self.payload_len))
