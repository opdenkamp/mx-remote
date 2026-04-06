##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################

'''Protocol constants, feature flags, and enumeration types for the MX Remote binary protocol.'''

from enum import IntEnum, IntFlag

MXR_PROTOCOL_VERSION = 20

class DeviceFeature(IntFlag):
	'''Device feature flags reported in hello frames.'''
	IR_RX              = (1 << 0)
	IR_TX              = (1 << 1)
	CEC                = (1 << 2)
	V2IP_SOURCE        = (1 << 3)
	V2IP_SINK          = (1 << 4)
	VIDEO_ROUTING      = (1 << 5)
	AUDIO_ROUTING      = (1 << 6)
	VOLUME_CONTROL     = (1 << 7)
	AUDIO_RETURN       = (1 << 8)
	REMOTE_CONTROL     = (1 << 9)
	SETUP_COMPLETED    = (1 << 10)
	MESH_MASTER        = (1 << 11)
	STATUS_NOTIFY      = (1 << 12)
	STATUS_WARNING     = (1 << 13)
	STATUS_ERROR       = (1 << 14)
	STATUS_REBOOTING   = (1 << 15)
	MESH_MEMBER        = (1 << 16)
	AUDIO_AMPLIFIER    = (1 << 17)
	BOOTING            = (1 << 18)
	MANAGER            = (1 << 19)
	STATUS_POWER_SAVE  = (1 << 20)
	MESH               = (1 << 21)
	MULTIVIEWER        = (1 << 22)
	STATUS_CRASHED     = (1 << 23)
	BOOT_BIT           = (1 << 31)

BAY_FEATURE_DOLBY_IN_POS = 24

class BayFeaturesMask(IntFlag):
	'''Bay feature flags reported in bay config frames.'''
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

	def toJson(self) -> str:
		return '{' + f'"features":"{int(self)}"' + '}'

	def __str__(self) -> str:
		rv = ""
		if BayFeaturesMask.HDMI_IN in self:
			rv += ", HDMI input"
		if BayFeaturesMask.HDMI_OUT in self:
			rv += ", HDMI output"
		if BayFeaturesMask.AUDIO_DIG_OUT in self:
			rv += ", digital audio output"
		if BayFeaturesMask.AUDIO_DIG_IN in self:
			rv += ", digital audio input"
		if BayFeaturesMask.AUDIO_ANA_OUT in self:
			rv += ", analog audio output"
		if BayFeaturesMask.AUDIO_ANA_IN in self:
			rv += ", analog audio input"
		if BayFeaturesMask.AUDIO_AMP_OUT in self:
			rv += ", amplifier audio output"
		if BayFeaturesMask.DOLBY in self:
			rv += ", Dolby"
		if BayFeaturesMask.IR_IN in self:
			rv += ", IR input"
		if BayFeaturesMask.IR_OUT in self:
			rv += ", IR output"
		if BayFeaturesMask.RC_IN in self:
			rv += ", remote control input"
		if BayFeaturesMask.RC_OUT in self:
			rv += ", remote control output"
		if BayFeaturesMask.AUTO_OFF in self:
			rv += ", auto standby"
		if BayFeaturesMask.V2IP_SOURCE_REMOTE in self:
			rv += ", V2IP remote source"
		if BayFeaturesMask.V2IP_SINK_REMOTE in self:
			rv += ", V2IP remote sink"
		if BayFeaturesMask.V2IP_SOURCE_LOCAL in self:
			rv += ", V2IP local source"
		if BayFeaturesMask.V2IP_SINK_LOCAL in self:
			rv += ", V2IP local sink"

		if (len(rv) != 0):
			return rv[2:]
		return "none"

	def __repr__(self) -> str:
		return str(self)

class BayStatusMask(IntFlag):
	'''Bay status flags.'''
	FAULT = (1 << 0)
	HIDDEN = (1 << 1)
	POWERED = (1 << 2)
	SIGNAL_DETECTED = (1 << 3)
	HPD_DETECTED = (1 << 4)
	SIGNAL_SCRAMBLED = (1 << 5)
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

	def __str__(self) -> str:
		rv = ""
		if BayStatusMask.FAULT in self:
			rv += ", fault detected"
		if BayStatusMask.HIDDEN in self:
			rv += ", hidden"
		if BayStatusMask.POWERED in self:
			rv += ", power enabled"
		if BayStatusMask.SIGNAL_DETECTED in self:
			rv += ", signal detected"
		if BayStatusMask.HPD_DETECTED in self:
			rv += ", hpd detected"
		if BayStatusMask.HDBT_CONNECTED in self:
			rv += ", hdbt link"
		if BayStatusMask.CEC_DETECTED in self:
			rv += ", cec detected"
		if BayStatusMask.POWERED_ON in self:
			rv += ", remote powered on"
		if BayStatusMask.POWERED_OFF in self:
			rv += ", remote powered off"
		if BayStatusMask.AUDIO_ARC_HDMI in self:
			rv += ", hdmi arc"
		if BayStatusMask.AUDIO_ARC_OPTICAL in self:
			rv += ", optical arc"
		if BayStatusMask.AUDIO_ARC_ANALOG in self:
			rv += ", analog arc"
		if BayStatusMask.OFFLINE in self:
			rv += ", offline"
		if BayStatusMask.DECODER_DISABLED in self:
			rv += ", decoder disabled"
		if BayStatusMask.ENCODER_DISABLED in self:
			rv += ", encoder disabled"
		if len(rv) != 0:
			return rv[2:]
		return "none"

class LinkFeature(IntFlag):
	'''Virtual link feature flags.'''
	NONE          = 0
	VIDEO_HDMI    = (1 << 0)
	AUDIO_OPTICAL = (1 << 1)
	AUDIO_ANALOG  = (1 << 2)
	IR            = (1 << 3)
	RC            = (1 << 4)

class RCAction(IntEnum):
	'''Remote control actions.'''
	ACTION_POWER_TOGGLE 	= 0
	ACTION_POWER_ON			= 1
	ACTION_POWER_OFF		= 2
	ACTION_VOLUME_DOWN		= 3
	ACTION_VOLUME_UP		= 4
	ACTION_VOLUME_MUTE		= 5

class RCKey(IntEnum):
    '''Remote control key codes (CEC/IR).'''
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

class RCType(IntEnum):
	'''Remote control protocol type.'''
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

	@staticmethod
	def values() -> dict[int, str]:
		rv:dict[int, str] = {}
		for val in range(8):
			rv[val] = str(RCType(val))
		return rv

class EdidProfile(IntEnum):
	'''EDID profile presets for HDMI sources.'''
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

class FirmwareType(IntEnum):
	'''Firmware component type identifiers.'''
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

class UtpLinkSpeed(IntEnum):
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
