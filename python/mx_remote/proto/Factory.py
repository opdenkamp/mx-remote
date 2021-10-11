''' Methods for creating and processing frames '''
from typing import Tuple
from .FrameBase import FrameBase
from .FrameHeader import FrameHeader

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

def process_mxr_frame(mxr:'mx_remote.Remote.Remote', data:bytes, addr:Tuple[str,int]) -> FrameBase:
	# decode a (received) mx_remote frame
	from .FrameHeader import FrameHeader
	hdr = FrameHeader(mxr, data, addr)
	if hdr is not None:
		# valid frame
		if hdr.remote_id_raw == mxr.uid:
			return None
		# not one of my own, process the incoming frame
		return _mxr_frame_factory(hdr)

def _mxr_frame_factory(hdr:FrameHeader) -> FrameBase:
	# create a new frame from a decoded mx_remote header
	from .FrameBayConfig import FrameBayConfig
	from .FrameHello import FrameHello
	from .FrameLinks import FrameLinks
	from .FrameRoutingChange import FrameRoutingChange
	from .FrameRCKey import FrameRCKey
	from .FrameSignalStatus import FrameSignalStatus
	from .FrameConnectStatus import FrameConnectStatus 
	from .FramePowerChange import FramePowerChange
	from .FramePDUState import FramePDUState
	from .FrameSysTemperature import FrameSysTemperature
	from .FrameVolume import FrameVolume
	from .FrameVolumeUp import FrameVolumeUp
	from .FrameVolumeDown import FrameVolumeDown

	if hdr.opcode == 0:
		return FrameHello(hdr)
	if hdr.opcode == 2:
		return FrameBayConfig(hdr)
	if hdr.opcode == 3:
		return FrameLinks(hdr)
	if hdr.opcode == 4:
		return FrameConnectStatus(hdr)
	if hdr.opcode == 5:
		return FramePowerChange(hdr)
	if hdr.opcode == 6:
		return FrameSignalStatus(hdr)
	if hdr.opcode == 8:
		return FrameRoutingChange(hdr)
	if hdr.opcode == 11:
		return FrameRCKey(hdr)
	if hdr.opcode == 15:
		return FrameVolumeUp(hdr)
	if hdr.opcode == 16:
		return FrameVolumeDown(hdr)
	if hdr.opcode == 18:
		return FrameVolume(hdr)
	if hdr.opcode == 21:
		return FrameSysTemperature(hdr)
	if hdr.opcode == 22:
		return FramePDUState(hdr)
	return None

