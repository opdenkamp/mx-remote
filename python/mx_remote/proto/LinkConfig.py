from .FrameBase import FrameBase
import struct

class LinkConfig:
    ''' Single link configuration '''
    def __init__(self, frame:FrameBase, payload:bytes):
        self.frame = frame
        self.payload = payload

    @property
    def remote_device(self) -> 'mx_remote.remote.Device.Device':
        # device instance of the device that sent this frame
        return self.frame.remote_device

    @property
    def remote_port(self) -> int:
        # remote port number
        return int(self.payload[0])

    @property
    def remote_bay(self) -> 'mx_remote.remote.Bay.Bay':
        # bay instance of the bay that sent this link configuration
        dev = self.remote_device
        if dev is None:
            return
        return dev.get_by_portnum(self.remote_port)

    @property
    def auto_config(self) -> bool:
        # auto-configuration enabled
        return (int(self.payload[1]) == 1)

    @property
    def linked_serial(self) -> str:
        # serial number of the device linked to this bay, or an empty string if not linked
        return self.payload[2:18].split(b'\0',1)[0].decode('ascii')

    @property
    def linked_bay_name(self) -> str:
        # name of the bay linked to this bay, or an empty string if not linked
        return self.payload[18:34].split(b'\0',1)[0].decode('ascii')

    @property
    def features(self) -> int:
        # supported features bitmask for this link
        return struct.unpack('<L', self.payload[34:38])[0]

    @property
    def is_linked(self) -> bool:
        # bay linked or not
        return (len(self.linked_serial) != 0) and (len(self.linked_bay_name) != 0)

    @property
    def linked_device(self) -> 'mx_remote.remote.Device.Device':
        # device instance of the device that's linked to this bay
        if not self.is_linked:
            return None
        return self.frame.mxr.get_by_serial(self.linked_serial)

    @property
    def linked_bay(self) -> 'mx_remote.remote.Bay.Bay':
        # bay instance of the bay that's linked to this bay
        dev = self.linked_device
        if dev is None:
            return None
        return dev.get_by_portname(self.linked_bay_name)

    def process(self) -> None:
        # register or update this link in the local cache
        bay = self.remote_bay
        if bay is None:
            return

        bay.on_mxr_link_config(self)
        otherbay = self.linked_bay
        if otherbay is not None and otherbay.link is not None:
            bay.on_mxr_link_config(self)
            return

    def __str__(self) -> str:
        if not self.is_linked:
            return "{} not linked".format(str(self.remote_bay))
        return "{} link serial:{} remote bay:{} features:{}".format(str(self.remote_bay), self.linked_serial, self.linked_bay_name, str(self.features))
