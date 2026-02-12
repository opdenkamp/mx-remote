##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from enum import Enum
from typing import Any

MXR_PROTOCOL_VERSION = 20

MXR_DEVICE_FEATURE_IR_RX              = (1 << 0)
MXR_DEVICE_FEATURE_IR_TX              = (1 << 1)
MXR_DEVICE_FEATURE_CEC                = (1 << 2)
MXR_DEVICE_FEATURE_V2IP_SOURCE        = (1 << 3)
MXR_DEVICE_FEATURE_V2IP_SINK          = (1 << 4)
MXR_DEVICE_FEATURE_VIDEO_ROUTING      = (1 << 5)
MXR_DEVICE_FEATURE_AUDIO_ROUTING      = (1 << 6)
MXR_DEVICE_FEATURE_VOLUME_CONTROL     = (1 << 7)
MXR_DEVICE_FEATURE_AUDIO_RETURN       = (1 << 8)
MXR_DEVICE_FEATURE_REMOTE_CONTROL     = (1 << 9)
MXR_DEVICE_FEATURE_SETUP_COMPLETED    = (1 << 10)
MXR_DEVICE_FEATURE_MESH_MASTER        = (1 << 11)
MXR_DEVICE_FEATURE_STATUS_NOTIFY      = (1 << 12)
MXR_DEVICE_FEATURE_STATUS_WARNING     = (1 << 13)
MXR_DEVICE_FEATURE_STATUS_ERROR       = (1 << 14)
MXR_DEVICE_FEATURE_STATUS_REBOOTING   = (1 << 15)
MXR_DEVICE_FEATURE_MESH_MEMBER        = (1 << 16)
MXR_DEVICE_FEATURE_AUDIO_AMPLIFIER    = (1 << 17)
MXR_DEVICE_FEATURE_BOOTING            = (1 << 18)
MXR_DEVICE_FEATURE_MANAGER            = (1 << 19)
MXR_DEVICE_FEATURE_STATUS_POWER_SAVE  = (1 << 20)
MXR_DEVICE_FEATURE_MESH               = (1 << 21)
MXR_DEVICE_FEATURE_MULTIVIEWER        = (1 << 22)
MXR_DEVICE_FEATURE_STATUS_CRASHED     = (1 << 23)
MXR_DEVICE_FEATURE_BOOT_BIT           = (1 << 31)

MX_BAY_FEATURE_HDMI_OUT           = (1 << 0)
MX_BAY_FEATURE_HDMI_IN            = (1 << 1)
MX_BAY_FEATURE_AUDIO_DIG_OUT      = (1 << 2)
MX_BAY_FEATURE_AUDIO_DIG_IN       = (1 << 3)
MX_BAY_FEATURE_AUDIO_ANA_OUT      = (1 << 4)
MX_BAY_FEATURE_AUDIO_ANA_IN       = (1 << 5)
MX_BAY_FEATURE_IR_IN              = (1 << 6)
MX_BAY_FEATURE_IR_OUT             = (1 << 7)
MX_BAY_FEATURE_AUDIO_AMP_OUT      = (1 << 8)
MX_BAY_FEATURE_RC_OUT             = (1 << 9)
MX_BAY_FEATURE_RC_IN              = (1 << 10)
MX_BAY_FEATURE_DOLBY              = (1 << 11)
MX_BAY_FEATURE_AUTO_OFF           = (1 << 12)
MX_BAY_FEATURE_V2IP_SOURCE_REMOTE = (1 << 13)
MX_BAY_FEATURE_V2IP_SINK_REMOTE   = (1 << 14)
MX_BAY_FEATURE_V2IP_SOURCE_LOCAL  = (1 << 15)
MX_BAY_FEATURE_V2IP_SINK_LOCAL    = (1 << 16)
MX_BAY_FEATURE_DOLBY_IN_POS       = 24

MX_LINK_FEATURE_NONE          = 0
MX_LINK_FEATURE_VIDEO_HDMI    = (1 << 0)
MX_LINK_FEATURE_AUDIO_OPTICAL = (1 << 1)
MX_LINK_FEATURE_AUDIO_ANALOG  = (1 << 2)
MX_LINK_FEATURE_IR            = (1 << 3)
MX_LINK_FEATURE_RC            = (1 << 4)

