######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for detailed signal status with AV stream information.'''

from enum import IntEnum
from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import BayBase, SignalStatus
from ..Uid import MxrDeviceUid
import struct
from .Svd import SvdMap, Svd
from .Constants import BayStatusMask, MxrSignalType

class VideoColourSpace(IntEnum):
    '''Video colour space encoding format.'''
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
    '''Bitmask indicating which AV detail fields are present in the frame.'''
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
    '''Bitmask of stream characteristics (scrambled, interlaced, 3D, HDR, etc.).'''
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
    '''Parsed video signal details including resolution, colour space, and timing.'''
    def __init__(self, svd:SvdMap, data:bytes) -> None:
        if len(data) != 16:
            raise Exception(f"invalid length: {len(data)}")
        self._svd = svd
        self._data = data

    @property
    def svd(self) -> Svd|None:
        return self._svd.svd[self._data[0]] if self._data[0] != 0 else None

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
        '''Frame rate in Hz (uint16 at offset 8 of av_details_video).'''
        return int.from_bytes(self._data[8:10], "little")

    @property
    def tmds_clock(self) -> int:
        '''TMDS clock rate in Hz (uint32 at offset 10 of av_details_video).'''
        return int.from_bytes(self._data[10:14], "little")

    def __str__(self) -> str:
        return f"{self.svd}, rate {self.frame_rate}, tmds = {self.tmds_clock}"

# av_details wire layout (packed):
#   0..8     av_details_header
#   8..24    avi_infoframe
#   24..40   av_details_audio
#   40..56   av_details_video
#   56..88   av_details_vsync
#   88..100  av_details_hdmi_link_errors (3 x u32)
#   100..112 av_details_bay (u16 portnum, u32 status, mxr_signal_type scaling, u32 clock_rate)
_AV_DETAILS_SIZE = 112

class FrameSignalStatusNew(FrameBase):
    ''' signal status changed

    A report is answered one packet per bay, not one per device: the port
    number in the bay block at the tail is what names the reporting bay, so
    demultiplex on it. Because that block sits behind the vsync and link-error
    tail, a report shorter than the full 112 bytes cannot be attributed to a
    bay at all and is dropped - firmware does the same since commit 88ea427.

    An empty payload is a broadcast request for every device to report; a
    16-byte payload requests a report from the one unit it addresses. '''
    @cached_property
    def signal_header_version(self) -> int:
        if ((pl := self.payload_u16(0)) is not None):
            return pl
        return 0

    @cached_property
    def support_flags(self) -> AvDetailsSupportFlags|None:
        if ((pl := self.payload_u8(2)) is not None):
            return AvDetailsSupportFlags(pl)
        return None

    @cached_property
    def stream_flags(self) -> AvDetailsStreamFlags|None:
        if ((pl := self.payload_u8(3)) is not None):
            return AvDetailsStreamFlags(pl)
        return None

    @cached_property
    def infoframe(self) -> bytes:
        if ((pl := self.payload_idx(8, 24)) is not None):
            return pl
        return bytes()

    @cached_property
    def audio(self) -> bytes:
        if ((pl := self.payload_idx(24, 40)) is not None):
            return pl
        return bytes()

    @cached_property
    def video(self) -> SignalStatusAvDetailsVideo|None:
        if ((pl := self.payload_idx(40, 56)) is not None):
            return SignalStatusAvDetailsVideo(svd=self.mxr.svd_map, data=pl)
        return None

    @cached_property
    def vsync(self) -> bytes:
        if ((pl := self.payload_idx(56, 88)) is not None):
            return pl
        return bytes()

    @cached_property
    def errors(self) -> list[int]:
        if ((pl := self.payload_idx(88, 100)) is not None):
            return [struct.unpack('<L', pl[0:4])[0], struct.unpack('<L', pl[4:8])[0], struct.unpack('<L', pl[8:12])[0]]
        return []

    @cached_property
    def bay_details(self) -> bytes:
        '''av_details_bay block at the tail of the struct; empty on a short report.'''
        if ((pl := self.payload_idx(100, _AV_DETAILS_SIZE)) is not None) and (len(pl) == 12):
            return pl
        return bytes()

    @cached_property
    def port_number(self) -> int:
        details = self.bay_details
        if len(details) < 2:
            return 0xFF
        return (details[1] << 8) | (details[0])

    @cached_property
    def bay_status(self) -> BayStatusMask|None:
        '''Bay status word from the bay block, or None on a short report.'''
        details = self.bay_details
        if len(details) < 6:
            return None
        return BayStatusMask(int.from_bytes(details[2:6], "little"))

    @cached_property
    def scaling(self) -> MxrSignalType|None:
        '''Signal type the bay is scaling to, or None on a short report.'''
        details = self.bay_details
        if len(details) < 8:
            return None
        return MxrSignalType(details[6:8])

    @cached_property
    def clock_rate(self) -> int|None:
        '''Video clock rate in Hz, or None on a short report.'''
        details = self.bay_details
        if len(details) < 12:
            return None
        return int.from_bytes(details[8:12], "little")

    @cached_property
    def bay(self)  -> BayBase|None:
        dev = self.remote_device
        if dev is None:
            return None
        return dev.get_by_portnum(self.port_number)

    @cached_property
    def bay_name(self) -> str:
        bay = self.bay
        return str(bay) if bay is not None else "(Waiting For HELLO)"

    @cached_property
    def stream_detected(self) -> bool:
        return self.support_flags.stream_detected if (self.support_flags is not None) else False

    @cached_property
    def stream_valid(self) -> bool:
        return self.support_flags.stream_valid if (self.support_flags is not None) else False

    @cached_property
    def frame_rate(self) -> float:
        if (self.stream_flags is None) or (self.video is None):
            return 0
        if self.stream_flags.video_non_int_clock:
            return round(self.video.frame_rate * 1000 / 1001, 2)
        return self.video.frame_rate

    def process(self) -> None:
        '''Update the local device cache with detailed signal status.'''
        if (self.payload is None):
            return
        if len(self.payload) < 8:
            # request rather than a report
            return
        if len(self.payload) < _AV_DETAILS_SIZE:
            # the bay block naming the reporting bay sits at the tail, so a
            # shorter report cannot be attributed to a bay
            return
        bay = self.bay
        if bay is None:
            return
        
        if self.stream_valid and (self.video is not None) and (self.video.svd is not None):
            signal_type = f'{self.video.svd.horizontal_active}x{self.video.svd.vertical_active} / {self.video.colour_space} / {self.video.colour_depth}bpp'
            if (self.stream_flags is not None):
                if self.stream_flags.video_interlaced:
                    signal_type += ' interlaced'
                if self.stream_flags.video_hdr:
                    signal_type += ' HDR'
            signal_type += f' / {self.frame_rate}Hz'
        else:
            signal_type = 'No Signal'
        bay.on_mxr_update(SignalStatus(detected=self.stream_valid, description=signal_type))

    def __str__(self) -> str:
        if (self.payload is None):
            return "Unknown"
        if len(self.payload) < 8:
            return "signal status request"
        if len(self.payload) == 16:
            return f"signal status request for {self.uid_to_user_string(self.payload)}"
        if len(self.payload) < _AV_DETAILS_SIZE:
            return f"signal status request len {len(self.payload)}"
        if self.stream_valid:
            return f"{self.bay_name} signal status - {self.video}, errors = {self.errors}"
        if self.stream_detected:
            return f"{self.bay_name} signal status - invalid signal detected"
        return f"{self.bay_name} signal status - no signal"
