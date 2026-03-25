from abc import ABC, abstractmethod
from enum import IntEnum
from ..Uid import MxrDeviceUid

class MultiviewerOpcode(IntEnum):
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
    UNKNOWN = 0
    LEFT_TOP = 1
    LEFT_BOTTOM = 2
    RIGHT_TOP = 3
    RIGHT_BOTTOM = 4

class MultiviewerPipSize(IntEnum):
    UNKNOWN = 0
    SMALL = 1
    MEDIUM = 2
    LARGE = 3

class MultiviewerOutputMode(IntEnum):
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
    UNKNOWN = 0
    V1_4 = 1
    V2_2 = 2

class MultiviewerITCMode(IntEnum):
    UNKNOWN = 0
    VIDEO = 1
    PC = 2

class MultiviewerEDIDTemplate(IntEnum):
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
    UNKNOWN = 0
    ASPECT_FULL = 1
    ASPECT_16_9 = 2

class MultiviewerBoolSetting(IntEnum):
    UNKNOWN = 0xFF
    OFF = 0
    ON = 1

class MultiviewerSource(IntEnum):
    UNKNOWN = 0
    SOURCE_1 = 1
    SOURCE_2 = 2
    SOURCE_3 = 3
    SOURCE_4 = 4


class MultiviewerConfig(ABC):
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
