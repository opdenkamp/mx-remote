######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################

'''Multiviewer configuration enums and abstract configuration interface.'''

from abc import ABC, abstractmethod
from enum import IntEnum
from ..Uid import MxrDeviceUid

class MultiviewerOpcode(IntEnum):
    '''Opcodes for multiviewer configuration commands.'''
    STATUS            = 0
    VIEW_MODE         = 1
    VIDEO_SOURCE      = 2
    AUDIO_SOURCE      = 3
    AUDIO_VOLUME      = 4
    EDID_TEMPLATE     = 5
    ROUTE_RC          = 6
    PIP_SIZE          = 7
    PIP_POSITION      = 8
    ASPECT            = 9
    AUTO_SWITCH       = 10
    OUTPUT_MODE       = 11
    OUTPUT_ITC_MODE   = 12
    HDCP_MODE         = 13
    CONFIG_SOURCE     = 14
    AUTO_ROUTE        = 15
    UNKNOWN           = 0xFF

class MultiviewerViewMode(IntEnum):
    '''Screen layout modes for the multiviewer output.'''
    UNKNOWN = 0
    SINGLE = 1
    PIP = 2
    TWO_SCREEN_LARGE = 3
    TWO_SCREEN_SMALL = 4
    THREE_SCREEN_LARGE = 5
    THREE_SCREEN_SMALL = 6
    FOUR_SCREEN_LARGE = 7
    FOUR_SCREEN_SMALL = 8

class MultiviewerPipPosition(IntEnum):
    '''Picture-in-picture window position on screen.'''
    UNKNOWN = 0
    LEFT_TOP = 1
    LEFT_BOTTOM = 2
    RIGHT_TOP = 3
    RIGHT_BOTTOM = 4

class MultiviewerPipSize(IntEnum):
    '''Picture-in-picture window size.'''
    UNKNOWN = 0
    SMALL = 1
    MEDIUM = 2
    LARGE = 3

class MultiviewerOutputMode(IntEnum):
    '''Output resolution and refresh rate modes.'''
    UNKNOWN = 0
    OUT_4096x2160P60 = 1
    OUT_4096x2160P50 = 2
    OUT_3840x2160P60 = 3
    OUT_3840x2160P50 = 4
    OUT_3840x2160P30 = 5
    OUT_3840x2160P25 = 6
    OUT_1920x1200P60RB = 7
    OUT_1920x1080P60 = 8
    OUT_1920x1080P50 = 9
    OUT_1360x768P60 = 10
    OUT_1280x800P60 = 11
    OUT_1280x720P60 = 12
    OUT_1280x720P50 = 13
    OUT_1024x768P60 = 14

class MultiviewerHDCPMode(IntEnum):
    '''HDCP content protection version modes.'''
    UNKNOWN = 0
    V1_4 = 1
    V2_2 = 2

class MultiviewerITCMode(IntEnum):
    '''IT Content mode for output signal type.'''
    UNKNOWN = 0
    VIDEO = 1
    PC = 2

class MultiviewerEDIDTemplate(IntEnum):
    '''EDID template presets for input source negotiation.'''
    UNKNOWN = 0
    EDID_4K60_STEREO = 1
    EDID_4K60_51 = 2
    EDID_4K60_71 = 3
    EDID_4K30_STEREO = 4
    EDID_4K30_51 = 5
    EDID_4K30_71 = 6
    EDID_1080P_STEREO = 7
    EDID_1080P_51 = 8
    EDID_1080P_71 = 9
    EDID_1920x1200 = 10
    EDID_1680x1050 = 11
    EDID_1600x1200 = 12
    EDID_1440x900 = 13
    EDID_1360x768 = 14
    EDID_1280x1024 = 15
    EDID_1024x768 = 16
    EDID_720P = 17
    EDID_COPY_OUTPUT = 18
    EDID_CUSTOM = 19

class MultiviewerAspectRatio(IntEnum):
    '''Output aspect ratio modes.'''
    UNKNOWN = 0
    ASPECT_FULL = 1
    ASPECT_16_9 = 2

class MultiviewerBoolSetting(IntEnum):
    '''Boolean on/off setting for multiviewer features.'''
    UNKNOWN = 0xFF
    OFF = 0
    ON = 1

