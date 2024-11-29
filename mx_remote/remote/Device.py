##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

import aiohttp
from .Bay import Bay
from ..Interface import MxrCallbacks, V2IPStreamSources, AmpDolbySettings, DeviceStatus, DeviceV2IPDetailsBase
from .PDU import PDU
from ..proto.BayConfig import BayConfig
from ..proto.FrameHello import FrameHello
from ..proto.FrameSysTemperature import FrameSysTemperature
from ..proto.FrameNetworkStatus import NetworkPortStatus
from ..proto.PDUState import PDUState
from ..proto.V2IPStats import V2IPDeviceStats
from ..Uid import MxrDeviceUid
from typing import Any
from datetime import datetime
import logging
import time

from ..Interface import DeviceBase, BayBase, DeviceRegistry, DeviceFeatures

_LOGGER = logging.getLogger(__name__)

class Device(DeviceBase):
	''' remote device '''

	def __init__(self, registry:DeviceRegistry, hello:FrameHello) -> None:
		# initialise a new device after receiving a hello frame
		self._bays:dict[str, BayBase] = {}
		self._registry = registry
		self._hello = hello
		self._temperature = None
		self._pdu = None
		self._link_config_received = False
		self._last_ping = datetime.now()
		self._online = True
		self._have_config = False
		self._dolby_settings:AmpDolbySettings|None = None
		self._v2ip_sources:list[V2IPStreamSources] = None
		self._network:dict[int, NetworkPortStatus] = {}
		self._v2ip_stats:V2IPDeviceStats = None
		self._v2ip_details:DeviceV2IPDetailsBase = None
		self._mesh_master_uid:MxrDeviceUid = None
		self._rebooting = False
		self._hello_received = time.time()
		self._dev_callbacks:list[callable] = []

	def register_callback(self, callback:callable) -> None:
		'''register a callback, called when the device state changed'''
		self._dev_callbacks.append(callback)

	def unregister_callback(self, callback:callable) -> None:
		'''unregister a callback'''
		if callback in self._dev_callbacks:
			self._dev_callbacks.remove(callback)

	def call_callbacks(self) -> None:
		for callback in self._dev_callbacks:
			callback(self)

	@property
	def status(self) -> DeviceStatus:
		if self.online:
			if self.rebooting:
				return DeviceStatus.REBOOTING
			if self.booting:
				return DeviceStatus.BOOTING
			return DeviceStatus.ONLINE
		return DeviceStatus.OFFLINE

	@property
	def bays(self) -> dict[str, BayBase]:
		return self._bays

	@property
	def callbacks(self) -> MxrCallbacks:
		return self._registry.callbacks

	@property
	def registry(self) -> DeviceRegistry:
		return self._registry

	@property
	def online(self) -> bool:
		# check whether this device has pinged in the last minute
		return (datetime.now() - self._last_ping).total_seconds() < 120

	@property
	def rebooting(self) -> bool:
		if self._rebooting:
			return True
		return self.online and self._hello.features.status_rebooting

	@property
	def booting(self) -> bool:
		return self.online and not self._hello.features.status_rebooting and self.features.booting

	def check_online(self) -> None:
		if self.online != self._online:
			self._online = not self._online
			if not self._online:
				self._have_config = False
			self.callbacks.on_device_online_status_changed(self, self._online)
			self.call_callbacks()

	def on_link_config_received(self) -> None:
		self._link_config_received = True
		self._check_config_complete()

	@property
	def v2ip_sources(self) -> list[V2IPStreamSources]:
		return self._v2ip_sources

	@v2ip_sources.setter
	def v2ip_sources(self, sources:list[V2IPStreamSources]) -> None:
		if (self._v2ip_sources is None) or (self._v2ip_sources != sources):
			self._v2ip_sources = sources
			self.call_callbacks()

	def v2ip_source(self, bay:BayBase) -> V2IPStreamSources|None:
		if not bay.is_input or not bay.device.is_v2ip:
			return None
		if self._v2ip_sources is None:
			return None
		if bay.bay >= len(self._v2ip_sources):
			return None
		return self._v2ip_sources[bay.bay]

	@property
	def v2ip_stats(self) -> V2IPDeviceStats:
		return self._v2ip_stats

	@v2ip_stats.setter
	def v2ip_stats(self, stats:V2IPDeviceStats) -> None:
		self._v2ip_stats = stats
		self.call_callbacks()

	@property
	def v2ip_details(self) -> DeviceV2IPDetailsBase:
		return self._v2ip_details

	@v2ip_details.setter
	def v2ip_details(self, details:DeviceV2IPDetailsBase) -> None:
		self._v2ip_details = details
		self.call_callbacks()

	@property
	def v2ip_source_local(self) -> V2IPStreamSources|None:
		input = self.first_input
		if (input is None):
			return None
		return self.v2ip_source(input)

	@property
	def configuration_complete(self) -> bool:
		'''check whether all configuration info for this device has been received'''
		if not self.has_bays:
			return False
		if self.is_v2ip and (self.v2ip_sources is None):
			return False
		return not self.need_link_config

	def check_configuration_complete_timeout(self) -> bool:
		if self.configuration_complete:
			# info received
			return True
		if ((time.time() - self._hello_received) > 15):
			# configuration incomplete after 15 seconds
			return False
		# waiting for the timeout to pass
		return True

	@property
	def protocol(self) -> int:
		return self._hello.supported_protocol

	@property
	def name(self) -> str:
		# remote device name
		name = self._hello.device_name
		if (len(name.strip()) == 0):
			return "<unnamed>"
		return name

	@property
	def address(self) -> str:
		# remote ip address
		return self._hello.address

	@property
	def serial(self) -> str:
		# device serial number
		return self._hello.serial

	@property
	def remote_id(self) -> MxrDeviceUid:
		# device uid
		return self._hello.remote_id

	@property
	def version(self) -> str:
		# remote firwmare version
		return self._hello.version

	@property
	def is_v2ip(self) -> bool:
		return self.features.v2ip_sink or self.features.v2ip_source

	@property
	def has_local_source(self) -> bool:
		'''True if this device has at least 1 local source'''
		return self.first_input.is_local

	@property
	def has_local_sink(self) -> bool:
		'''True if this device has at least 1 local sink'''
		return self.first_output.is_local

	@property
	def is_video_matrix(self) -> bool:
		# video matrix or not
		return self.features.video_routing

	@property
	def is_audio_matrix(self) -> bool:
		# audio matrix or not
		return self.features.audio_routing and not self.features.video_routing

	@property
	def is_amp(self) -> bool:
		# amp or not
		return self.features.volume_control and self.features.audio_routing and not self.features.video_routing

	@property
	def temperatures(self) -> dict[str,int]:
		if self._temperature is None:
			return {}
		temperatures = self._temperature.temperature
		if self.is_v2ip:
			return {
				'System': temperatures[0] if len(temperatures) > 0 else -1,
				'FPGA': temperatures[1] if len(temperatures) > 1 else -1,
				'Switch': temperatures[2] if len(temperatures) > 2 else -1,
			}
		rv = {}
		cnt = 1
		for temperature in temperatures:
			rv[f'Sensor {cnt}'] = temperature
			cnt += 1
		return rv

	@property
	def pdu(self) -> PDU:
		return self._pdu

	@property
	def pdu_connected(self) -> bool:
		pdu = self.pdu
		if pdu is not None:
			return pdu.connected
		return False

	@property
	def features(self) -> DeviceFeatures:
		return self._hello.features

	@property
	def has_bays(self) -> bool:
		# check whether the configuration for all bays has been received
		return len(self.bays) >= (self.nb_inputs + self.nb_outputs)

	@property
	def inputs(self) -> dict[str, BayBase]:
		# all sources available on this device
		rv = {}
		for _, bay in self.bays.items():
			if bay.is_input and not bay.hidden:
				rv[bay.bay_name] = bay
		return rv

	@property
	def first_input(self) -> BayBase:
		for _, bay in self.bays.items():
			if bay.is_input:
				return bay
		return None

	@property
	def nb_inputs(self) -> int:
		return len(self.inputs)

	@property
	def outputs(self) -> dict[str, BayBase]:
		# all sinks available on this device
		rv = {}
		for _, bay in self.bays.items():
			if bay.is_output:
				rv[bay.bay_name] = bay
		return rv

	@property
	def first_output(self) -> BayBase:
		for _, bay in self.bays.items():
			if bay.is_output:
				return bay
		return None

	@property
	def nb_outputs(self) -> int:
		return len(self.outputs)

	@property
	def nb_hdbt(self) -> int:
		# TODO hardcoded
		if self.name[0:4] == 'FF88':
			return 8
		if self.name == 'PROAMP8':
			return 0
		if (self.name == 'FFMB44') or (self.name == 'FFMS44') or (self.name == 'SP14'):
			return 4
		#unknown model
		return 0

	@property
	def model_name(self) -> str:
		if self.is_v2ip:
			if self.has_local_source and self.has_local_sink:
				return 'OneIP TZ'
			if self.has_local_source:
				return 'OneIP TX'
			return 'OneIP RX'
		if (self.name == 'PROAMP8'):
			return 'ProAmp8'
		if (self.name == 'FFMB44'):
			return 'neo:4 Bronze'
		if (self.name == 'FFMS44'):
			return 'neo:4 Silver'
		if (self.name == 'FF88SA'):
			return 'neo:X'
		if (self.name == 'FF88S'):
			return 'neo:X'
		if (self.name == 'FF88'):
			return 'neo:8'
		if (self.name == 'SP14'):
			return 'neo:4 Splitter'
		return self.name

	@property
	def mesh_master(self) -> 'DeviceBase':
		if not self.is_v2ip or (self._mesh_master_uid is None):
			return self
		return self.registry.get_by_uid(remote_id=self._mesh_master_uid)

	@mesh_master.setter
	def mesh_master(self, master:MxrDeviceUid) -> None:
		if (self._mesh_master_uid is None) or (self._mesh_master_uid != master):
			self._mesh_master_uid = master
			self.call_callbacks()

	@property
	def is_mesh_master(self) -> bool:
		return self.features.mesh_master

	@property
	def need_link_config(self) -> bool:
		# check whether the link configuration has been received
		if (self.is_amp or self.is_video_matrix or self.is_audio_matrix or self.is_v2ip):
			return not self._link_config_received
		return False

	def get_by_portnum(self, portnum: int) -> BayBase:
		# get a bay given its port number
		if portnum in self.bays.keys():
			return self.bays[portnum]
		return None

	def get_by_portname(self, portname: str) -> BayBase:
		# get a bay given its port name
		for _, bay in self.bays.items():
			if bay.bay_name == portname:
				return bay
		return None

	def on_mxr_hello(self, hello_frame:FrameHello) -> None:
		# received a new hello frame from this device. update local info
		self._last_ping = datetime.now()
		changed = (self._hello != hello_frame)
		self._hello = hello_frame
		self._rebooting = False
		if changed:
			# tell callbacks that this device changed
			self.callbacks.on_device_config_changed(self)
			self.call_callbacks()

	def on_mxr_temperature(self, temperature_frame:FrameSysTemperature) -> None:
		changed = self._temperature is None or (self._temperature != temperature_frame)
		self._temperature = temperature_frame
		if changed:
			# tell callbacks that this device changed
			self.callbacks.on_device_temperature_changed(self)
			self.call_callbacks()

	def on_mxr_update_pdu(self, pdu_frame:PDUState) -> None:
		self._last_ping = datetime.now()
		if self._pdu is None:
			self._pdu = PDU(self, pdu_frame)
			self.callbacks.on_pdu_registered(self._pdu)
			self.call_callbacks()
		else:
			self._pdu.on_mxr_update(pdu_frame)

	@property
	def dolby_settings(self) -> AmpDolbySettings|None:
		return self._dolby_settings

	@dolby_settings.setter
	def dolby_settings(self, settings:AmpDolbySettings) -> None:
		changed = (self._dolby_settings is None) or (self._dolby_settings != settings)
		self._dolby_settings = settings
		if changed:
			self.callbacks.on_amp_dolby_settings_changed(self, settings)
			self.call_callbacks()

	def _check_config_complete(self) -> None:
		if self.configuration_complete and not self._have_config:
			# tell callbacks that all bays got registered for this device
			self._have_config = True
			self.callbacks.on_device_config_complete(self)
			self.call_callbacks()

	def on_mxr_bay_config(self, data:BayConfig) -> None:
		self._last_ping = datetime.now()
		bay = self.get_by_portnum(data.port)
		isnew = (bay is None)
		if bay is None:
			bay = Bay(dev=self, data=data)
			self.bays[data.port] = bay
		bay.on_mxr_bay_config(data)
		if isnew:
			self.callbacks.on_bay_registered(bay)
			self._check_config_complete()
			self.call_callbacks()

	@property
	def amp_dolby_channels(self) -> int:
		rv = 0
		for _, bay in self.bays.items():
			if bay.dolby_input is not None:
				rv += 1
		return rv

	@property
	def network_status(self) -> dict[int, NetworkPortStatus]:
		return self._network

	def update_network_status(self, status:NetworkPortStatus):
		self._network[status.port] = status
		self.call_callbacks()

	async def get_api(self, uri:str) -> Any:
		cmd = f"http://{self.address}/{uri}"
		_LOGGER.debug(f"tx: {cmd}")
		try:
			async with self.registry.http_session.get(cmd) as resp:
				data = await resp.json()
				if data['Result']:
					return data
		except Exception as err:
			_LOGGER.warning(err)
		return None

	async def get_log(self) -> str|None:
		cmd = f"http://{self.address}/system/log"
		_LOGGER.debug(f"tx: {cmd}")
		try:
			session:aiohttp.ClientSession = self.registry.http_session
			async with session.get(cmd) as resp:
				data = await resp.read()
				return data.decode('ascii', 'replace')
		except Exception as err:
			_LOGGER.warning(err)
		return None

	async def reboot(self) -> bool:
		from ..proto.FrameReboot import FrameReboot
		from ..proto.FrameBase import FrameBase
		frame:FrameBase = FrameReboot.construct(mxr=self.registry, target=self)
		if frame is not None:
			self.registry.transmit(frame.frame)
			self._rebooting = True
			return True
		return False

	async def mesh_promote(self) -> bool:
		from ..proto.FrameMeshOperation import FrameMeshOperation, MeshOperation
		from ..proto.FrameBase import FrameBase
		frame:FrameBase = FrameMeshOperation.construct(mxr=self.registry, target=self, operation=MeshOperation.PROMOTE_MASTER)
		if frame is not None:
			self.registry.transmit(frame.frame)
			return True
		return False

	async def mesh_remove(self) -> bool:
		from ..proto.FrameMeshOperation import FrameMeshOperation, MeshOperation
		from ..proto.FrameBase import FrameBase
		frame:FrameBase = FrameMeshOperation.construct(mxr=self.registry, target=self, operation=MeshOperation.UNREGISTER)
		if frame is not None:
			self.registry.transmit(frame.frame)
			return True
		return False

	async def read_stats(self, enable:bool) -> bool:
		from ..proto.FrameV2IPStats import FrameV2IPStats
		from ..proto.FrameBase import FrameBase
		frame:FrameBase = FrameV2IPStats.construct(registry=self.registry, device=self, enable=enable)
		if frame is not None:
			self.registry.transmit(frame.frame)
			return True
		return False

	def __str__(self) -> str:
		return f"({self.serial} {self.name})"

	def __eq__(self, other) -> bool:
		return isinstance(other, DeviceBase) and \
			(self.remote_id == other.remote_id)