class RCAction(Enum):
	ACTION_POWER_TOGGLE 	= 0
	ACTION_POWER_ON			= 1
	ACTION_POWER_OFF		= 2
	ACTION_VOLUME_DOWN		= 3
	ACTION_VOLUME_UP		= 4
	ACTION_VOLUME_MUTE		= 5

class RCKey(Enum):
    KEY_0                = 0
    KEY_1                = 1
    KEY_2                = 2
    KEY_3                = 3
    KEY_4                = 4
    KEY_5                = 5
    KEY_6                = 6
    KEY_7                = 7
    KEY_8                = 8
    KEY_9                = 9
    KEY_SELECT           = 10
    KEY_BACK             = 11
    KEY_UP               = 12
    KEY_DOWN             = 13
    KEY_LEFT             = 14
    KEY_RIGHT            = 15
    KEY_MENU             = 16
    KEY_CONTENT_MENU     = 17
    KEY_CHANNEL_UP       = 18
    KEY_CHANNEL_DOWN     = 19
    KEY_PLAY             = 20
    KEY_PAUSE            = 21
    KEY_STOP             = 22
    KEY_RECORD           = 23
    KEY_FAST_FORWARD     = 24
    KEY_REWIND           = 25
    KEY_RED              = 26
    KEY_GREEN            = 27
    KEY_YELLOW           = 28
    KEY_BLUE             = 29
    KEY_HELP             = 30
    KEY_INFORMATION      = 31
    KEY_TEXT             = 32
    KEY_GUIDE            = 33
    KEY_VIDEO_ON_DEMAND  = 34
    KEY_PREVIOUS_CHANNEL = 80
    KEY_3D_MODE          = 81
    KEY_SUBTITLE         = 82
    KEY_SOUND_SELECT     = 83
    KEY_INPUT_SELECT     = 84
    KEY_EJECT            = 85
    KEY_NEXT_CHAPTER     = 86
    KEY_PREVIOUS_CHAPTER = 87
    KEY_CUSTOM_CEC       = 1280
    KEY_INTERACTIVE      = 128
    KEY_SEARCH           = 129
    KEY_SKY              = 130
    KEY_CUSTOM_SKY       = 2048