class MultiviewerSource(IntEnum):
    '''Input source selection for multiviewer screens.'''
    UNKNOWN = 0
    SOURCE_1 = 1
    SOURCE_2 = 2
    SOURCE_3 = 3
    SOURCE_4 = 4


class MultiviewerConfig(ABC):
    '''Abstract interface for multiviewer device configuration.'''

    @property
    @abstractmethod
    def uid(self) -> MxrDeviceUid|None:
        pass

    @abstractmethod
    def mapping(self, idx:int) -> MxrDeviceUid|None:
        pass

    @property
    @abstractmethod
    def mappings(self) -> list[MxrDeviceUid|None]:
        pass

    @property
    @abstractmethod
    def mcu_version(self) -> str|None:
        pass

    @property
    @abstractmethod
    def scaler_version(self) -> str|None:
        pass

    @property
    @abstractmethod
    def hw_view_mode(self) -> int|None:
        pass

    @property
    @abstractmethod
    def view_mode(self) -> MultiviewerViewMode:
        pass

    @property
    @abstractmethod
    def pip_position(self) -> MultiviewerPipPosition:
        pass

    @property
    @abstractmethod
    def pip_size(self) -> MultiviewerPipSize:
        pass

    @property
    @abstractmethod
    def output_mode(self) -> MultiviewerOutputMode:
        pass

    @property
    @abstractmethod
    def hdcp_mode(self) -> MultiviewerHDCPMode:
        pass

    @property
    @abstractmethod
    def output_itc_mode(self) -> MultiviewerITCMode:
        pass

    @property
    @abstractmethod
    def edid_template(self) -> MultiviewerEDIDTemplate:
        pass

    @property
    @abstractmethod
    def aspect_ratio(self) -> MultiviewerAspectRatio:
        pass

    @property
    @abstractmethod
    def auto_switch(self) -> MultiviewerBoolSetting:
        pass

    @property
    @abstractmethod
    def audio_source(self) -> MultiviewerSource:
        pass

    @property
    @abstractmethod
    def audio_volume(self) -> int:
        pass

    @property
    @abstractmethod
    def audio_muted(self) -> MultiviewerBoolSetting:
        pass

    @abstractmethod
    def video_source(self, screen:int) -> MultiviewerSource:
        pass

    @property
    @abstractmethod
    def remote_control(self) -> MultiviewerSource:
        pass


class MultiviewerScreenMode(IntEnum):
    '''Hardware screen-mode field.'''
    UNKNOWN = 0
    MODE_1 = 1
    MODE_2 = 2


class MultiviewerHWViewMode(IntEnum):
    '''Hardware view-mode field, distinct from the user-facing MultiviewerViewMode.'''
    UNKNOWN = 0
    SINGLE = 1
    PIP = 2
    TWO = 3
    THREE = 4
    FOUR = 5


_MV_SETTINGS_SIZE = 168
_MV_CONFIG_SIZE = 19


