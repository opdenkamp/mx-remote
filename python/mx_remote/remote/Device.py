from .Bay import Bay
from .PDU import PDU
from mx_remote.proto.BayConfig import BayConfig
from mx_remote.proto.FrameHello import FrameHello
from mx_remote.proto.FrameSysTemperature import FrameSysTemperature
from mx_remote.proto.PDUState import PDUState
from typing import Any, Dict, List
from datetime import datetime
import json
import logging

class Device:
	''' remote device '''

	def __init__(self, mxr:'remote.Remote', hello:FrameHello):
		# initialise a new device after receiving a hello frame
		self.bays = {}
		self._mxr = mxr
		self._mxr_hello = hello
		self._mxr_temperature = None
		self._mxr_pdu = None
		self._link_config_received = False
		self._last_ping = datetime.now()

	@property
	def mxr(self) -> 'remote.Remote':
		# mxremote instance
		return self._mxr

	@property
	def online(self) -> bool:
		# check whether this device has pinged in the last minute
		return (datetime.now() - self._last_ping).total_seconds() < 120

	@property
	def configuration_complete(self) -> bool:
		# check whether all configuration info for this device has been received
		return not self.need_link_config and self.has_bays

	@property
	def name(self) -> str:
		# remote device name
		return self._mxr_hello.device_name

	@property
	def address(self) -> str:
		# remote ip address
		return self._mxr_hello.address

	@property
	def serial(self) -> str:
		# device serial number
		return self._mxr_hello.serial

	@property
	def remote_id(self) -> str:
		# device uid
		return self._mxr_hello.remote_id

	@property
	def version(self) -> str:
		# remote firwmare version
		return self._mxr_hello.version

	@property
	def is_video_matrix(self) -> bool:
		# video matrix or not
		return (self._features & (1 << 5)) != 0

	@property
	def is_audio_matrix(self) -> bool:
		# audio matrix or not
		return ((self._features & (1 << 6)) != 0) and not self.is_video_matrix

	@property
	def is_amp(self) -> bool:
		# amp or not
		return ((self._features & (1 << 7)) != 0) and not self.is_video_matrix

	@property
	def supports_arc(self) -> bool:
		return (self._features & (1 << 8)) != 0

	@property
	def temperature(self) -> List[int]:
		if self._mxr_temperature is None:
			return None
		return self._mxr_temperature.temperature

	@property
	def pdu(self) -> PDU:
		return self._mxr_pdu

	@property
	def pdu_connected(self) -> bool:
		pdu = self.pdu
		if pdu is not None:
			return pdu.connected
		return False

	@property
	def features(self) -> List[str]:
		# supported features
		ft = []
		if (self._features & (1 << 0)):
			ft.append("IR RX")
		if (self._features & (1 << 1)):
			ft.append("IR TX")
		if (self._features & (1 << 2)):
			ft.append("CEC")
		if (self._features & (1 << 3)):
			ft.append("V2IP source")
		if (self._features & (1 << 4)):
			ft.append("V2IP sink")
		if (self._features & (1 << 5)):
			ft.append("video routing")
		if (self._features & (1 << 6)):
			ft.append("audio routing")
		if (self._features & (1 << 7)):
			ft.append("volume control")
		if (self._features & (1 << 8)):
			ft.append("ARC")
		if (self._features & (1 << 9)):
			ft.append("remote control")
		return ft

	@property
	def _features(self) -> int:
		# remote feature bitmask
		return self._mxr_hello.features

	@property
	def has_bays(self) -> bool:
		# check whether the configuration for all bays has been received
		return len(self.bays) == (self.nb_inputs + self.nb_outputs)

	@property
	def inputs(self) -> Dict[str, Bay]:
		# all sources available on this device
		rv = {}
		for _, bay in self.bays.items():
			if bay.is_input and not bay.hidden:
				rv[bay.bay_name] = bay
		return rv

	@property
	def nb_inputs(self) -> int:
		# TODO need api call to /system/features to get rid of hardcoded values
		if self.name == 'FF88SA':
			return 12
		if self.name[0:4] == 'FF88':
			return 8
		if self.name == 'PROAMP8':
			return 9
		if self.name == 'FFMB44' or self.name == 'FFMS44':
			return 4
		if self.name[0:4] == 'SP14':
			return 1
		#unknown model
		return 0

	@property
	def outputs(self) -> Dict[str, Bay]:
		# all sinks available on this device
		rv = {}
		for _, bay in self.bays.items():
			if bay.is_output and not bay.hidden:
				rv[bay.bay_name] = bay
		return rv

	@property
	def nb_outputs(self) -> int:
		# TODO need api call to /system/features to get rid of hardcoded values
		if self.name[0:4] == 'FF88':
			return 10
		if self.name == 'PROAMP8':
			return 8
		if self.name == 'FFMB44':
			return 4
		if self.name == 'FFMS44':
			return 6
		if self.name[0:4] == 'SP14':
			return 4
		#unknown model
		return 0

	@property
	def nb_hdbt(self) -> int:
		# TODO hardcoded
		if self.name[0:4] == 'FF88':
			return 8
		if self.name == 'PROAMP8':
			return 0
		if (self.name == 'FFMB44') or (self.name == 'FFMS44') or (self.name[0:4] == 'SP14'):
			return 4
		#unknown model
		return 0

	@property
	def need_link_config(self) -> bool:
		# check whether the link configuration has been received
		return not self._link_config_received if (self.is_amp or self.is_video_matrix or self.is_audio_matrix) else False

	def get_by_portnum(self, portnum: int) -> Bay:
		# get a bay given its port number
		if portnum in self.bays.keys():
			return self.bays[portnum]
		return None

	def get_by_portname(self, portname: str) -> Bay:
		# get a bay given its port name
		for _, bay in self.bays.items():
			if bay.bay_name == portname:
				return bay
		return None

	def on_mxr_hello(self, hello_frame:FrameHello) -> None:
		# received a new hello frame from this device. update local info
		changed = (self._mxr_hello != hello_frame)
		self._mxr_hello = hello_frame
		if changed:
			# tell callbacks that this device changed
			self.mxr.on_device_config_changed(self)

	def on_mxr_temperature(self, temperature_frame:FrameSysTemperature) -> None:
		changed = self._mxr_temperature is None or (self._mxr_temperature != temperature_frame)
		self._mxr_temperature = temperature_frame
		if changed:
			# tell callbacks that this device changed
			self.mxr.on_device_temperature_changed(self)

	def on_mxr_update_pdu(self, pdu_frame:PDUState) -> None:
		self._last_ping = datetime.now()
		if self._mxr_pdu is None:
			self._mxr_pdu = PDU(self, pdu_frame)
			self.mxr.on_pdu_registered(self._mxr_pdu)
		else:
			self._mxr_pdu.on_mxr_update(pdu_frame)

	def on_link_config_received(self) -> None:
		# received link configuration. update local info
		self._last_ping = datetime.now()
		had_config = self._link_config_received
		self._link_config_received = True
		if self.has_bays and not had_config:
			# tell callbacks that all bays got registered for this device
			self.mxr.on_device_config_complete(self)

	def on_mxr_bay_config(self, data:BayConfig) -> None:
		self._last_ping = datetime.now()
		bay = self.get_by_portname(data.bay_name)
		isnew = (bay is None)
		if bay is None:
			bay = Bay(self, data.port, data.bay_name)
			self.bays[data.port] = bay
		bay.on_mxr_bay_config(data)
		if isnew:
			self.mxr.on_bay_registered(bay)
			if self.configuration_complete:
				# tell callbacks that all bays got registered for this device
				self.mxr.on_device_config_complete(self)

	@property
	def amp_dolby_channels(self) -> int:
		rv = 0
		for _, bay in self.bays.items():
			if bay.dolby_input is not None:
				rv += 1
		return rv

	async def get_api(self, uri:str) -> Any:
		cmd = "http://{}/{}".format(self.address, uri)
		logging.debug("tx: %s", str(cmd))
		try:
			async with self.mxr.http_session.get(cmd) as resp:
				data = await resp.json()
				if data['Result']:
					return data
		except Exception as err:
			logging.warning(err)
		return None

	def __str__(self) -> str:
		return "({}) {}".format(self.serial, self.name)

	def __eq__(self, other) -> bool:
		return isinstance(other, Device) and \
			(self.serial == other.serial)

	def __ne__(self, other) -> bool:
		return (not isinstance(other, Device)) or \
			(self.serial != other.serial)