class BayFeaturesMask:
	HDMI_OUT           = (1 << 0)
	HDMI_IN            = (1 << 1)
	AUDIO_DIG_OUT      = (1 << 2)
	AUDIO_DIG_IN       = (1 << 3)
	AUDIO_ANA_OUT      = (1 << 4)
	AUDIO_ANA_IN       = (1 << 5)
	IR_IN              = (1 << 6)
	IR_OUT             = (1 << 7)
	AUDIO_AMP_OUT      = (1 << 8)
	RC_OUT             = (1 << 9)
	RC_IN              = (1 << 10)
	DOLBY              = (1 << 11)
	AUTO_OFF           = (1 << 12)
	V2IP_SOURCE_REMOTE = (1 << 13)
	V2IP_SINK_REMOTE   = (1 << 14)
	V2IP_SOURCE_LOCAL  = (1 << 15)
	V2IP_SINK_LOCAL    = (1 << 16)
	DOLBY_IN_POS       = 24

	def __init__(self, mask:int):
		self._mask = mask

	def toJson(self):
		return '{' + f'"features":"{self._mask}"' + '}'

	@property
	def mask(self) -> int:
		return self._mask

	@property
	def hdmi_out(self) -> bool:
		return (self._mask & self.HDMI_OUT) != 0

	@property
	def hdmi_in(self) -> bool:
		return (self._mask & self.HDMI_IN) != 0

	@property
	def audio_digital_out(self) -> bool:
		return (self._mask & self.AUDIO_DIG_OUT) != 0

	@property
	def audio_digital_in(self) -> bool:
		return (self._mask & self.AUDIO_DIG_IN) != 0

	@property
	def audio_analog_in(self) -> bool:
		return (self._mask & self.AUDIO_ANA_IN) != 0

	@property
	def audio_analog_out(self) -> bool:
		return (self._mask & self.AUDIO_ANA_OUT) != 0

	@property
	def audio_amp_out(self) -> bool:
		return (self._mask & self.AUDIO_AMP_OUT) != 0

	@property
	def ir_in(self) -> bool:
		return (self._mask & self.IR_IN) != 0

	@property
	def ir_out(self) -> bool:
		return (self._mask & self.IR_OUT) != 0

	@property
	def rc_out(self) -> bool:
		return (self._mask & self.RC_OUT) != 0

	@property
	def rc_in(self) -> bool:
		return (self._mask & self.RC_IN) != 0

	@property
	def dolby(self) -> bool:
		return (self._mask & self.DOLBY) != 0

	@property
	def auto_off(self) -> bool:
		return (self._mask & self.AUTO_OFF) != 0

	@property
	def v2ip_source_remote(self) -> bool:
		return (self._mask & self.V2IP_SOURCE_REMOTE) != 0

	@property
	def v2ip_source_local(self) -> bool:
		return (self._mask & self.V2IP_SOURCE_LOCAL) != 0

	@property
	def v2ip_sink_remote(self) -> bool:
		return (self._mask & self.V2IP_SINK_REMOTE) != 0

	@property
	def v2ip_sink_local(self) -> bool:
		return (self._mask & self.V2IP_SINK_LOCAL) != 0

	def __eq__(self, mask:Any) -> bool:
		if isinstance(mask, int):
			return self._mask == mask
		if isinstance(mask, BayFeaturesMask):
			return self._mask == mask._mask
		return False

	def __ne__(self, mask:Any) -> bool:
		return not (self == mask)

	def __str__(self) -> str:
		rv = ""
		if self.hdmi_in:
			rv += ", HDMI input"
		if self.hdmi_out:
			rv += ", HDMI output"
		if self.audio_digital_out:
			rv += ", digital audio output"
		if self.audio_digital_in:
			rv += ", digital audio input"
		if self.audio_analog_out:
			rv += ", analog audio output"
		if self.audio_analog_in:
			rv += ", analog audio input"
		if self.audio_amp_out:
			rv += ", amplifier audio output"
		if self.dolby:
			rv += ", Dolby"
		if self.ir_in:
			rv += ", IR input"
		if self.ir_out:
			rv += ", IR output"
		if self.rc_in:
			rv += ", remote control input"
		if self.rc_out:
			rv += ", remote control output"
		if self.auto_off:
			rv += ", auto standby"
		if self.v2ip_source_remote:
			rv += ", V2IP remote source"
		if self.v2ip_sink_remote:
			rv += ", V2IP remote sink"
		if self.v2ip_source_local:
			rv += ", V2IP local source"
		if self.v2ip_sink_local:
			rv += ", V2IP local sink"

		if (len(rv) != 0):
			return rv[2:]
		return "none"

	def __repr__(self) -> str:
		return str(self)

