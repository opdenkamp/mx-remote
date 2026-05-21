##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Device implementation for MX Remote network devices (matrix, OneIP, amplifier).'''

from .Bay import Bay
from ..Interface import (
	MxrCallbacks,
	V2IPStreamSources,
	AmpDolbySettings,
	DeviceStatus,
	DeviceV2IPDetails,
	DeviceV2IPSink,
	SystemTemperature,
	V2IPStreamSourcesList,
	Multiviewer,
	AudioEndpoint,
	AudioEndpoints,
	AudioChangeSource,
	AudioLinks,
)
from ..proto.BayConfig import BayConfig
from ..proto.FrameHello import FrameHello
from ..proto.FrameMeshOperation import MeshOperation, FrameMeshOperation
from ..proto.FrameV2IPStats import FrameV2IPStats
from ..proto.FrameNetworkStatus import NetworkPortStatus
from ..proto.FrameReboot import FrameReboot
from ..proto.FrameV2IPBayMapping import FrameV2IPBayMapping
from ..proto.V2IPStats import V2IPDeviceStats
from ..proto.FrameSystemStatus import FrameSystemStatus
from ..proto.FrameV2IPMultiviewer import V2IPMultiviewerConfig
from ..proto.FrameFirmwareVersion import FirmwareType,FirmwareVersion
from ..proto.FrameTopology import FrameTopology, TopologyEntry
from ..proto.FrameV2IPMultiviewer import FrameV2IPMultiviewer
from ..proto.Multiviewer import (
	MultiviewerConfig,
	MultiviewerViewMode,
	MultiviewerSource,
	MultiviewerBoolSetting,
	MultiviewerEDIDTemplate,
	MultiviewerPipSize,
	MultiviewerPipPosition,
	MultiviewerAspectRatio,
	MultiviewerOutputMode,
	MultiviewerITCMode,
	MultiviewerHDCPMode,
)
from ..Uid import MxrDeviceUid
from typing import Any, Callable, override
from datetime import datetime
import logging
import time

from ..Interface import DeviceBase, BayBase, DeviceRegistry
from ..proto.Constants import DeviceFeature

_LOGGER = logging.getLogger(__name__)

