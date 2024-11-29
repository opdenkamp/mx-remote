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

def create_mxr_frame(uid:bytes, opcode:int, payload:bytes=None) -> bytes:
	# create a new mx_remote frame for transmission
	pkt = [80, 56, 1, 0 ]
	pkt.extend(uid)
	pkt.extend([(opcode & 0xFF), ((opcode >> 8) & 0xFF)])
	if payload is None or len(payload) == 0:
		pkt.extend([0, 0])
	else:
		l = len(payload)
		pkt.extend([(l & 0xFF), ((l >> 8) & 0xFF)])
		pkt.extend([payload])
	return bytes(pkt)

def process_mxr_frame(mxr:DeviceRegistry, data:bytes, addr:tuple[str,int]) -> FrameBase:
	# decode a (received) mx_remote frame
	from .FrameHeader import FrameHeader
	hdr = FrameHeader(mxr, data, addr)
	if hdr is not None:
		try:
			# valid frame
			if hdr.remote_id == mxr.uid:
				logging.debug("ignore frame sent by myself")
				return None
			# not one of my own, process the incoming frame
			return _mxr_frame_factory(hdr)
		except Exception:
			print(f"failed to process frame: {traceback.format_exc()}")
			raise
	logging.warning("frame header missing")

def _mxr_frame_factory(hdr:FrameHeader) -> FrameBase:
	# create a new frame from a decoded mx_remote header
	if hdr.opcode == 0x00:
		from .FrameHello import FrameHello
		return FrameHello(hdr)
	if hdr.opcode == 0x01:
		from .FrameDiscover import FrameDiscover
		return FrameDiscover(hdr)
	if hdr.opcode == 0x02:
		from .FrameBayConfig import FrameBayConfig
		return FrameBayConfig(hdr)
	if hdr.opcode == 0x03:
		from .FrameLinks import FrameLinks
		return FrameLinks(hdr)
	if hdr.opcode == 0x04:
		from .FrameConnectStatus import FrameConnectStatus
		return FrameConnectStatus(hdr)
	if hdr.opcode == 0x05:
		from .FramePowerChange import FramePowerChange
		return FramePowerChange(hdr)
	if hdr.opcode == 0x06:
		from .FrameSignalStatus import FrameSignalStatus
		return FrameSignalStatus(hdr)
	if hdr.opcode == 0x07:
		from .FrameEDID import FrameEDID
		return FrameEDID(hdr)
	if hdr.opcode == 0x08:
		from .FrameRoutingChange import FrameRoutingChange
		return FrameRoutingChange(hdr)
	if hdr.opcode == 0x0A:
		from .FrameRCIr import FrameRCIr
		return FrameRCIr(hdr)
	if hdr.opcode == 0x0B:
		from .FrameRCKey import FrameRCKey
		return FrameRCKey(hdr)
	if hdr.opcode == 0x0D:
		from .FrameRCAction import FrameRCAction
		return FrameRCAction(hdr)
	if hdr.opcode == 0x0F:
		from .FrameVolumeUp import FrameVolumeUp
		return FrameVolumeUp(hdr)
	if hdr.opcode == 0x10:
		from .FrameVolumeDown import FrameVolumeDown
		return FrameVolumeDown(hdr)
	if hdr.opcode == 0x12:
		from .FrameVolume import FrameVolume
		return FrameVolume(hdr)
	if hdr.opcode == 0x14:
		from .FrameVolumeSet import FrameVolumeSet
		return FrameVolumeSet(hdr)
	if hdr.opcode == 0x15:
		from .FrameSysTemperature import FrameSysTemperature
		return FrameSysTemperature(hdr)
	if hdr.opcode == 0x1F:
		from .FrameV2IPSourceSwitch import FrameV2IPSourceSwitch
		return FrameV2IPSourceSwitch(hdr)
	if hdr.opcode == 0x16:
		from .FramePDUState import FramePDUState
		return FramePDUState(hdr)
	if hdr.opcode == 0x20:
		from .FrameV2IPLink import FrameV2IPLinkStatus
		return FrameV2IPLinkStatus(hdr)
	if hdr.opcode == 0x22:
		from .FrameSetName import FrameSetName
		return FrameSetName(hdr)
	if hdr.opcode == 0x23:
		from .FrameBayConfigSecondary import FrameBayConfigSecondary
		return FrameBayConfigSecondary(hdr)
	if hdr.opcode == 0x26:
		from .FrameV2IPSources import FrameV2IPSources
		return FrameV2IPSources(hdr)
	if hdr.opcode == 0x27:
		from .FrameBayHide import FrameBayHide
		return FrameBayHide(hdr)
	if hdr.opcode == 0x28:
		from .FrameReboot import FrameReboot
		return FrameReboot(hdr)
	if hdr.opcode == 0x29:
		from .FrameNetworkStatus import FrameNetworkStatus
		return FrameNetworkStatus(hdr)
	if hdr.opcode == 0x2A:
		from .FrameFirmwareVersion import FrameFirmwareVersion
		return FrameFirmwareVersion(hdr)
	if hdr.opcode == 0x30:
		from .FrameTopology import FrameTopology
		return FrameTopology(hdr)
	if hdr.opcode == 0x31:
		from .FrameSignalStatusNew import FrameSignalStatusNew
		return FrameSignalStatusNew(hdr)
	if hdr.opcode == 0x32:
		from .FrameMirrorStatus import FrameMirrorStatus
		return FrameMirrorStatus(hdr)
	if hdr.opcode == 0x34:
		from .FrameEDIDProfile import FrameEDIDProfile
		return FrameEDIDProfile(hdr)
	if hdr.opcode == 0x36:
		from .FrameV2IPSetMaster import FrameV2IPSetMaster
		return FrameV2IPSetMaster(hdr)
	if hdr.opcode == 0x38:
		from .FrameFilterStatus import FrameFilterStatus
		return FrameFilterStatus(hdr)
	if hdr.opcode == 0x39:
		from .FrameBayStatus import FrameBayStatus
		return FrameBayStatus(hdr)
	if hdr.opcode == 0x3B:
		from .FrameMeshOperation import FrameMeshOperation
		return FrameMeshOperation(hdr)
	if hdr.opcode == 0x3C:
		from .FrameV2IPDeviceConfiguration import FrameV2IPDeviceConfiguration
		return FrameV2IPDeviceConfiguration(hdr)
	if hdr.opcode == 0x3D:
		from .FrameAmpZoneSettings import FrameAmpZoneSettings
		return FrameAmpZoneSettings(hdr)
	if hdr.opcode == 0x3E:
		from .FrameAmpDolbySettings import FrameAmpDolbySettings
		return FrameAmpDolbySettings(hdr)
	if hdr.opcode == 0x3F:
		from .FrameV2IPStats import FrameV2IPStats
		return FrameV2IPStats(hdr)
	logging.warning(f"opcode {hdr.opcode:02X} is not processed")
	return None