class BayStatusMask:
	FAULT = (1 << 0)
	HIDDEN = (1 << 1)
	POWERED = (1 << 2)
	SIGNAL_DETECTED = (1 << 3)
	HPD_DETECTED = (1 << 4)
	SIGNAL_SCRAMBLED =(1 << 5)
	HDBT_CONNECTED = (1 << 6)
	CEC_DETECTED = (1 << 7)
	POWERED_ON = (1 << 8)
	POWERED_OFF = (1 << 9)
	AUDIO_ARC_HDMI = (1 << 10)
	AUDIO_ARC_OPTICAL = (1 << 11)
	AUDIO_ARC_ANALOG = (1 << 12)
	OFFLINE = (1 << 13)
	DECODER_DISABLED = (1 << 14)
	ENCODER_DISABLED = (1 << 15)

	def __init__(self, mask:int):
		self._mask = mask

	@property
	def mask(self) -> int:
		return self._mask

	@property
	def fault(self) -> bool:
		# bay is faulty
		return (self._mask & self.FAULT) != 0

	@property
	def hidden(self) -> bool:
		# bay is hidden
		return (self._mask & self.HIDDEN) != 0

	@property
	def powered(self) -> bool:
		# PoE powered on
		return (self._mask & self.POWERED) != 0

	@property
	def signal_detected(self) -> bool:
		# signal detected
		return (self._mask & self.SIGNAL_DETECTED) != 0

	@property
	def hpd_detected(self) -> bool:
		# hotplug detected
		return (self._mask & self.HPD_DETECTED) != 0

	@property
	def hdbt_connected(self) -> bool:
		# HDBaseT connected
		return (self._mask & self.HDBT_CONNECTED) != 0

	@property
	def cec_detected(self) -> bool:
		# CEC capable device connected to this bay
		return (self._mask & self.CEC_DETECTED) != 0

	@property
	def powered_on(self) -> bool:
		# device is powered on
		return (self._mask & self.POWERED_ON) != 0

	@property
	def powered_off(self) -> bool:
		# device is powered off
		return (self._mask & self.POWERED_OFF) != 0

	@property
	def audio_arc_hdmi(self) -> bool:
		# HDMI ARC active
		return (self._mask & self.AUDIO_ARC_HDMI) != 0

	@property
	def audio_arc_optical(self) -> bool:
		# optical ARC active
		return (self._mask & self.AUDIO_ARC_OPTICAL) != 0

	@property
	def audio_arc_analog(self) -> bool:
		# analog ARC active
		return (self._mask & self.AUDIO_ARC_ANALOG) != 0

	@property
	def offline(self) -> bool:
		# v2ip unit offline
		return (self._mask & self.OFFLINE) != 0

	@property
	def decoder_disabled(self) -> bool:
		# v2ip decoder disabled
		return (self._mask & self.DECODER_DISABLED) != 0

	@property
	def encoder_disabled(self) -> bool:
		# v2ip decoder disabled
		return (self._mask & self.ENCODER_DISABLED) != 0

	def __str__(self) -> str:
		rv = ""
		if self.fault:
			rv += ", fault detected"
		if self.hidden:
			rv += ", hidden"
		if self.powered:
			rv += ", power enabled"
		if self.signal_detected:
			rv += ", signal detected"
		if self.hpd_detected:
			rv += ", hpd detected"
		if self.hdbt_connected:
			rv += ", hdbt link"
		if self.cec_detected:
			rv += ", cec detected"
		if self.powered_on:
			rv += ", remote powered on"
		if self.powered_off:
			rv += ", remote powered off"
		if self.audio_arc_hdmi:
			rv += ", hdmi arc"
		if self.audio_arc_optical:
			rv += ", optical arc"
		if self.audio_arc_analog:
			rv += ", analog arc"
		if self.offline:
			rv += ", offline"
		if self.decoder_disabled:
			rv += ", decoder disabled"
		if self.encoder_disabled:
			rv += ", encoder disabled"
		if len(rv) != 0:
			return rv[2:]
		return "none"

	def __eq__(self, mask:Any) -> bool:
		if isinstance(mask, int):
			return self._mask == mask
		if isinstance(mask, BayStatusMask):
			return self._mask == mask._mask
		return False

	def __ne__(self, mask:Any) -> bool:
		return not (self == mask)

class RCType(Enum):
	IR = 0
	CEC = 1
	SKY_UK = 2
	TIVO = 3
	KODI = 4
	DISH = 5
	DIRECTV = 6
	MX_REMOTE = 7

	def __str__(self) -> str:
		if self.value == RCType.IR.value:
			return "IR"
		if self.value == RCType.CEC.value:
			return "CEC"
		if self.value == RCType.SKY_UK.value:
			return "Sky"
		if self.value == RCType.TIVO.value:
			return "TiVo"
		if self.value == RCType.KODI.value:
			return "Kodi"
		if self.value == RCType.DISH.value:
			return "Dish"
		if self.value == RCType.DIRECTV.value:
			return "DirecTV"
		if self.value == RCType.MX_REMOTE.value:
			return "MX-Remote"
		return "Unknown"

	def values() -> dict[int, str]:
		rv:dict[int, str] = {}
		for val in range(8):
			rv[val] = str(RCType(val))
		return rv

