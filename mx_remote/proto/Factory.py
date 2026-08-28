######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################

''' Methods for creating and processing frames '''
from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import DeviceRegistry
import logging
import traceback

logging.basicConfig(level=logging.DEBUG)

def create_mxr_frame(uid:bytes, opcode:int, payload:bytes|None=None) -> bytes:
	'''Create a new MX Remote frame for transmission.'''
	pkt = [80, 56, 1, 0 ]
	pkt.extend(uid)
	pkt.extend([(opcode & 0xFF), ((opcode >> 8) & 0xFF)])
	if (payload is None) or (len(payload) == 0):
		pkt.extend([0, 0])
	else:
		l = len(payload)
		pkt.extend([(l & 0xFF), ((l >> 8) & 0xFF)])
		pkt.extend(list(payload))
	return bytes(pkt)

def process_mxr_frame(mxr:DeviceRegistry, timestamp:float, data:bytes, addr:tuple[str,int]) -> FrameBase|None:
	'''Decode a received MX Remote frame and return the appropriate frame object.'''
	from .FrameHeader import FrameHeader
	hdr = FrameHeader(mxr, data, addr)
	try:
		return _mxr_frame_factory(hdr=hdr, timestamp=timestamp)
	except Exception:
		print(f"failed to process frame: {traceback.format_exc()}")
		raise