class MultiviewerConfigData:
    '''Writable multiviewer configuration that packs to mxr_multiviewer_config.'''

    __slots__ = (
        "hw_view_mode", "view_mode", "pip_position", "pip_size",
        "output_mode", "hdcp_mode", "output_itc_mode", "edid_template",
        "screen_mode", "screen_aspect", "auto_switch", "audio_source",
        "volume", "muted", "video_sources", "rc_route",
    )

    def __init__(
        self,
        *,
        hw_view_mode: MultiviewerHWViewMode = MultiviewerHWViewMode.SINGLE,
        view_mode: MultiviewerViewMode = MultiviewerViewMode.SINGLE,
        pip_position: MultiviewerPipPosition = MultiviewerPipPosition.LEFT_TOP,
        pip_size: MultiviewerPipSize = MultiviewerPipSize.SMALL,
        output_mode: MultiviewerOutputMode = MultiviewerOutputMode.OUT_3840x2160P60,
        hdcp_mode: MultiviewerHDCPMode = MultiviewerHDCPMode.V1_4,
        output_itc_mode: MultiviewerITCMode = MultiviewerITCMode.VIDEO,
        edid_template: MultiviewerEDIDTemplate = MultiviewerEDIDTemplate.EDID_4K60_STEREO,
        screen_mode: MultiviewerScreenMode = MultiviewerScreenMode.MODE_1,
        screen_aspect: MultiviewerAspectRatio = MultiviewerAspectRatio.ASPECT_FULL,
        auto_switch: bool = False,
        audio_source: int = 0,
        volume: int = 50,
        muted: bool = False,
        video_sources: tuple[int, int, int, int] = (0, 1, 2, 3),
        rc_route: int = 0,
    ) -> None:
        if len(video_sources) != 4:
            raise ValueError("video_sources must have exactly 4 entries")
        if not (0 <= volume <= 100):
            raise ValueError(f"volume out of range: {volume}")
        self.hw_view_mode = MultiviewerHWViewMode(int(hw_view_mode))
        self.view_mode = MultiviewerViewMode(int(view_mode))
        self.pip_position = MultiviewerPipPosition(int(pip_position))
        self.pip_size = MultiviewerPipSize(int(pip_size))
        self.output_mode = MultiviewerOutputMode(int(output_mode))
        self.hdcp_mode = MultiviewerHDCPMode(int(hdcp_mode))
        self.output_itc_mode = MultiviewerITCMode(int(output_itc_mode))
        self.edid_template = MultiviewerEDIDTemplate(int(edid_template))
        self.screen_mode = MultiviewerScreenMode(int(screen_mode))
        self.screen_aspect = MultiviewerAspectRatio(int(screen_aspect))
        self.auto_switch = bool(auto_switch)
        self.audio_source = int(audio_source) & 0xFF
        self.volume = int(volume) & 0xFF
        self.muted = bool(muted)
        self.video_sources = tuple(int(s) & 0xFF for s in video_sources)
        self.rc_route = int(rc_route) & 0xFF

    def pack(self) -> bytes:
        '''Return the 18-byte wire encoding.'''
        out = bytes([
            int(self.hw_view_mode) & 0xFF,
            int(self.view_mode) & 0xFF,
            int(self.pip_position) & 0xFF,
            int(self.pip_size) & 0xFF,
            int(self.output_mode) & 0xFF,
            int(self.hdcp_mode) & 0xFF,
            int(self.output_itc_mode) & 0xFF,
            int(self.edid_template) & 0xFF,
            int(self.screen_mode) & 0xFF,
            int(self.screen_aspect) & 0xFF,
            1 if self.auto_switch else 0,
            self.audio_source,
            self.volume,
            1 if self.muted else 0,
            self.video_sources[0], self.video_sources[1],
            self.video_sources[2], self.video_sources[3],
            self.rc_route,
        ])
        if len(out) != _MV_CONFIG_SIZE:
            raise AssertionError(f"config block must be {_MV_CONFIG_SIZE} bytes, got {len(out)}")
        return out


def pack_multiviewer_settings(
    *,
    uid: bytes,
    mappings: list[bytes] | tuple[bytes, ...] = (b"\x00" * 16,) * 4,
    fw_mcu: str = "",
    fw_scaler: str = "",
    config: MultiviewerConfigData | None = None,
) -> bytes:
    '''Pack a 168-byte mxr_multiviewer_settings struct.

    Trailing 6 bytes of zero pad bring the natural 162-byte content up to
    the C sizeof of 168 (ALIGN(8)); receivers walk arrays by sizeof.'''
    if len(uid) != 16:
        raise ValueError("uid must be 16 bytes")
    if len(mappings) != 4:
        raise ValueError("mappings must have 4 entries")
    for i, m in enumerate(mappings):
        if len(m) != 16:
            raise ValueError(f"mapping {i} must be 16 bytes, got {len(m)}")
    fw_mcu_b = fw_mcu.encode("ascii", errors="replace")[:32]
    fw_scaler_b = fw_scaler.encode("ascii", errors="replace")[:32]
    cfg = (config or MultiviewerConfigData()).pack()
    out = (
        uid
        + b"".join(mappings)
        + fw_mcu_b + b"\x00" * (32 - len(fw_mcu_b))
        + fw_scaler_b + b"\x00" * (32 - len(fw_scaler_b))
        + cfg
        + b"\x00" * 5
    )
    if len(out) != _MV_SETTINGS_SIZE:
        raise AssertionError(f"settings must be {_MV_SETTINGS_SIZE} bytes, got {len(out)}")
    return out