class Device(DeviceBase):
	'''Remote device on the MX network (matrix, OneIP unit, or amplifier).'''

	def __init__(self, registry:DeviceRegistry, hello:FrameHello) -> None:
		'''Initialise a new device after receiving a hello frame.'''
		self._bays:dict[int, BayBase] = {}
		self._registry = registry
		self._hello = hello
		self._temperatures:SystemTemperature = SystemTemperature([])
		self._link_config_received = False
		self._last_ping = datetime.now()
		self._online = True
		self._have_config = False
		self._dolby_settings:AmpDolbySettings|None = None
		self._network:dict[int, NetworkPortStatus] = {}
		self._v2ip_sources:V2IPStreamSourcesList|None = None
		self._v2ip_stats:V2IPDeviceStats|None = None
		self._v2ip_details:DeviceV2IPDetails|None = None
		self._v2ip_sink:DeviceV2IPSink|None = None
		self._mesh_master_uid:MxrDeviceUid|None = None
		self._v2ip_in_mapping:list[MxrDeviceUid]|None = None
		self._v2ip_out_mapping:list[MxrDeviceUid]|None = None
		self._v2ip_versions:dict[FirmwareType,FirmwareVersion] = {}
		self._audio_endpoints:AudioEndpoints|None = None
		self._sys_status:int|None = None
		self._sys_message:str|None = None
		self._topology:list[TopologyEntry]|None = None
		self._rebooting = False
		self._multiviewer:MultiviewerImpl = MultiviewerImpl(device=self)
		self._hello_received = time.time()
		self._dev_callbacks:list[Callable[[DeviceBase], None]] = []

	def register_callback(self, callback:Callable[[DeviceBase], None]) -> None:
		'''register a callback, called when the device state changed'''
		self._dev_callbacks.append(callback)

	def unregister_callback(self, callback:Callable[[DeviceBase], None]) -> None:
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
	def bays(self) -> dict[int, BayBase]:
		return self._bays

	@property
	def callbacks(self) -> MxrCallbacks:
		return self._registry.callbacks

	@property
	def registry(self) -> DeviceRegistry:
		return self._registry

	@property
	def online(self) -> bool:
		'''Check whether this device has pinged recently.'''
		if (self.protocol >= 0x20):
			return ((datetime.now() - self._last_ping).total_seconds() < 15)
		return ((datetime.now() - self._last_ping).total_seconds() < 120)

	@property
	def rebooting(self) -> bool:
		if self._rebooting:
			return True
		return self.online and \
			(self._hello.features is not None) and \
			DeviceFeature.STATUS_REBOOTING in self._hello.features

	@property
	def booting(self) -> bool:
		return self.online \
			and not self.rebooting \
			and (self.features is not None) \
			and DeviceFeature.BOOTING in self.features

	@property
	def power_save(self) -> bool:
		return (self.features is not None) \
			and DeviceFeature.STATUS_POWER_SAVE in self.features

	@property
	def mesh_support(self) -> bool:
		return (self.features is not None) \
			and DeviceFeature.MESH in self.features

	@property
	def crashed_recently(self) -> bool:
		return (self.features is not None) \
			and DeviceFeature.STATUS_CRASHED in self.features

	@property
	def status_message(self) -> str:
		con_status = self.status
		if (con_status == DeviceStatus.OFFLINE) or (con_status == DeviceStatus.REBOOTING) or (con_status == DeviceStatus.INACTIVE):
			return str(con_status)
		if (con_status == DeviceStatus.ONLINE) and (not self.crashed_recently):
			return 'Healthy'
		if (con_status != DeviceStatus.ONLINE) and (self._sys_message is None):
			return str(con_status)
		def_message = 'Crashed Recently' if (self.crashed_recently) else 'Healthy'
		sys_message = def_message if (self._sys_message is None) else self._sys_message
		return f'{str(con_status)} - {sys_message}'

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
	def v2ip_sources(self) -> V2IPStreamSourcesList|None:
		return self._v2ip_sources

	@v2ip_sources.setter
	def v2ip_sources(self, sources:V2IPStreamSourcesList) -> None:
		if (self._v2ip_sources is None) or (self._v2ip_sources != sources):
			self._v2ip_sources = sources
			self.call_callbacks()

	def v2ip_source(self, bay:BayBase) -> V2IPStreamSources|None:
		if not bay.is_input or not bay.device.is_v2ip:
			return None
		if self._v2ip_sources is None:
			return None
		# Firmware fills MXR_OP_SYS_BAY_V2IP_SOURCES by iterating bays in order
		# (MBAY_ITERATE). Devices with no local input (pure RX) skip bay 0, so
		# the list starts at bay 1 — shift the lookup so bay.bay still maps to
		# the right entry.
		offset = 0 if self.has_local_source else 1
		idx = bay.bay - offset
		if (idx < 0) or (idx >= len(self._v2ip_sources)):
			return None
		return self._v2ip_sources[idx]

	@property
	def v2ip_stats(self) -> V2IPDeviceStats|None:
		return self._v2ip_stats

	@v2ip_stats.setter
	def v2ip_stats(self, stats:V2IPDeviceStats) -> None:
		self._v2ip_stats = stats
		self.call_callbacks()

	@property
	def v2ip_details(self) -> DeviceV2IPDetails|None:
		return self._v2ip_details

	@v2ip_details.setter
	def v2ip_details(self, details:DeviceV2IPDetails) -> None:
		self._v2ip_details = details
		self.call_callbacks()

	@property
	def v2ip_sink(self) -> DeviceV2IPSink|None:
		return self._v2ip_sink

	@v2ip_sink.setter
	def v2ip_sink(self, sink:DeviceV2IPSink) -> None:
		self._v2ip_sink = sink
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
		if (self._hello.supported_protocol is None):
			return 0
		return self._hello.supported_protocol

	@property
	def name(self) -> str:
		'''Remote device name.'''
		name = self._hello.device_name
		if (name is None):
			return "Unknown"
		if (len(name.strip()) == 0):
			return "<unnamed>"
		return name

	@property
	def address(self) -> str:
		'''Remote IP address.'''
		return self._hello.address

	@property
	def serial(self) -> str:
		'''Device serial number.'''
		if (self._hello.serial is None):
			return "Unknown"
		return self._hello.serial

	@property
	def remote_id(self) -> MxrDeviceUid:
		'''Device UID.'''
		return self._hello.remote_id

	@property
	def version(self) -> str:
		'''Remote firmware version.'''
		if (self._hello.version is None):
			return "Unknown"
		return self._hello.version

	@property
	def is_v2ip(self) -> bool:
		return (self.features is not None) \
			and (DeviceFeature.V2IP_SINK in self.features or DeviceFeature.V2IP_SOURCE in self.features)

	@property
	def has_local_source(self) -> bool:
		'''True if this device has at least 1 local source'''
		return self.first_input.is_local if self.first_input is not None else False

	@property
	def has_local_sink(self) -> bool:
		'''True if this device has at least 1 local sink'''
		return self.first_output.is_local if self.first_output is not None else False

	@property
	def is_video_matrix(self) -> bool:
		'''True if this device is a video matrix.'''
		return (self.features is not None) and DeviceFeature.VIDEO_ROUTING in self.features

	@property
	def is_audio_matrix(self) -> bool:
		'''True if this device is an audio matrix.'''
		return (self.features is not None) \
			and DeviceFeature.AUDIO_ROUTING in self.features \
			and DeviceFeature.VIDEO_ROUTING not in self.features

	@property
	def is_amp(self) -> bool:
		'''True if this device is an amplifier.'''
		return (self.features is not None) \
			and DeviceFeature.VOLUME_CONTROL in self.features \
			and DeviceFeature.AUDIO_ROUTING in self.features \
			and DeviceFeature.VIDEO_ROUTING not in self.features

	@property
	def temperatures(self) -> dict[str,int]:
		if self.is_v2ip:
			return {
				'System': self._temperatures[0] if len(self._temperatures) > 0 else -1,
				'FPGA': self._temperatures[1] if len(self._temperatures) > 1 else -1,
				'Switch': self._temperatures[2] if len(self._temperatures) > 2 else -1,
			}
		rv:dict[str,int] = {}
		cnt = 1
		for temperature in self._temperatures:
			rv[f'Sensor {cnt}'] = temperature
			cnt += 1
		return rv

	@property
	def features(self) -> DeviceFeature|None:
		return self._hello.features

	@property
	def has_bays(self) -> bool:
		'''Check whether the configuration for all bays has been received.'''
		return len(self.bays) >= (self.nb_inputs + self.nb_outputs)

	@property
	def inputs(self) -> dict[str, BayBase]:
		'''All sources available on this device.'''
		rv:dict[str, BayBase] = {}
		for _, bay in self.bays.items():
			if bay.is_input and not bay.hidden:
				rv[bay.bay_name] = bay
		return rv

	@property
	def first_input(self) -> BayBase|None:
		for _, bay in self.bays.items():
			if bay.is_input:
				return bay
		return None

	@property
	def nb_inputs(self) -> int:
		return len(self.inputs)

	@property
	def outputs(self) -> dict[str, BayBase]:
		'''All sinks available on this device.'''
		rv:dict[str, BayBase] = {}
		for _, bay in self.bays.items():
			if bay.is_output:
				rv[bay.bay_name] = bay
		return rv

	@property
	def first_output(self) -> BayBase|None:
		for _, bay in self.bays.items():
			if bay.is_output:
				return bay
		return None

	@property
	def nb_outputs(self) -> int:
		return len(self.outputs)

	@property
	def nb_hdbt(self) -> int:
		'''Number of HDBaseT ports. Hardcoded per model name (not in hello frame for older models).'''
		if self.name[0:4] == 'FF88' or self.name[0:4] == 'FF66' or self.name[0:4] == 'FF64':
			return 8 if self.name[0:4] == 'FF88' else 6 if self.name[0:4] == 'FF66' else 4
		if (self.name == 'FFMB44') or (self.name == 'FFMS44') or (self.name == 'FFMG44') \
			or self.name[0:4] == 'SP14':
			return 4
		return 0

	@property
	def model_name(self) -> str:
		if self.is_v2ip:
			if self.is_oneip_multiviewer:
				return 'OneIP Multiviewer'
			if self.has_local_source and self.has_local_sink:
				return 'OneIP Transceiver'
			if self.has_local_source:
				return 'OneIP Transmitter'
			return 'OneIP Receiver'
		_MODEL_NAMES:dict[str, str] = {
			'PROAMP8':  'ProAmp8',
			'PROAMPv2': 'ProAmp8 v2',
			'FFMB44':   'neo:4 Bronze',
			'FFMS44':   'neo:4 Silver',
			'FFMG44':   'neo:4 Gold',
			'FF88SA':   'neo:X',
			'FF88S':    'neo:X',
			'FF88T':    'neo:X',
			'FF88':     'neo:8',
			'FF88A':    'neo:8 Audio',
			'FF88A1':   'neo:8 Audio',
			'FF66SA':   'neo:6 X',
			'FF66A':    'neo:6 Audio',
			'FF66A1':   'neo:6 Audio',
			'FF64S':    'neo:6',
			'SP14':     'neo:4 Splitter',
			'SP142':    'neo:4 Splitter',
		}
		return _MODEL_NAMES.get(self.name, self.name)

	@property
	def mesh_master(self) -> 'DeviceBase|None':
		if not self.is_v2ip or (self._mesh_master_uid is None):
			return self
		return self.registry.get_by_uid(remote_id=self._mesh_master_uid)

	@mesh_master.setter
	def mesh_master(self, master:MxrDeviceUid|None) -> None:
		if (self._mesh_master_uid is None) or (self._mesh_master_uid != master):
			self._mesh_master_uid = master
			self.call_callbacks()

	@property
	@override
	def is_mesh_master(self) -> bool:
		return (self.features is not None) and DeviceFeature.MESH_MASTER in self.features

	@property
	@override
	def is_mesh_member(self) -> bool:
		return (self.features is not None) and DeviceFeature.MESH_MEMBER in self.features

	@property
	@override
	def is_oneip_multiviewer(self) -> bool:
		return self.is_v2ip and (self.features is not None) and DeviceFeature.MULTIVIEWER in self.features

	@property
	@override
	def is_oneip_tz(self) -> bool:
		return self.is_v2ip and self.has_local_sink and self.has_local_source

	@property
	@override
	def is_oneip_tx(self) -> bool:
		return self.is_v2ip and self.has_local_source and not self.has_local_sink

	@property
	@override
	def is_oneip_rx(self) -> bool:
		return self.is_v2ip and self.has_local_sink and not self.has_local_source

	@property
	def need_link_config(self) -> bool:
		'''Check whether the link configuration has been received.'''
		if (self.is_amp or self.is_video_matrix or self.is_audio_matrix or self.is_v2ip):
			return not self._link_config_received
		return False

	@override
	def get_by_portnum(self, portnum: int) -> BayBase|None:
		'''Get a bay given its port number.'''
		if portnum in self.bays.keys():
			return self.bays[portnum]
		return None

	@override
	def get_by_portname(self, portname: str) -> BayBase|None:
		'''Get a bay given its port name.'''
		for _, bay in self.bays.items():
			if bay.bay_name == portname:
				return bay
		return None

	@override
	def get_by_mode_bay(self, mode:str, bay: int) -> BayBase|None:
		for _, b in self.bays.items():
			if (b.mode == mode) and (b.bay == bay):
				return b
		return None

	def _on_mxr_hello(self, hello_frame:FrameHello) -> None:
		# received a new hello frame from this device. update local info
		self._last_ping = datetime.now()
		changed = (self._hello != hello_frame)
		self._hello = hello_frame
		self._rebooting = False
		if changed:
			# tell callbacks that this device changed
			self.callbacks.on_device_config_changed(self)
			self.call_callbacks()

	def _on_mxr_temperature(self, temperature_frame:SystemTemperature) -> None:
		changed = (self._temperatures != temperature_frame)
		self._temperatures = temperature_frame
		if changed:
			# tell callbacks that this device changed
			self.callbacks.on_device_temperature_changed(self)
			self.call_callbacks()

	@property
	@override
	def dolby_settings(self) -> AmpDolbySettings|None:
		return self._dolby_settings

	@property
	@override
	def multiviewer(self) -> Multiviewer:
		return self._multiviewer

	@dolby_settings.setter
	def dolby_settings(self, settings:AmpDolbySettings) -> None:
		changed = (self._dolby_settings is None) or (self._dolby_settings != settings)
		self._dolby_settings = settings
		if changed:
			_LOGGER.debug(f"dolby settings changed {self}: mode={settings.mode} upmix={settings.pcm_upmix} dolby detected={settings.dolby_detected} upmix active={settings.pcm_upmix_active}")
			self.callbacks.on_amp_dolby_settings_changed(self, settings)
			self.call_callbacks()

	def _check_config_complete(self) -> None:
		if self.configuration_complete and not self._have_config:
			# tell callbacks that all bays got registered for this device
			self._have_config = True
			self.callbacks.on_device_config_complete(self)
			self.call_callbacks()

	def _on_mxr_bay_config(self, data:BayConfig) -> None:
		self._last_ping = datetime.now()
		bay = self.get_by_portnum(data.port)
		isnew = (bay is None)
		if bay is None:
			bay = Bay(dev=self, data=data)
			self.bays[data.port] = bay
		bay.on_mxr_update(data)
		if isnew:
			self.callbacks.on_bay_registered(bay)
			self._check_config_complete()
			self.call_callbacks()

	@override
	def audio_endpoint_by_name(self, name:str) -> AudioEndpoint|None:
		if (self._audio_endpoints is None):
			return None
		for _, ep in self._audio_endpoints.endpoints.items():
			if (str(ep.id) == name):
				return ep
		return None

	@override
	def audio_endpoint_by_id(self, id:int) -> AudioEndpoint|None:
		if (self._audio_endpoints is None):
			return None
		for _, ep in self._audio_endpoints.endpoints.items():
			if (ep.id == id):
				return ep
		return None

	@override
	def on_mxr_update(self, data:Any) -> None:
		if isinstance(data, BayConfig):
			self._on_mxr_bay_config(data)
		elif isinstance(data, FrameHello):
			self._on_mxr_hello(data)
		elif isinstance(data, FrameMeshOperation):
			if (data.operation == MeshOperation.REPORT_MEMBERSHIP):
				self.mesh_master = data.target_uid
		elif isinstance(data, NetworkPortStatus):
			self.update_network_status(data)
		elif isinstance(data, SystemTemperature):
			self._on_mxr_temperature(data)
		elif isinstance(data, DeviceV2IPDetails):
			self.v2ip_details = data
		elif isinstance(data, DeviceV2IPSink):
			self.v2ip_sink = data
		elif isinstance(data, V2IPStreamSourcesList):
			self.v2ip_sources = data
		elif isinstance(data, V2IPDeviceStats):
			self.v2ip_stats = data
		elif isinstance(data, V2IPStreamSources):
			if ((sources := self._v2ip_sources) is None):
				self._v2ip_sources = V2IPStreamSourcesList()
				sources = self._v2ip_sources
			if len(sources) > 0:
				sources[0] = data
			else:
				sources.append(data)
		elif isinstance(data, FrameV2IPBayMapping):
			if data.first_bay_id is None:
				return
			# Firmware iterates bays in MBAY_ITERATE order; the wire payload's
			# first_bay_id tells us the bay number of payload[0], so payload[i]
			# maps to bay number (first_bay_id + i). Devices without a local
			# bay 0 (pure RX) emit first_bay_id=1 and skip the bay-0 slot.
			mode = 'Input' if data.is_input else 'Output'
			for idx in range(data.nb_bays):
				bay = self.get_by_mode_bay(mode=mode, bay=data.first_bay_id + idx)
				if (bay is not None):
					bay.v2ip_uid = data.bay(idx=idx) # pyright: ignore[reportAttributeAccessIssue]
		elif isinstance(data, FrameSystemStatus):
			if (self._sys_message is None) or (self._sys_status is None) or (self._sys_status != data.status) or (self._sys_message != data.message):
				self._sys_status = data.status
				self._sys_message = data.message
				self.call_callbacks()
		elif isinstance(data, V2IPMultiviewerConfig):
			if self._multiviewer.update(config=data):
				self.call_callbacks()
		elif isinstance(data, FirmwareVersion):
			if (data.firmware_type not in self._v2ip_versions) or (self._v2ip_versions[data.firmware_type] != data):
				self._v2ip_versions[data.firmware_type] = data
				self.call_callbacks()
		elif isinstance(data, FrameTopology):
			if (self._topology is None) or (self._topology != data.topology):
				self._topology = data.topology
				self.call_callbacks()
		elif isinstance(data, AudioEndpoints):
			self._audio_endpoints = data
			if (self.is_oneip_tz or self.is_oneip_tx):
				first_input = self.first_input
				first_ep = data.tree_first_output
				if (first_input is not None):
					first_input.audio_endpoint = first_ep # pyright: ignore[reportAttributeAccessIssue]
				first_output = self.first_output
				first_ep = data.tree_first_input
				if (first_output is not None):
					first_output.audio_endpoint = first_ep # pyright: ignore[reportAttributeAccessIssue]
			elif self.is_amp:
				for id, ep in data.endpoints.items():
					if (id < 10):
						bay = self.get_by_mode_bay(mode="Input", bay=id)
					else:
						bay = self.get_by_mode_bay(mode="Output", bay=id-10)
					if (bay is not None):
						bay.audio_endpoint = ep # pyright: ignore[reportAttributeAccessIssue]
		elif isinstance(data, AudioChangeSource):
			if (data.source_uid is not None) and (data.source_id is not None):
				source_ep = self.registry.get_audio_endpoint(device=data.source_uid, id=data.source_id)
				if (source_ep is not None) and (source_ep.bay is not None):
					source_ep.bay.on_mxr_audio_source_change(endpoint=source_ep, data=data) # pyright: ignore[reportAttributeAccessIssue]
		elif isinstance(data, AudioLinks):
			for link in data.entries:
				ep = self.audio_endpoint_by_id(link.endpoint)
				if ep is not None:
					ep.set_link(link.link_device, link.link_endpoint)
		else:
			_LOGGER.warning(f"unknown update type {str(type(data))}: {str(data)}")

	@property
	def amp_dolby_channels(self) -> int:
		rv = 0
		for _, bay in self.bays.items():
			if bay.dolby_input is not None:
				rv += 1
		return rv

	@property
	@override
	def v2ip_firmware_versions(self) -> dict[FirmwareType,FirmwareVersion]|None:
		return self._v2ip_versions

	@property
	def mac_address(self) -> str|None:
		for _, status in self._network.items():
			v = status.mac_address
			if (v is not None) and (v != "00:00:00:00:00:00"):
				return v
		return None

	@property
	def network_status(self) -> dict[int, NetworkPortStatus]:
		return self._network

	def update_network_status(self, status:NetworkPortStatus) -> None:
		self._network[status.port] = status
		self.call_callbacks()

	async def get_api(self, uri:str) -> dict[str, Any]|None:
		'''Perform an HTTP GET request against the device API.'''
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
		'''Retrieve the system log from the device.'''
		cmd = f"http://{self.address}/system/log"
		_LOGGER.debug(f"tx: {cmd}")
		try:
			async with self.registry.http_session.get(cmd) as resp:
				data = await resp.read()
				return data.decode('ascii', 'replace')
		except Exception as err:
			_LOGGER.warning(err)
		return None

	async def reboot(self) -> bool:
		'''Send a reboot command to the device.'''
		frame = FrameReboot.construct(mxr=self.registry, target=self)
		if frame is not None:
			self.registry.transmit(frame.frame)
			self._rebooting = True
			return True
		return False

	async def mesh_promote(self) -> bool:
		'''Promote this device to mesh controller.'''
		frame = FrameMeshOperation.construct(mxr=self.registry, target=self, operation=MeshOperation.PROMOTE_CONTROLLER)
		if frame is not None:
			self.registry.transmit(frame.frame)
			return True
		return False

	async def mesh_remove(self) -> bool:
		'''Remove this device from the mesh network.'''
		frame = FrameMeshOperation.construct(mxr=self.registry, target=self, operation=MeshOperation.UNREGISTER)
		if frame is not None:
			self.registry.transmit(frame.frame)
			return True
		return False

	async def read_stats(self, enable:bool) -> bool:
		'''Enable or disable V2IP statistics reporting on the device.'''
		frame = FrameV2IPStats.construct(registry=self.registry, device=self, enable=enable)
		if frame is not None:
			self.registry.transmit(frame.frame)
			return True
		return False

	def __repr__(self) -> str:
		return self.serial

	def __str__(self) -> str:
		return f"({self.serial} {self.name})"

	def __eq__(self, other:Any) -> bool:
		return isinstance(other, DeviceBase) and \
			(self.remote_id == other.remote_id)