class EdidProfile(Enum):
	def __str__(self) -> str:
		if self.value == EdidProfile.TEMPLATE_1080P_STEREO.value:
			return '1080p stereo'
		if self.value == EdidProfile.FIXED.value:
			return 'fixed'
		if self.value == EdidProfile.TEMPLATE_4K.value:
			return '4K'
		if self.value == EdidProfile.TEMPLATE_1080P_5_1.value:
			return '1080p 5.1'
		if self.value == EdidProfile.TEMPLATE_720P.value:
			return '720p'
		if self.value == EdidProfile.TEMPLATE_1080P_7_1.value:
			return '1080p 7.1'
		if self.value == EdidProfile.TEMPLATE_4K_HDR_STEREO.value:
			return '4K HDR Stereo'
		if self.value == EdidProfile.TEMPLATE_4K_HDR_7_1.value:
			return '4K HDR 7.1'
		if self.value == EdidProfile.TEMPLATE_4K_HDR_AVR_ONLY.value:
			return '4K HDR AVR'
		if self.value == EdidProfile.LOWEST_COMMON_DENOMINATOR.value:
			return 'lowest common denominator'
		if self.value == EdidProfile.LOWEST_COMMON_DENOMINATOR_ALL.value:
			return 'lowest common denominator (all sinks)'
		if self.value == EdidProfile.TEMPLATE_4K_HDR_ATMOS.value:
			return '4K HDR Dolby Atmos'
		if (self.value >= EdidProfile.SINK_1.value) and (self.value <= EdidProfile.SINK_32.value):
			return f'copy from sink #{self.value - EdidProfile.SINK_1.value + 1}'
		return f"custom #{self.value}"

	TEMPLATE_1080P_STEREO = 0
	FIXED = 1
	TEMPLATE_4K = 2
	TEMPLATE_1080P_5_1 = 3
	TEMPLATE_720P = 4
	TEMPLATE_1080P_7_1 = 5
	TEMPLATE_4K_7_1 = 6
	TEMPLATE_4K_HDR_STEREO = 7
	TEMPLATE_4K_HDR_7_1 = 8
	TEMPLATE_4K_HDR_AVR_ONLY = 9
	LOWEST_COMMON_DENOMINATOR = 10
	LOWEST_COMMON_DENOMINATOR_ALL = 11
	TEMPLATE_4K_HDR_ATMOS = 12
	SINK_1 = 101
	SINK_2 = 102
	SINK_3 = 103
	SINK_4 = 104
	SINK_5 = 105
	SINK_6 = 106
	SINK_7 = 107
	SINK_8 = 108
	SINK_9 = 109
	SINK_10 = 110
	SINK_11 = 111
	SINK_12 = 112
	SINK_13 = 113
	SINK_14 = 114
	SINK_15= 115
	SINK_16 = 116
	SINK_17 = 117
	SINK_18 = 118
	SINK_19 = 119
	SINK_20 = 120
	SINK_21 = 121
	SINK_22 = 122
	SINK_23 = 123
	SINK_24 = 124
	SINK_25 = 125
	SINK_26 = 126
	SINK_27 = 127
	SINK_28 = 128
	SINK_29 = 129
	SINK_30 = 130
	SINK_31 = 131
	SINK_32 = 132
	CUSTOM_0 = 500
	CUSTOM_1 = 501
	CUSTOM_2 = 502
	CUSTOM_3 = 503
	CUSTOM_4 = 504
	CUSTOM_5 = 505
	CUSTOM_6 = 506
	CUSTOM_7 = 507
	CUSTOM_8 = 508
	CUSTOM_9 = 509
	CUSTOM_10 = 510
	UNKNOWN = 0xFFF

	def values(nb_sinks:int|None=None) -> dict[int, str]: # type: ignore
		rv:dict[int, str] = {}
		for val in range(13):
			rv[val] = str(EdidProfile(val))
		if nb_sinks is None:
			nb_sinks = 32
		for val in range(101, 101 + nb_sinks):
			rv[val] = str(EdidProfile(val))
		return rv

class FirmwareType(Enum):
	UNKNOWN = 0
	FPGA = 1
	LINUX = 2
	LOADING_OVERLAY = 3

	def __init__(self, val:int|None) -> None:
		if (val is None) or (val > 3):
			self._value = 0
		else:
			self._value = val

	def __str__(self) -> str:
		if (self.value == FirmwareType.FPGA.value):
			return "FPGA"
		if (self.value == FirmwareType.LINUX.value):
			return "Linux"
		if (self.value == FirmwareType.LOADING_OVERLAY.value):
			return "Loading Overlay"
		return "Unknown"

	def __repr__(self) -> str:
		return str(self)

class UtpLinkSpeed(Enum):
    ''' UTP link speed '''

    UNKNOWN = 0
    ''' unknown speed '''

    L_10M = 1
    ''' 10Mbit/s '''

    L_100M = 2
    ''' 100Mbit/s '''

    L_200M = 3
    ''' 200Mbit/s '''

    L_1G = 4
    ''' 1Gbit/s '''

    def __str__(self) -> str:
        if self.value == UtpLinkSpeed.L_10M.value:
            return '10Mbit/s'
        if self.value == UtpLinkSpeed.L_100M.value:
            return '100Mbit/s'
        if self.value == UtpLinkSpeed.L_200M.value:
            return '200Mbit/s'
        if self.value == UtpLinkSpeed.L_1G.value:
            return '1Gbit/s'
        return 'Unknown'

    def __repr__(self) -> str:
        return str(self)