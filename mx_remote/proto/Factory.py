##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

''' Methods for creating and processing frames '''
from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import DeviceRegistry
import logging
import traceback

logging.basicConfig(level=logging.DEBUG)

def create_mxr_frame(uid:bytes, opcode:int, payload:bytes|None=None) -> bytes:
	# create a new mx_remote frame for transmission
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
	# decode a (received) mx_remote frame
	from .FrameHeader import FrameHeader
	hdr = FrameHeader(mxr, data, addr)
	try:
		return _mxr_frame_factory(hdr=hdr, timestamp=timestamp)
	except Exception:
		print(f"failed to process frame: {traceback.format_exc()}")
		raise

def _mxr_frame_factory(hdr:FrameHeader, timestamp:float) -> FrameBase|None:
	# create a new frame from a decoded mx_remote header
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
	if hdr.opcode == 0x0A:
		from .FrameRCIr import FrameRCIr
		return FrameRCIr(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x0B:
		from .FrameRCKey import FrameRCKey
		return FrameRCKey(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x0D:
		from .FrameRCAction import FrameRCAction
		return FrameRCAction(header=hdr, timestamp=timestamp)
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
	if hdr.opcode == 0x22:
		from .FrameSetName import FrameSetName
		return FrameSetName(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x23:
		from .FrameBayConfigSecondary import FrameBayConfigSecondary
		return FrameBayConfigSecondary(header=hdr, timestamp=timestamp)
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
	if hdr.opcode == 0x36:
		from .FrameV2IPSetMaster import FrameV2IPSetMaster
		return FrameV2IPSetMaster(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x38:
		from .FrameFilterStatus import FrameFilterStatus
		return FrameFilterStatus(header=hdr, timestamp=timestamp)
	if hdr.opcode == 0x39:
		from .FrameBayStatus import FrameBayStatus
		return FrameBayStatus(header=hdr, timestamp=timestamp)
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

	logging.debug(f"opcode {hdr.opcode:02X} is not processed")
	return None

