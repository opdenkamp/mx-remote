from .FrameBase import FrameBase
import struct

class V2IPConfig:
    ''' Single source configuration '''
    def __init__(self, frame:FrameBase, port:int, payload:bytes):
        self.frame = frame
        self.port = port
        self.payload = payload

    def process(self) -> None:
        # register or update this link in the local cache
        pass

    @property
    def serial(self) -> str:
        return self.payload[0:16].split(b'\0',1)[0].decode('ascii')

    @property
    def uid(self) -> [int]:
        return [int.from_bytes(self.payload[16:24], "little"), int.from_bytes(self.payload[24:32], "little"), int.from_bytes(self.payload[32:40], "little"), int.from_bytes(self.payload[40:48], "little")]

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return f"V2IP port {self.port} source {self.serial} uid {self.uid}"
