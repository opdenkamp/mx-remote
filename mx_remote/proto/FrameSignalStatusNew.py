##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from enum import Enum
from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import BayBase
from ..Uid import MxrDeviceUid
import struct
from .Svd import SvdMap, Svd

SVD = SvdMap()

class VideoColourSpace(Enum):
    RGB = 0
    YUV444 = 1
    YUV422 = 2
    YUV420 = 3

    def __str__(self) -> str:
        if self.value == 0:
            return 'RGB'
        if self.value == 1:
            return '4:4:4'
        if self.value == 2:
            return '4:2:2'
        if self.value == 3:
            return '4:2:0'
        return 'unknown'

class AvDetailsSupportFlags:
    def __init__(self, data:int) -> None:
        self.data = data & 0xFF

    @property
    def stream_detected(self) -> bool:
        return (self.data & (1 << 0) != 0)

    @property
    def stream_valid(self) -> bool:
        return (self.data & (1 << 1) != 0)

    @property
    def have_colour_depth(self) -> bool:
        return (self.data & (1 << 2) != 0)

    @property
    def have_avi_infoframe(self) -> bool:
        return (self.data & (1 << 3) != 0)

    @property
    def have_audio_infoframe(self) -> bool:
        return (self.data & (1 << 4) != 0)

    @property
    def have_audio_details(self) -> bool:
        return (self.data & (1 << 5) != 0)

    @property
    def have_video_details(self) -> bool:
        return (self.data & (1 << 6) != 0)

    @property
    def have_link_errors(self) -> bool:
        return (self.data & (1 << 7) != 0)

class AvDetailsStreamFlags:
    def __init__(self, data:int) -> None:
        self.data = data & 0xFF

    @property
    def video_scrambled(self) -> bool:
        return (self.data & (1 << 0) != 0)

    @property
    def video_interlaced(self) -> bool:
        return (self.data & (1 << 1) != 0)

    @property
    def video_3d(self) -> bool:
        return (self.data & (1 << 2) != 0)

    @property
    def video_non_int_clock(self) -> bool:
        return (self.data & (1 << 3) != 0)

    @property
    def video_hdr(self) -> bool:
        return (self.data & (1 << 4) != 0)

    @property
    def avmute_set(self) -> bool:
        return (self.data & (1 << 5) != 0)

    @property
    def avmute_clear(self) -> bool:
        return (self.data & (1 << 6) != 0)

    @property
    def reserved(self) -> bool:
        return (self.data & (1 << 7) != 0)

class SignalStatusAvDetailsVideo:
    def __init__(self, data:bytes) -> None:
        if len(data) != 16:
            raise Exception(f"invalid length: {len(data)}")
        self._data = data

    @property
    def svd(self) -> Svd:
        return SVD.svd[self._data[0]] if self._data[0] != 0 else None

    @property
    def colour_space(self) -> VideoColourSpace:
        return VideoColourSpace(self._data[1])

    @property
    def colour_depth(self) -> int:
        return self._data[2]

    @property
    def pixels_per_clock(self) -> int:
        return self._data[3]

    @property
    def aspect_ratio(self) -> int:
        return self._data[4]

    @property
    def format_3d(self) -> int:
        return self._data[5]

    @property
    def samping_3d(self) -> int:
        return self._data[6]

    @property
    def samping_position(self) -> int:
        return self._data[7]

    @property
    def frame_rate(self) -> int:
        return int.from_bytes(self._data[8:9], "little")

    @property
    def tmds_clock(self) -> int:
        return int.from_bytes(self._data[10:13], "little")

    def __str__(self) -> str:
        return f"{self.svd}, rate {self.frame_rate}, tmds = {self.tmds_clock}"

class FrameSignalStatusNew(FrameBase):
    ''' signal status changed '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    @property
    def signal_header(self) -> bytes:
        return self.payload[0:8]

    @property
    def signal_header_version(self) -> int:
        if len(self.payload) < 8:
            return 0
        return int(self.signal_header[1]) << 8 | int(self.signal_header[0])

    @property
    def support_flags(self) -> AvDetailsSupportFlags:
        if len(self.payload) < 8:
            return 0
        return AvDetailsSupportFlags(self.signal_header[2])

    @property
    def stream_flags(self) -> AvDetailsStreamFlags:
        if len(self.payload) < 8:
            return 0
        return AvDetailsStreamFlags(self.signal_header[3])

    @property
    def infoframe(self) -> bytes:
        if len(self.payload) < 24:
            return bytes()
        return self.payload[8:24]

    @property
    def audio(self) -> bytes:
        if len(self.payload) < 40:
            return bytes()
        return self.payload[24:40]

    @property
    def video(self) -> SignalStatusAvDetailsVideo:
        if len(self.payload) < 56:
            return None
        return SignalStatusAvDetailsVideo(self.payload[40:56])

    @property
    def vsync(self) -> bytes:
        if len(self.payload) < 88:
            return bytes()
        return self.payload[56:88]

    @property
    def errors(self) -> bytes:
        if len(self.payload) < 100:
            return bytes()
        pl = self.payload[88:100]
        return [struct.unpack('<L', pl[0:4])[0], struct.unpack('<L', pl[4:8])[0], struct.unpack('<L', pl[8:12])[0]]

    @property
    def bay_details(self) -> bytes:
        if len(self.payload) < 112:
            return bytes()
        return self.payload[100:112]

    @property
    def port_number(self) -> int:
        if len(self.payload) < 8:
            return 0xFF
        #return struct.unpack('<L', self.payload[57:61])[0]
        return (self.bay_details[1] << 8) | (self.bay_details[0])

    @property
    def bay(self)  -> BayBase:
        dev = self.remote_device
        if dev is None:
            return None
        return dev.get_by_portnum(self.port_number)

    @property
    def bay_name(self) -> str:
        bay = self.bay
        return str(bay) if bay is not None else "(Waiting For HELLO)"

    @property
    def stream_detected(self) -> bool:
        return self.support_flags.stream_detected

    @property
    def stream_valid(self) -> bool:
        return self.support_flags.stream_valid

    @property
    def frame_rate(self) -> float:
        if self.stream_flags.video_non_int_clock:
            return round(self.video.frame_rate * 1000 / 1001, 2)
        return self.video.frame_rate

    def process(self) -> None:
        if len(self.payload) < 8:
            return
        if len(self.payload) < 112:
            return
        # update the local cache
        bay = self.bay
        if bay is None:
            return
        bay.signal_detected = self.stream_valid
        if self.stream_valid:
            signal_type = f'{self.video.svd.horizontal_active}x{self.video.svd.vertical_active} / {self.video.colour_space} / {self.video.colour_depth}bpp'
            if self.stream_flags.video_interlaced:
                signal_type += ' interlaced'
            if self.stream_flags.video_hdr:
                signal_type += ' HDR'
            signal_type += f' / {self.frame_rate}Hz'
            bay.signal_type = signal_type
        else:
            bay.signal_type = 'No Signal'

    def __str__(self) -> str:
        if len(self.payload) < 8:
            return "signal status request"
        if len(self.payload) == 16:
            return f"signal status request for {MxrDeviceUid(self.payload)}"
        if len(self.payload) < 112:
            return f"signal status request len {len(self.payload)}"
        if self.stream_valid:
            return f"{self.bay_name} signal status - {self.video}, errors = {self.errors}"
        if self.stream_detected:
            return f"{self.bay_name} signal status - invalid signal detected"
        return f"{self.bay_name} signal status - no signal"