def _mxr_frame_factory(hdr:FrameHeader, timestamp:float) -> FrameBase|None:
	'''Create a typed frame object from a decoded MX Remote header.'''
	if hdr.opcode == 0x00:
		from .FrameHello import FrameHello
		return FrameHello(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x01:
		from .FrameDiscover import FrameDiscover
		return FrameDiscover(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x02:
		from .FrameBayConfig import FrameBayConfig
		return FrameBayConfig(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x03:
		from .FrameLinks import FrameLinks
		return FrameLinks(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x04:
		from .FrameConnectStatus import FrameConnectStatus
		return FrameConnectStatus(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x05:
		from .FramePowerChange import FramePowerChange
		return FramePowerChange(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x06:
		from .FrameSignalStatus import FrameSignalStatus
		return FrameSignalStatus(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x07:
		from .FrameEDID import FrameEDID
		return FrameEDID(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x08:
		from .FrameRoutingChange import FrameRoutingChange
		return FrameRoutingChange(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x09:
		from .FrameSetRoute import FrameSetRoute
		return FrameSetRoute(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x0A:
		from .FrameRCIr import FrameRCIr
		return FrameRCIr(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x0B:
		from .FrameRCKey import FrameRCKey
		return FrameRCKey(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x0C:
		from .FrameTXRCKey import FrameTXRCKey
		return FrameTXRCKey(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x0D:
		from .FrameRCAction import FrameRCAction
		return FrameRCAction(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x0E:
		from .FrameTXRCAction import FrameTXRCAction
		return FrameTXRCAction(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x11:
		from .FrameAudioClip import FrameAudioClip
		return FrameAudioClip(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x13:
		from .FrameAudioSetRoute import FrameAudioSetRoute
		return FrameAudioSetRoute(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x0F:
		from .FrameVolumeUp import FrameVolumeUp
		return FrameVolumeUp(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x10:
		from .FrameVolumeDown import FrameVolumeDown
		return FrameVolumeDown(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x12:
		from .FrameVolume import FrameVolume
		return FrameVolume(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x14:
		from .FrameVolumeSet import FrameVolumeSet
		return FrameVolumeSet(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x15:
		from .FrameSysTemperature import FrameSysTemperature
		return FrameSysTemperature(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x1F:
		from .FrameV2IPSourceSwitch import FrameV2IPSourceSwitch
		return FrameV2IPSourceSwitch(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x16:
		from .FramePDUState import FramePDUState
		return FramePDUState(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x20:
		from .FrameV2IPLink import FrameV2IPLinkStatus
		return FrameV2IPLinkStatus(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x21:
		from .FrameV2IPDetectBays import FrameV2IPDetectBays
		return FrameV2IPDetectBays(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x22:
		from .FrameSetName import FrameSetName
		return FrameSetName(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x23:
		from .FrameBayConfigSecondary import FrameBayConfigSecondary
		return FrameBayConfigSecondary(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x24:
		from .FrameV2IPManualSourceSwitch import FrameV2IPManualSourceSwitch
		return FrameV2IPManualSourceSwitch(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x26:
		from .FrameV2IPSources import FrameV2IPSources
		return FrameV2IPSources(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x27:
		from .FrameBayHide import FrameBayHide
		return FrameBayHide(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x28:
		from .FrameReboot import FrameReboot
		return FrameReboot(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x29:
		from .FrameNetworkStatus import FrameNetworkStatus
		return FrameNetworkStatus(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x2A:
		from .FrameFirmwareVersion import FrameFirmwareVersion
		return FrameFirmwareVersion(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x2B:
		from .FrameMonitoringPulse import FrameMonitoringPulse
		return FrameMonitoringPulse(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x2C:
		from .FrameUpgradeFPGA import FrameUpgradeFPGA
		return FrameUpgradeFPGA(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x30:
		from .FrameTopology import FrameTopology
		return FrameTopology(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x31:
		from .FrameSignalStatusNew import FrameSignalStatusNew
		return FrameSignalStatusNew(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x32:
		from .FrameMirrorStatus import FrameMirrorStatus
		return FrameMirrorStatus(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x34:
		from .FrameEDIDProfile import FrameEDIDProfile
		return FrameEDIDProfile(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x35:
		from .FrameSetupStatus import FrameSetupStatus
		return FrameSetupStatus(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x36:
		from .FrameV2IPSetMaster import FrameV2IPSetMaster
		return FrameV2IPSetMaster(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x37:
		from .FrameSetInstaller import FrameSetInstaller
		return FrameSetInstaller(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x38:
		from .FrameFilterStatus import FrameFilterStatus
		return FrameFilterStatus(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x39:
		from .FrameBayStatus import FrameBayStatus
		return FrameBayStatus(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x3A:
		from .FrameFactoryReset import FrameFactoryReset
		return FrameFactoryReset(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x3B:
		from .FrameMeshOperation import FrameMeshOperation
		return FrameMeshOperation(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x3C:
		from .FrameV2IPDeviceConfiguration import FrameV2IPDeviceConfiguration
		return FrameV2IPDeviceConfiguration(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x3D:
		from .FrameAmpZoneSettings import FrameAmpZoneSettings
		return FrameAmpZoneSettings(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x3E:
		from .FrameAmpDolbySettings import FrameAmpDolbySettings
		return FrameAmpDolbySettings(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x3F:
		from .FrameV2IPStats import FrameV2IPStats
		return FrameV2IPStats(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x40:
		from .FrameV2IPTiling import FrameV2IPTiling
		return FrameV2IPTiling(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x41:
		from .FrameV2IPPowerSave import FrameV2IPPowerSave
		return FrameV2IPPowerSave(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x42:
		from .FrameV2IPMultiviewer import FrameV2IPMultiviewer
		return FrameV2IPMultiviewer(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x43:
		from .FrameV2IPAudio import FrameV2IPAudio
		return FrameV2IPAudio(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x44:
		from .FrameV2IPBayMapping import FrameV2IPBayMapping
		return FrameV2IPBayMapping(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x45:
		from .FrameRCSettings import FrameRCSettings
		return FrameRCSettings(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x46:
		from .FrameSystemStatus import FrameSystemStatus
		return FrameSystemStatus(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x47:
		from .FrameDebug import FrameDebug
		return FrameDebug(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x48:
		from .FrameTxIR import FrameTxIR
		return FrameTxIR(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x49:
		from .FrameV2IPVideoWall import FrameV2IPVideoWall
		return FrameV2IPVideoWall(header=hdr, timestamp=timestamp)

	# Opcodes reaching here are ones current firmware does not emit:
	#
	#   0x17..0x1E  the CEC range           never implemented
	#   0x25        SYS_BAY_V2IP_DETAILS    retired 2024-09; see below
	#   0x33        RESERVED_1              was MX_OP_NB, the table's end sentinel
	#   0x2D        VIDEO_CLOCK_RATE_OLD    superseded by clock_rate in 0x31
	#   0x2E, 0x2F  V2IP_BLIST_*            behind V2IP_SUPPORT_BLACKLIST, which
	#                                       no project defines
	#
	# Never reuse 0x25. It carried v2ip_device_sources - video, audio and anc at
	# 0, 8 and 16, audio_return at 24, source_clock at 32 - until 0x3C replaced it
	# with the same data reorganised behind a uid. A unit from before that change
	# still decodes 0x25 as those addresses, so anything reissued under the number
	# is read as a stream configuration by whatever is left in the field. 0x33 is
	# reserved for a different reason: it was only ever the count marker, so no
	# unit ever decoded a payload from it.
	#
	# Add decoders here rather than removing them: a unit on older firmware still
	# emits superseded opcodes, which is what 0x06, 0x36 and 0x47 are for. An
	# unhandled opcode is no proof nothing implements it either - 0x42, 0x43 and
	# 0x49 belong to loadable modules.
	logging.debug(f"opcode {hdr.opcode:02X} is not processed")
	return None