class MultiviewerImpl(Multiviewer):
	'''Multiviewer configuration and control for a OneIP multiviewer device.'''

	def __init__(self, device:Device) -> None:
		self._device = device
		self._config:MultiviewerConfig|None = None

	def update(self, config:MultiviewerConfig) -> bool:
		if (self._config is None) or (self._config != config):
			self._config = config
			return True
		return False

	@property
	def device(self) -> Device:
		return self._device

	@property
	def mcu_version(self) -> str:
		if not self.device.is_oneip_multiviewer:
			return "Not a Multiviewer"
		if (self._config is None) or (self._config.mcu_version is None):
			return "Unknown"
		return self._config.mcu_version

	@property
	def scaler_version(self) -> str:
		if not self.device.is_oneip_multiviewer:
			return "Not a Multiviewer"
		if (self._config is None) or (self._config.scaler_version is None):
			return "Unknown"
		return self._config.scaler_version

	@property
	def view_mode(self) -> MultiviewerViewMode:
		if not self.device.is_oneip_multiviewer:
			return MultiviewerViewMode.UNKNOWN
		if (self._config is None):
			return MultiviewerViewMode.UNKNOWN
		return self._config.view_mode

	def video_source(self, screen:int) -> MultiviewerSource:
		if not self.device.is_oneip_multiviewer:
			return MultiviewerSource.UNKNOWN
		if (self._config is None):
			return MultiviewerSource.UNKNOWN
		return self._config.video_source(screen=screen)

	@property
	def audio_source(self) -> MultiviewerSource:
		if not self.device.is_oneip_multiviewer:
			return MultiviewerSource.UNKNOWN
		if (self._config is None):
			return MultiviewerSource.UNKNOWN
		return self._config.audio_source

	@property
	def audio_volume(self) -> int:
		if not self.device.is_oneip_multiviewer:
			return -1
		if (self._config is None):
			return -1
		return self._config.audio_volume

	@property
	def audio_muted(self) -> MultiviewerBoolSetting:
		if not self.device.is_oneip_multiviewer:
			return MultiviewerBoolSetting.UNKNOWN
		if (self._config is None):
			return MultiviewerBoolSetting.UNKNOWN
		return self._config.audio_muted

	@property
	def edid_template(self) -> MultiviewerEDIDTemplate:
		if not self.device.is_oneip_multiviewer:
			return MultiviewerEDIDTemplate.UNKNOWN
		if (self._config is None):
			return MultiviewerEDIDTemplate.UNKNOWN
		return self._config.edid_template

	@property
	def remote_control(self) -> MultiviewerSource:
		if not self.device.is_oneip_multiviewer:
			return MultiviewerSource.UNKNOWN
		if (self._config is None):
			return MultiviewerSource.UNKNOWN
		return self._config.remote_control

	@property
	def pip_size(self) -> MultiviewerPipSize:
		if not self.device.is_oneip_multiviewer:
			return MultiviewerPipSize.UNKNOWN
		if (self._config is None):
			return MultiviewerPipSize.UNKNOWN
		return self._config.pip_size

	@property
	def pip_position(self) -> MultiviewerPipPosition:
		if not self.device.is_oneip_multiviewer:
			return MultiviewerPipPosition.UNKNOWN
		if (self._config is None):
			return MultiviewerPipPosition.UNKNOWN
		return self._config.pip_position

	@property
	def screen_aspect(self) -> MultiviewerAspectRatio:
		if not self.device.is_oneip_multiviewer:
			return MultiviewerAspectRatio.UNKNOWN
		if (self._config is None):
			return MultiviewerAspectRatio.UNKNOWN
		return self._config.aspect_ratio

	@property
	def auto_switch(self) -> MultiviewerBoolSetting:
		if not self.device.is_oneip_multiviewer:
			return MultiviewerBoolSetting.UNKNOWN
		if (self._config is None):
			return MultiviewerBoolSetting.UNKNOWN
		return self._config.auto_switch

	@property
	def output_mode(self) -> MultiviewerOutputMode:
		if not self.device.is_oneip_multiviewer:
			return MultiviewerOutputMode.UNKNOWN
		if (self._config is None):
			return MultiviewerOutputMode.UNKNOWN
		return self._config.output_mode

	@property
	def output_itc_mode(self) -> MultiviewerITCMode:
		if not self.device.is_oneip_multiviewer:
			return MultiviewerITCMode.UNKNOWN
		if (self._config is None):
			return MultiviewerITCMode.UNKNOWN
		return self._config.output_itc_mode

	@property
	def hdcp_mode(self) -> MultiviewerHDCPMode:
		if not self.device.is_oneip_multiviewer:
			return MultiviewerHDCPMode.UNKNOWN
		if (self._config is None):
			return MultiviewerHDCPMode.UNKNOWN
		return self._config.hdcp_mode

	def connected_source(self, input:int) -> MxrDeviceUid|None:
		if not self.device.is_oneip_multiviewer:
			return None
		if (self._config is None):
			return None
		return self._config.mapping(idx=input)

	async def set_view_mode(self, view_mode:MultiviewerViewMode) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.view_mode == view_mode):
			return True
		frame = FrameV2IPMultiviewer.construct_set_view_mode(mxr=self.device.registry, target=self.device, view_mode=view_mode)
		if frame is not None:
			self.device.registry.transmit(frame.frame)
			return True
		return False

	async def set_video_source(self, screen:int, source:MultiviewerSource) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.video_source(screen=screen) == source):
			return True
		frame = FrameV2IPMultiviewer.construct_set_video_source(mxr=self.device.registry, target=self.device, screen=screen, source=source)
		if frame is not None:
			self.device.registry.transmit(frame.frame)
			return True
		return False

	async def set_audio_source(self, source:MultiviewerSource) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.audio_source == source):
			return True
		frame = FrameV2IPMultiviewer.construct_set_audio_source(mxr=self.device.registry, target=self.device, source=source)
		if frame is not None:
			self.device.registry.transmit(frame.frame)
			return True
		return False

	async def set_audio_volume(self, volume:int, muted:bool) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.audio_volume == volume) and (self.audio_muted == (MultiviewerBoolSetting.ON if muted else MultiviewerBoolSetting.OFF)):
			return True
		frame = FrameV2IPMultiviewer.construct_set_audio_volume(mxr=self.device.registry, target=self.device, volume=volume, muted=muted)
		if frame is not None:
			self.device.registry.transmit(frame.frame)
			return True
		return False

	async def set_edid_template(self, edid:MultiviewerEDIDTemplate) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.edid_template == edid):
			return True
		frame = FrameV2IPMultiviewer.construct_set_edid_template(mxr=self.device.registry, target=self.device, edid=edid)
		if frame is not None:
			self.device.registry.transmit(frame.frame)
			return True
		return False

	async def set_remote_control(self, source:MultiviewerSource) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.remote_control == source):
			return True
		frame = FrameV2IPMultiviewer.construct_set_remote_control(mxr=self.device.registry, target=self.device, source=source)
		if frame is not None:
			self.device.registry.transmit(frame.frame)
			return True
		return False

	async def set_pip_size(self, size:MultiviewerPipSize) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.pip_size == size):
			return True
		frame = FrameV2IPMultiviewer.construct_set_pip_size(mxr=self.device.registry, target=self.device, size=size)
		if frame is not None:
			self.device.registry.transmit(frame.frame)
			return True
		return False

	async def set_pip_position(self, position:MultiviewerPipPosition) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.pip_position == position):
			return True
		frame = FrameV2IPMultiviewer.construct_set_pip_position(mxr=self.device.registry, target=self.device, position=position)
		if frame is not None:
			self.device.registry.transmit(frame.frame)
			return True
		return False

	async def set_screen_aspect(self, aspect:MultiviewerAspectRatio) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.screen_aspect == aspect):
			return True
		frame = FrameV2IPMultiviewer.construct_set_screen_aspect(mxr=self.device.registry, target=self.device, aspect=aspect)
		if frame is not None:
			self.device.registry.transmit(frame.frame)
			return True
		return False

	async def set_auto_switch(self, enable:bool) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.auto_switch == (MultiviewerBoolSetting.ON if enable else MultiviewerBoolSetting.OFF)):
			return True
		frame = FrameV2IPMultiviewer.construct_set_auto_switch(mxr=self.device.registry, target=self.device, enable=enable)
		if frame is not None:
			self.device.registry.transmit(frame.frame)
			return True
		return False

	async def set_output_mode(self, mode:MultiviewerOutputMode) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.output_mode == mode):
			return True
		frame = FrameV2IPMultiviewer.construct_set_output_mode(mxr=self.device.registry, target=self.device, mode=mode)
		if frame is not None:
			self.device.registry.transmit(frame.frame)
			return True
		return False

	async def set_output_itc_mode(self, mode:MultiviewerITCMode) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.output_itc_mode == mode):
			return True
		frame = FrameV2IPMultiviewer.construct_set_output_itc_mode(mxr=self.device.registry, target=self.device, mode=mode)
		if frame is not None:
			self.device.registry.transmit(frame.frame)
			return True
		return False

	async def set_hdcp_mode(self, mode:MultiviewerHDCPMode) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.hdcp_mode == mode):
			return True
		frame = FrameV2IPMultiviewer.construct_set_hdcp_mode(mxr=self.device.registry, target=self.device, mode=mode)
		if frame is not None:
			self.device.registry.transmit(frame.frame)
			return True
		return False

	async def set_connected_source(self, input:int, source:MxrDeviceUid|None) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		current = self.connected_source(input=input)
		if ((current is None) and (source is not None)) or ((current is not None) and (source is None)) or (current != source):
			frame = FrameV2IPMultiviewer.construct_set_connected_source(mxr=self.device.registry, target=self.device, input=input, source=source)
			if frame is not None:
				self.device.registry.transmit(frame.frame)
				return True
		return False

	async def auto_route(self) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		frame = FrameV2IPMultiviewer.construct_auto_route(mxr=self.device.registry, target=self.device)
		if frame is not None:
			self.device.registry.transmit(frame.frame)
			return True
		return False
