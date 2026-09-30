######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Device implementation for MX Remote network devices (matrix, OneIP, amplifier).'''

from .Bay import Bay
from ..Interface import (
	MxrCallbacks,
	OneIPStreamSources,
	AmpDolbySettings,
	DeviceStatus,
	DeviceOneIPDetails,
	DeviceOneIPSink,
	SystemTemperature,
	OneIPStreamSourcesList,
	Multiviewer,
	AudioEndpoint,
	AudioEndpoints,
	AudioChangeSource,
	AudioLinks,
	DeviceOneIPScalingSettings,
	OneIPDeviceSettings,
	OneIPPowerSaveSchedule,
	OneIPVlan,
	OneIPTestcard,
	OneIPTestSync,
	OneIPTestTone,
	TimeZone,
	DeviceClock,
	OneIPOutputMode,
	OneIPScalingSettings,
)
from ..proto.BayConfig import BayConfig
from ..proto.FrameHello import FrameHello
from ..proto.FrameMeshOperation import MeshOperation, FrameMeshOperation
from ..proto.FrameV2IPStats import FrameV2IPStats
from ..proto.FrameNetworkStatus import NetworkPortStatus
from ..proto.FrameReboot import FrameReboot
from ..proto.FramePing import FramePing
from ..proto.FrameV2IPBayMapping import FrameV2IPBayMapping
from ..proto.V2IPStats import OneIPDeviceStats
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
from ..const import MXR_CONFIG_TIMEOUT
from ..Uid import MxrDeviceUid
from typing import Any, Callable
from ..compat import override
from datetime import datetime
import logging
import time

from ..Interface import DeviceBase, BayBase, DeviceRegistry
from ..proto.FrameBase import FrameBase
from ..proto.Constants import (MXR_PROTOCOL_VERSION_SLOW_HELLO, DeviceFeature, MxrSignalType, OneIPDeviceSetting, OneIPVideoProcessorFeature, OneIPVlanFlag,
                              OneIPTestPattern, OneIPToneMode,
                              MXR_SCALING_FLAG_AUTO_SCALING, MXR_SCALING_FLAG_MODE_VALID,
                              MXR_SCALING_FLAG_OPTIONS_VALID, ONEIP_DEVICE_SETTING_SWITCHES,
                              ONEIP_IR_PROFILE_MAX, ONEIP_IR_PROFILE_NOT_SET, ONEIP_VLAN_PORT_SFP)
from ..proto.FrameV2IPAudio import FrameV2IPAudio
from ..proto.FrameV2IPDeviceConfiguration import FrameV2IPDeviceConfiguration
from ..proto.FrameV2IPTestcard import (FrameV2IPTestcard, TESTCARD_REQUEST, TESTCARD_SET,
                                       TESTCARD_PART_PATTERN, TESTCARD_PART_TONE, TESTCARD_PART_SYNC)

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
		self._bay_config_received = False
		self._last_ping = datetime.now()
		self._online = True
		self._have_config = False
		self._dolby_settings:AmpDolbySettings|None = None
		self._network:dict[int, NetworkPortStatus] = {}
		self._v2ip_sources:OneIPStreamSourcesList|None = None
		# Source records by their position in the sender's list. A paged list
		# arrives as windows that can be reordered or lost, so the records are
		# held by position and _v2ip_sources is the run of them that has
		# arrived from the start.
		self._v2ip_source_pages:dict[int, OneIPStreamSources] = {}
		self._v2ip_stats:OneIPDeviceStats|None = None
		self._v2ip_details:DeviceOneIPDetails|None = None
		self._v2ip_sink:DeviceOneIPSink|None = None
		self._v2ip_features:OneIPVideoProcessorFeature|None = None
		self._v2ip_settings:OneIPDeviceSettings|None = None
		self._v2ip_vlan:OneIPVlan|None = None
		self._v2ip_testcard:OneIPTestcard|None = None
		self._time_zone:TimeZone|None = None
		self._clock:DeviceClock|None = None
		self._mesh_master_uid:MxrDeviceUid|None = None
		# The source device behind each OneIP bay, by bay mode and number. Held
		# here as well as on the bays because a device may send its mappings
		# before the bay configuration that creates those bays, and a bay that
		# arrives later picks its mapping up from here.
		self._v2ip_bay_mappings:dict[tuple[str, int], MxrDeviceUid] = {}
		# Bay mapping pages whose first port names no bay yet, by that port. A
		# page runs on by bay number from the bay at its first port, so it cannot
		# be filed until that bay's configuration says which one it is.
		self._v2ip_bay_mapping_pages:dict[int, list[MxrDeviceUid]] = {}
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
		if (self.protocol >= MXR_PROTOCOL_VERSION_SLOW_HELLO):
			return ((datetime.now() - self._last_ping).total_seconds() < 60)
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

	@override
	def note_link_config(self) -> None:
		'''Note that the device has reported its link configuration.'''
		if self._link_config_received:
			return
		self._link_config_received = True
		self._check_config_complete()

	@override
	def note_bay_config(self) -> None:
		'''Note that the device has sent its primary bay configuration.'''
		if self._bay_config_received:
			return
		self._bay_config_received = True
		self._check_config_complete()

	@property
	def oneip_sources(self) -> OneIPStreamSourcesList|None:
		return self._v2ip_sources

	@oneip_sources.setter
	def oneip_sources(self, sources:OneIPStreamSourcesList) -> None:
		if (self._v2ip_sources is None) or (self._v2ip_sources != sources):
			self._v2ip_sources = sources
			self.call_callbacks()

	@override
	def merge_oneip_sources(self, first:int, total:int, page:OneIPStreamSourcesList) -> None:
		'''Merge one frame of this device's source list into the list it belongs to.

		A list that fits one frame is the whole list and replaces what was held.
		A longer one arrives as pages, and a page is a window rather than the
		list: its records belong at first + index whatever order the pages arrive
		in, and it says nothing about the records it leaves out. Only a frame
		covering the whole list may shorten it.

		total is the sender's count at the moment that page was built rather than
		a promise about the set, so it decides only whether this frame is the
		whole list - it never sizes the result.
		'''
		whole = (first == 0) and (len(page) == total)
		if whole:
			self._v2ip_source_pages.clear()
		for idx, source in enumerate(page):
			self._v2ip_source_pages[first + idx] = source
		if whole:
			self.oneip_sources = page
			return
		# A record's position is what maps it to a bay, so the list reported is
		# the run that has arrived from the start. A gap is where it stops, never
		# something to fill: a placeholder in the middle would report a bay as
		# advertising no streams, which is a reading rather than an absence.
		merged = OneIPStreamSourcesList()
		for at in sorted(self._v2ip_source_pages):
			if (at != len(merged)):
				break
			merged.append(self._v2ip_source_pages[at])
		if (len(merged) == 0):
			return
		self.oneip_sources = merged

	def oneip_source(self, bay:BayBase) -> OneIPStreamSources|None:
		if not bay.is_input or not bay.device.is_oneip:
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
	def oneip_stats(self) -> OneIPDeviceStats|None:
		return self._v2ip_stats

	@oneip_stats.setter
	def oneip_stats(self, stats:OneIPDeviceStats) -> None:
		self._v2ip_stats = stats
		self.call_callbacks()

	@property
	def oneip_details(self) -> DeviceOneIPDetails|None:
		return self._v2ip_details

	@oneip_details.setter
	def oneip_details(self, details:DeviceOneIPDetails) -> None:
		# a controller writing only addresses or scaling sends an out-of-range
		# tx_rate and leaves the dscp bytes unset; keep the cached values for
		# those, like the firmware does, instead of reporting them as gone
		self._v2ip_details = details.merge(self._v2ip_details)
		self.call_callbacks()

	@property
	def oneip_sink(self) -> DeviceOneIPSink|None:
		return self._v2ip_sink

	@oneip_sink.setter
	def oneip_sink(self, sink:DeviceOneIPSink) -> None:
		self._v2ip_sink = sink
		self.call_callbacks()

	@property
	@override
	def oneip_features(self) -> OneIPVideoProcessorFeature|None:
		return self._v2ip_features

	@oneip_features.setter
	def oneip_features(self, features:OneIPVideoProcessorFeature) -> None:
		'''Record what this device's video processor supports.

		The mask only ever gains bits, and the caller passes a non-empty one
		from a frame the device sent about itself: every other frame says
		nothing about the subject's processor and leaves this alone.
		'''
		if (self._v2ip_features == features):
			return
		self._v2ip_features = features
		self.call_callbacks()

	@property
	@override
	def oneip_settings(self) -> OneIPDeviceSettings|None:
		return self._v2ip_settings

	@property
	@override
	def time_zone(self) -> TimeZone|None:
		return self._time_zone

	@property
	@override
	def clock(self) -> datetime|None:
		return self._clock.now() if (self._clock is not None) else None

	@property
	@override
	def oneip_vlan(self) -> OneIPVlan|None:
		return self._v2ip_vlan

	@property
	@override
	def oneip_testcard(self) -> OneIPTestcard|None:
		return self._v2ip_testcard

	def _merge_v2ip_settings(self, frame:OneIPDeviceSettings) -> None:
		'''Fold a settings block onto the cached one.

		The caller has already limited a write about this device to what the
		device takes from one; a block that carries no setting leaves the cache
		as it was.
		'''
		if (int(frame.valid) == 0):
			return
		merged = frame.merge(self._v2ip_settings)
		if (merged == self._v2ip_settings):
			return
		self._v2ip_settings = merged
		self.call_callbacks()

	@property
	def oneip_source_local(self) -> OneIPStreamSources|None:
		input = self.first_input
		if (input is None):
			return None
		return self.oneip_source(input)

	@property
	def configuration_complete(self) -> bool:
		'''check whether all configuration info for this device has been received'''
		if (self.features is not None) and (DeviceFeature.MANAGER in self.features):
			# a management client has no bays or links to send
			return True
		if not self.has_bays:
			return False
		if self.is_oneip and (self.oneip_sources is None):
			return False
		return not self.need_link_config

	def check_configuration_complete_timeout(self) -> bool:
		'''Whether this device's configuration is still on course.

		Called on every pass of the probe loop, which is what gives the window
		in need_link_config a moment to expire in: a device that stops waiting
		for its links is announced from here, since no frame need arrive for
		that to become true.

		False asks for another discover - something the device owes has not
		arrived and waiting has not produced it.
		'''
		self._check_config_complete()
		if self.configuration_complete:
			# info received
			return True
		return ((time.time() - self._hello_received) <= MXR_CONFIG_TIMEOUT)

	@property
	def protocol(self) -> int:
		if (self._hello.supported_protocol is None):
			return 0
		return self._hello.supported_protocol

	@override
	def supports_opcode(self, opcode:int) -> bool:
		'''True when this device can receive opcode. See DeviceBase.supports_opcode.'''
		protocol = self.protocol
		if (protocol == 0):
			return True
		return protocol >= FrameBase.opcode_protocol(opcode)

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
	def is_oneip(self) -> bool:
		return (self.features is not None) \
			and (DeviceFeature.ONEIP_SINK in self.features or DeviceFeature.ONEIP_SOURCE in self.features)

	@property
	@override
	def is_oneip_sink(self) -> bool:
		return (self.features is not None) and (DeviceFeature.ONEIP_SINK in self.features)

	@property
	@override
	def is_management(self) -> bool:
		'''True when a receiver would let this device write another device's configuration.

		See DeviceBase.is_management for why both bits are tested.'''
		return (self.features is not None) \
			and (DeviceFeature.MANAGER in self.features or DeviceFeature.MESH_MASTER in self.features)

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
		if self.is_oneip:
			return {
				'System': self._temperatures[0] if len(self._temperatures) > 0 else -1,
				'Video Processor': self._temperatures[1] if len(self._temperatures) > 1 else -1,
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
		'''Whether the device has sent its primary bay configuration.

		That it was sent at all is the whole of what can be established. A device
		pages its bays and nothing on the wire marks the last page - no count, no
		index, no terminating frame - and nothing it says about itself gives the
		number to expect, so counting what arrived could only be compared against
		a guess about the model. Every unit sends that list whatever else it
		sends, which is what makes requiring it safe for all of them; the
		secondary list does not stand in for it.

		For a OneIP device this is half the answer on its own: its bays include
		ones that live on other devices, which arrive on a frame of their own
		that configuration_complete requires separately.

		Unlike the link configuration, waiting for this never times out. A bay
		is what a caller names things after, and a name it assigns before this
		frame arrives is one it assigned to a placeholder - persisted, reused
		from then on, and undone only by editing whatever holds it. So a device
		that has not sent its bays is reported as undescribed for as long as
		that lasts.
		'''
		return self._bay_config_received

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
		if self.is_oneip:
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
		if not self.is_oneip or (self._mesh_master_uid is None):
			return self
		return self.registry.get_by_uid(remote_id=self._mesh_master_uid)

	@mesh_master.setter
	def mesh_master(self, master:MxrDeviceUid|None) -> None:
		if (self._mesh_master_uid is None) or (self._mesh_master_uid != master):
			self._mesh_master_uid = master
			self.call_callbacks()

	@property
	@override
	def mesh_master_uid(self) -> MxrDeviceUid|None:
		'''UID of the mesh controller this device reports, None while it has named none.'''
		return self._mesh_master_uid

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
		return self.is_oneip and (self.features is not None) and DeviceFeature.MULTIVIEWER in self.features

	@property
	@override
	def supports_video_wall(self) -> bool:
		return (self.features is not None) and DeviceFeature.VIDEO_WALL in self.features

	@property
	@override
	def config_initialised(self) -> bool:
		return (self.features is not None) and DeviceFeature.CONFIG_INITIALISED in self.features

	@property
	@override
	def is_oneip_tz(self) -> bool:
		return self.is_oneip and self.has_local_sink and self.has_local_source

	@property
	@override
	def is_oneip_tx(self) -> bool:
		return self.is_oneip and self.has_local_source and not self.has_local_sink

	@property
	@override
	def is_oneip_rx(self) -> bool:
		return self.is_oneip and self.has_local_sink and not self.has_local_source

	@property
	def need_link_config(self) -> bool:
		'''Whether the device has yet to report its link configuration.

		That it reported at all is the whole of what can be established, and no
		count of bays stands in for it. Two reasons, either enough on its own:

		A link record describes one of the sender's own ports. Most of a OneIP
		device's bays are proxies for streams that live on other devices, and
		those own no record - a 14-bay transceiver reports two, for its local
		input and its local output.

		A list longer than one payload is cut to what fits rather than continued.
		An 18-bay amplifier reports 17 records in one page and sends no second
		one, so even a device whose bays are all its own never accounts for the
		last of them.

		Waiting for it ends after MXR_CONFIG_TIMEOUT, and the device is still
		asked for the rest. Nothing a caller has already built needs revising
		when the records do arrive - a link is reported per bay and read on
		access, so an unreported one reads as no link, which is what a link
		coming up later looks like anyway. A withheld frame therefore costs a
		consumer that window rather than leaving the device permanently
		undescribed, which is a state nothing on the wire distinguishes from a
		device that has no bays to offer.
		'''
		if (self.is_amp or self.is_video_matrix or self.is_audio_matrix or self.is_oneip):
			return (not self._link_config_received) \
				and ((time.time() - self._hello_received) <= MXR_CONFIG_TIMEOUT)
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

	def _file_v2ip_bay_mappings(self, first:BayBase, page:list[MxrDeviceUid]) -> None:
		'''File one page of this device's OneIP bay mappings, and hand every filed
		mapping to the bay it names.

		The entries run on from first by bay number rather than by port: inputs
		and outputs share one port space, so a run of bays need not be a run of
		ports. A device may split its list over several pages, so each is filed on
		its own and none replaces what another said.
		'''
		for idx, uid in enumerate(page):
			self._v2ip_bay_mappings[(first.mode, first.bay + idx)] = uid
		for bay in self.bays.values():
			if ((mapped := self._v2ip_bay_mappings.get((bay.mode, bay.bay))) is not None):
				bay.oneip_uid = mapped # pyright: ignore[reportAttributeAccessIssue]

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
		if ((page := self._v2ip_bay_mapping_pages.pop(data.port, None)) is not None):
			# The page this bay starts also names the bays after it.
			self._file_v2ip_bay_mappings(first=bay, page=page)
		elif ((mapped := self._v2ip_bay_mappings.get((bay.mode, bay.bay))) is not None):
			bay.oneip_uid = mapped # pyright: ignore[reportAttributeAccessIssue]
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
		elif isinstance(data, DeviceOneIPDetails):
			self.oneip_details = data
		elif isinstance(data, DeviceOneIPSink):
			self.oneip_sink = data
		elif isinstance(data, OneIPVideoProcessorFeature):
			self.oneip_features = data
		elif isinstance(data, OneIPDeviceSettings):
			self._merge_v2ip_settings(data)
		elif isinstance(data, OneIPVlan):
			if (self._v2ip_vlan != data):
				self._v2ip_vlan = data
				self.call_callbacks()
		elif isinstance(data, OneIPTestcard):
			if (self._v2ip_testcard != data):
				self._v2ip_testcard = data
				self.call_callbacks()
		elif isinstance(data, TimeZone):
			if (self._time_zone != data):
				self._time_zone = data
				self.call_callbacks()
		elif isinstance(data, DeviceClock):
			# Repeated with every periodic broadcast, so it marks no change.
			self._clock = data
		elif isinstance(data, OneIPStreamSourcesList):
			self.merge_oneip_sources(first=0, total=len(data), page=data)
		elif isinstance(data, OneIPDeviceStats):
			self.oneip_stats = data
		elif isinstance(data, OneIPStreamSources):
			if ((sources := self._v2ip_sources) is None):
				self._v2ip_sources = OneIPStreamSourcesList()
				sources = self._v2ip_sources
			if len(sources) > 0:
				sources[0] = data
			else:
				sources.append(data)
		elif isinstance(data, FrameV2IPBayMapping):
			if ((first_port := data.first_port) is None):
				return
			# A page names the port of the bay it starts at, and a page whose first
			# port names no bay yet waits for that bay's configuration.
			if ((first := self.get_by_portnum(first_port)) is None):
				self._v2ip_bay_mapping_pages[first_port] = data.bays
				return
			self._file_v2ip_bay_mappings(first=first, page=data.bays)
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
			# A device answers a lock by re-sending its tree, so a report whose
			# only change is an endpoint's status is still a change.
			previous = self._audio_endpoints
			changed = (previous is None) or (previous != data) or not previous.same_status(data)
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
			if changed:
				self.call_callbacks()
		elif isinstance(data, AudioChangeSource):
			# the endpoint that is changing source is the frame's target, not its source
			if (data.target_uid is not None) and (data.target_id is not None):
				target_ep = self.registry.get_audio_endpoint(device=data.target_uid, id=data.target_id)
				if (target_ep is not None) and (target_ep.bay is not None):
					target_ep.bay.on_mxr_audio_source_change(endpoint=target_ep, data=data) # pyright: ignore[reportAttributeAccessIssue]
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
	def oneip_firmware_versions(self) -> dict[FirmwareType,FirmwareVersion]|None:
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
			if self.registry.transmit(frame.frame) != len(frame.frame):
				return False
			self._rebooting = True
			return True
		return False

	async def ping(self) -> bool:
		'''Ask this device to announce itself now.

		Its hello marks it online again, so a device suspected to be gone is
		confirmed or ruled out within a second or two rather than at the end of
		its silence window. A device that stays silent is not taken offline here:
		that remains the silence window's call.

		False for a device below 0x2A, which drops the frame.
		'''
		frame = FramePing.construct(mxr=self.registry, target=self)
		if (frame is None):
			return False
		return (self.registry.transmit(frame.frame) == len(frame.frame))

	async def mesh_promote(self) -> bool:
		'''Promote this device to mesh controller.'''
		frame = FrameMeshOperation.construct(mxr=self.registry, target=self, operation=MeshOperation.PROMOTE_CONTROLLER)
		if frame is not None:
			if self.registry.transmit(frame.frame) != len(frame.frame):
				return False
			return True
		return False

	async def mesh_remove(self) -> bool:
		'''Remove this device from the mesh network.'''
		frame = FrameMeshOperation.construct(mxr=self.registry, target=self, operation=MeshOperation.UNREGISTER)
		if frame is not None:
			if self.registry.transmit(frame.frame) != len(frame.frame):
				return False
			return True
		return False

	async def read_stats(self, enable:bool) -> bool:
		'''Enable or disable OneIP statistics reporting on the device.'''
		frame = FrameV2IPStats.construct(registry=self.registry, device=self, enable=enable)
		if frame is not None:
			if self.registry.transmit(frame.frame) != len(frame.frame):
				return False
			return True
		return False

	async def set_oneip_auto_scaling(self, enabled:bool) -> bool:
		'''Turn this sink's automatic scaling on or off.

		Automatic scaling and a configured output mode are separate reasons for
		a sink to scale, and this moves only the first: a sink with a mode
		configured goes on scaling to it with automatic scaling off. Turning
		both off is this call plus clear_oneip_output_mode().

		Nothing acknowledges the frame. Read oneip_details.scaling back to learn
		what the sink did, and trust that block only where config_initialised is
		set.

		**Read any route you still need before writing.** The sink rebuilds and
		rebroadcasts its subscription in response, and that report can arrive
		empty for up to a minute; DeviceOneIPSink says when and why.
		'''
		written = MXR_SCALING_FLAG_OPTIONS_VALID
		if enabled:
			written |= MXR_SCALING_FLAG_AUTO_SCALING
		def applied(cached:DeviceOneIPScalingSettings) -> OneIPScalingSettings:
			flags = (cached.flags & ~MXR_SCALING_FLAG_AUTO_SCALING) | written
			return OneIPScalingSettings(mode=cached.mode, refresh=cached.refresh, flags=flags)
		return self._send_v2ip_scaling(mode=MxrSignalType(bytes(2)), refresh=0,
		                               written=written, applied=applied)

	async def set_oneip_output_mode(self, mode:OneIPOutputMode) -> bool:
		'''Set the output format this sink scales to.

		The mode is checked here and nothing is sent if it fails, because every
		value a sink refuses it refuses in silence. Passing that check is not a
		guarantee: the sink also weighs the format against the display's EDID and
		against what its own output stage can produce.

		**Turn automatic scaling off first if it is on.** A sink refuses a mode
		whose format the attached display does not list while it is scaling
		automatically, and refuses it silently. Setting the mode and then turning
		automatic scaling back on is the order that survives, because the mode is
		checked while automatic scaling is still off.

		Configuring a mode is itself a reason to scale, so a sink with one scales
		whether or not automatic scaling is on.

		**Pass a descriptor and a refresh rate that agree.** A sink stores both
		halves and, with its match-source setting on as it ships, reports back
		the descriptor matching the refresh it holds: a 60Hz descriptor written
		with a refresh of 50 reads back as that descriptor's 50Hz sibling, once,
		and stays there. A sink with match-source off reports the descriptor it
		was given. Either way a pair that agrees reads back unchanged, and the
		format driven is the same, so this costs a caller nothing except a
		descriptor it did not write. The substitution shows up on the sink's next
		report rather than immediately, because the cached block holds what was
		written until then.

		A mode read from the sink's own web interface is not interchangeable with
		this pair. That interface reports the descriptor's 60Hz sibling and
		carries the refresh in a field of its own, so writing back what it shows
		as the mode, on its own, changes the setting rather than restoring it.

		**Read any route you still need before writing.** The sink rebuilds and
		rebroadcasts its subscription in response, and that report can arrive
		empty for up to a minute; DeviceOneIPSink says when and why.
		'''
		if ((reason := mode.validate()) is not None):
			_LOGGER.warning(f"not setting the output mode of {self}: {reason}")
			return False
		signal = mode.signal_type
		def applied(cached:DeviceOneIPScalingSettings) -> OneIPScalingSettings:
			return OneIPScalingSettings(mode=signal.value, refresh=mode.refresh,
			                           flags=(cached.flags | MXR_SCALING_FLAG_MODE_VALID))
		return self._send_v2ip_scaling(mode=signal, refresh=mode.refresh,
		                               written=MXR_SCALING_FLAG_MODE_VALID, applied=applied)

	async def clear_oneip_output_mode(self) -> bool:
		'''Clear the output format this sink is configured to scale to.

		The sink stops scaling for that reason and keeps its automatic scaling
		setting, so a sink scaling for both reasons goes on scaling until
		set_oneip_auto_scaling() turns the other one off.

		This is the only way to express "no mode configured", and it is what a
		caller restoring a sink that had none has to send: a sink reports no mode
		by leaving MXR_SCALING_FLAG_MODE_VALID clear, which is not something a
		write can say.

		**Read any route you still need before writing.** The sink rebuilds and
		rebroadcasts its subscription in response, and that report can arrive
		empty for up to a minute; DeviceOneIPSink says when and why.
		'''
		def applied(cached:DeviceOneIPScalingSettings) -> OneIPScalingSettings:
			return OneIPScalingSettings(mode=0, refresh=0,
			                           flags=(cached.flags & ~MXR_SCALING_FLAG_MODE_VALID))
		# The valid bit with a zero mode is the clear. The receiver takes that
		# branch ahead of validating anything, and ignores the depth, colour
		# space and refresh rate beside it.
		return self._send_v2ip_scaling(mode=MxrSignalType(bytes(2)), refresh=0,
		                               written=MXR_SCALING_FLAG_MODE_VALID, applied=applied)

	def _send_v2ip_scaling(self, mode:MxrSignalType, refresh:int, written:int,
	                       applied:Callable[[DeviceOneIPScalingSettings],OneIPScalingSettings]) -> bool:
		'''The one send behind the scaling commands.

		written is the flag byte that goes out; applied says what the sink will
		report afterwards. The two differ where the wire spells a write
		differently from the state it produces - clearing a mode is sent as the
		valid bit over a zero mode and read back as the valid bit clear - so
		predicting the cached value from the frame alone would leave a caller
		reading a state no device ever broadcasts.
		'''
		if not self.is_oneip_sink:
			_LOGGER.warning(f"not setting scaling on {self}: scaling settings need a OneIP sink")
			return False
		frame = FrameV2IPDeviceConfiguration.construct_scaling(
			mxr=self.registry, target=self, target_uid=self.remote_id,
			mode=mode, refresh=refresh, flags=written)
		if (frame is None):
			return False
		if self.registry.transmit(frame.frame) != len(frame.frame):
			return False
		self._apply_v2ip_scaling(applied(self._cached_scaling))
		return True

	async def set_oneip_setting(self, setting:OneIPDeviceSetting, enabled:bool) -> bool:
		'''Switch on/off settings of this OneIP device, all to the same value.

		setting names one or more of ONEIP_DEVICE_SETTING_SWITCHES, and each must
		be one the device has reported: a device ignores a setting it does not
		have, so a write for one would read back as applied here and change
		nothing there.

		Nothing acknowledges the frame. The device answers by reporting its
		settings, and until then oneip_settings reads back what was written.
		'''
		setting = OneIPDeviceSetting(setting)
		if (int(setting) == 0) or ((setting & ~ONEIP_DEVICE_SETTING_SWITCHES) != 0):
			_LOGGER.warning(f"not setting {setting!r} on {self}: only on/off device settings are switched")
			return False
		return self._send_v2ip_settings(OneIPDeviceSettings(
			valid=setting, flags=(setting if enabled else OneIPDeviceSetting(0))))

	async def set_oneip_ir_profile(self, profile:int) -> bool:
		'''Set the infrared profile of this OneIP device's global infrared port.

		profile is below ONEIP_IR_PROFILE_MAX, and is checked here because a
		device ignores one out of range. The terms of set_oneip_setting() apply.
		'''
		if not (0 <= profile < ONEIP_IR_PROFILE_MAX):
			_LOGGER.warning(f"not setting infrared profile {profile} on {self}: no such profile")
			return False
		return self._send_v2ip_settings(OneIPDeviceSettings(
			valid=OneIPDeviceSetting.IR_PROFILE, ir_profile=profile))

	async def set_oneip_sink_ir_profile(self, profile:int) -> bool:
		'''Set the infrared profile of this OneIP device's output infrared port.

		ONEIP_IR_PROFILE_NOT_SET makes the port follow the global one. Otherwise
		as set_oneip_ir_profile().
		'''
		if not (ONEIP_IR_PROFILE_NOT_SET <= profile < ONEIP_IR_PROFILE_MAX):
			_LOGGER.warning(f"not setting output infrared profile {profile} on {self}: no such profile")
			return False
		return self._send_v2ip_settings(OneIPDeviceSettings(
			valid=OneIPDeviceSetting.IR_PROFILE_SINK, ir_profile_sink=profile))

	async def set_oneip_auto_power_save(self, minutes:int) -> bool:
		'''Set how many idle minutes this OneIP device waits before it powers down
		by itself, 0 for never. The terms of set_oneip_setting() apply.'''
		if not (0 <= minutes <= 0xFFFF):
			_LOGGER.warning(f"not setting {minutes} idle minutes on {self}: the field holds 0 to 65535")
			return False
		return self._send_v2ip_settings(OneIPDeviceSettings(
			valid=OneIPDeviceSetting.AUTO_POWER_SAVE, auto_power_save=minutes))

	async def set_oneip_power_save_schedule(self, schedule:OneIPPowerSaveSchedule) -> bool:
		'''Set this OneIP device's daily power save windows.

		Every time is below ONEIP_MINUTES_PER_DAY, and is checked here. The
		windows are kept in the device's own time zone. The terms of
		set_oneip_setting() apply.
		'''
		if not schedule.is_valid():
			_LOGGER.warning(f"not setting power save schedule [{schedule}] on {self}: a time is not a time of day")
			return False
		return self._send_v2ip_settings(OneIPDeviceSettings(
			valid=OneIPDeviceSetting.POWER_SAVE_SCHEDULE, power_save=schedule))

	async def set_oneip_vlan(self, vlan:OneIPVlan) -> bool:
		'''Change this OneIP device's VLAN configuration.

		Writes the VLAN ids, the pinned uplink and the TRUNK flag of vlan; its
		other flags and the fields only the device reports are not sent.
		Refused before anything is sent unless the device announces
		DeviceFeature.VLAN and has reported its configuration, every id is at
		most ONEIP_VLAN_ID_MAX, and the uplink is detected or names a port the
		device has.

		The device applies the change at once and reverts it unless the mesh
		controller, hearing the device report it, confirms it. Nothing is cached
		here: oneip_vlan reads what the device reports, and its is_pending whether
		it is still to be confirmed.
		'''
		why = None
		if not vlan.is_valid():
			why = 'a VLAN id is out of range or the uplink names no port'
		elif (self.features is None) or (DeviceFeature.VLAN not in self.features):
			why = 'the device does not take VLANs'
		elif ((reported := self._v2ip_vlan) is None):
			why = 'it has not reported its VLAN configuration'
		elif (vlan.pinned_uplink_port == ONEIP_VLAN_PORT_SFP) and not reported.has_sfp:
			why = 'the device has no SFP port'
		if (why is not None):
			_LOGGER.warning(f"not changing the VLAN configuration of {self}: {why}")
			return False
		written = OneIPVlan(flags=(OneIPVlanFlag.VALID | (vlan.flags & OneIPVlanFlag.TRUNK)),
		                   device=vlan.device, port=tuple(vlan.port), uplink=vlan.uplink)
		frame = FrameV2IPDeviceConfiguration.construct_vlan(
			mxr=self.registry, target=self, target_uid=self.remote_id, vlan=written)
		if (frame is None):
			return False
		return self.registry.transmit(frame.frame) == len(frame.frame)

	async def set_audio_endpoint_locked(self, endpoint:int, locked:bool) -> bool:
		'''Lock or unlock the audio source of one of this device's audio
		endpoints: while it is locked, a video route change leaves the endpoint's
		audio source alone.

		Refused unless the endpoint reports AudioFeatures.FEATURE_AUDIO_LOCK,
		which is the only one the device acts on. The device reports its
		endpoints again once the lock has changed; the endpoint's audio_locked
		reads it.
		'''
		ep = self.audio_endpoint_by_id(endpoint)
		if (ep is None) or not ep.features.support_audio_lock:
			_LOGGER.warning(f"not locking audio endpoint {endpoint} of {self}: it cannot lock its audio source")
			return False
		frame = FrameV2IPAudio.construct_lock(mxr=self.registry, target=self.remote_id,
		                                      endpoint_id=endpoint, locked=locked)
		if (frame is None):
			return False
		return self.registry.transmit(frame.frame) == len(frame.frame)

	async def request_oneip_testcard(self) -> bool:
		'''Ask this OneIP sink for its test card, which it reports straight back
		into oneip_testcard.

		Refused unless the sink's video processor has reported
		OneIPVideoProcessorFeature.SINK_TEST_PATTERN. A sink with that feature but without
		the module that draws the test card does not answer.
		'''
		return self._send_v2ip_testcard(TESTCARD_REQUEST, 0, OneIPTestcard())

	async def set_oneip_test_pattern(self, pattern:OneIPTestPattern, colour:int=0) -> bool:
		'''Show a test pattern on this OneIP sink's output, or none for
		OneIPTestPattern.OFF. colour is 0xRRGGBB, used by OneIPTestPattern.FLAT.

		A pattern runs until it is turned off, and holds the output on while it
		does. The sink reports its test card in answer. Refused as
		request_oneip_testcard() is, and for a pattern this library does not name
		or a colour wider than 24 bits.
		'''
		if not isinstance(pattern, OneIPTestPattern) or not (0 <= colour <= 0xFFFFFF):
			_LOGGER.warning(f"not showing test pattern {pattern!r} colour {colour:#x} on {self}: "
			                "no such pattern, or a colour wider than 24 bits")
			return False
		return self._send_v2ip_testcard(TESTCARD_SET, TESTCARD_PART_PATTERN,
		                                OneIPTestcard(pattern=pattern, colour=colour))

	async def set_oneip_test_tone(self, tone:OneIPTestTone) -> bool:
		'''Play a test tone on this OneIP sink's output.

		Every value is checked here, as the sink ignores a tone that is not
		OneIPTestTone.is_valid(); OneIPToneMode.OFF stops it whatever the rest
		holds, and the sink keeps those values as its last ones. Otherwise as
		set_oneip_test_pattern().
		'''
		if (tone.mode != OneIPToneMode.OFF) and not tone.is_valid():
			_LOGGER.warning(f"not playing test tone {tone} on {self}: a value is out of range")
			return False
		return self._send_v2ip_testcard(TESTCARD_SET, TESTCARD_PART_TONE, OneIPTestcard(tone=tone))

	async def set_oneip_test_sync(self, sync:OneIPTestSync) -> bool:
		'''Set this OneIP sink's lip-sync flash.

		Checked here as OneIPTestSync.is_valid(), since the sink ignores settings
		that are not. Otherwise as set_oneip_test_pattern().
		'''
		if not sync.is_valid():
			_LOGGER.warning(f"not setting lip-sync {sync} on {self}: a value is out of range")
			return False
		return self._send_v2ip_testcard(TESTCARD_SET, TESTCARD_PART_SYNC, OneIPTestcard(sync=sync))

	def _send_v2ip_testcard(self, kind:int, parts:int, testcard:OneIPTestcard) -> bool:
		'''The one send behind the test card commands. Nothing is cached: the
		sink answers every frame with its test card.'''
		if ((features := self._v2ip_features) is None):
			_LOGGER.warning(f"not sending a test card frame to {self}: its video processor has reported no features")
			return False
		if (OneIPVideoProcessorFeature.SINK_TEST_PATTERN not in features):
			_LOGGER.warning(f"not sending a test card frame to {self}: it cannot draw a test card")
			return False
		frame = FrameV2IPTestcard.construct(mxr=self.registry, target=self, target_uid=self.remote_id,
		                                    kind=kind, parts=parts, testcard=testcard)
		if (frame is None):
			return False
		return self.registry.transmit(frame.frame) == len(frame.frame)

	def _send_v2ip_settings(self, settings:OneIPDeviceSettings) -> bool:
		'''The one send behind the device settings commands.'''
		if ((reported := self._v2ip_settings) is None):
			_LOGGER.warning(f"not changing the settings of {self}: it has not reported any")
			return False
		if ((settings.valid & reported.valid) != settings.valid):
			_LOGGER.warning(f"not changing the settings of {self}: it does not have {settings.valid!r}")
			return False
		frame = FrameV2IPDeviceConfiguration.construct_settings(
			mxr=self.registry, target=self, target_uid=self.remote_id, settings=settings)
		if (frame is None):
			return False
		if self.registry.transmit(frame.frame) != len(frame.frame):
			return False
		self._merge_v2ip_settings(settings)
		return True

	@property
	def _cached_scaling(self) -> DeviceOneIPScalingSettings:
		'''The scaling block as last reported or written, all-zero before either.'''
		if ((details := self._v2ip_details) is None) or ((scaling := details.scaling) is None):
			return OneIPScalingSettings(mode=0, refresh=0, flags=0)
		return scaling

	def _apply_v2ip_scaling(self, scaling:OneIPScalingSettings) -> None:
		'''Replace the cached scaling block with the state a write leaves on the device.

		Separate from the oneip_details setter because that merges a received
		frame on, and merging cannot express a cleared mode: a write clears one
		by sending the valid bit over a zero mode, while a device with no mode
		configured reports the valid bit clear. Only the second is a state a
		device broadcasts, so it is the one to cache.
		'''
		previous = self._v2ip_details
		self._v2ip_details = DeviceOneIPDetails(
			video=(previous.video if previous is not None else None),
			audio=(previous.audio if previous is not None else None),
			anc=(previous.anc if previous is not None else None),
			arc=(previous.arc if previous is not None else None),
			tx_rate=(previous.tx_rate if previous is not None else None),
			scaling=scaling,
			dscp=(previous.dscp if previous is not None else None))
		self.call_callbacks()

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
			if self.device.registry.transmit(frame.frame) != len(frame.frame):
				return False
			return True
		return False

	async def set_video_source(self, screen:int, source:MultiviewerSource) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.video_source(screen=screen) == source):
			return True
		# The layout in the last status report is what bounds the screen index.
		frame = FrameV2IPMultiviewer.construct_set_video_source(mxr=self.device.registry, target=self.device,
			screen=screen, source=source, screens=self.view_mode.screens)
		if frame is not None:
			if self.device.registry.transmit(frame.frame) != len(frame.frame):
				return False
			return True
		return False

	async def set_audio_source(self, source:MultiviewerSource) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.audio_source == source):
			return True
		frame = FrameV2IPMultiviewer.construct_set_audio_source(mxr=self.device.registry, target=self.device, source=source)
		if frame is not None:
			if self.device.registry.transmit(frame.frame) != len(frame.frame):
				return False
			return True
		return False

	async def set_audio_volume(self, volume:int, muted:bool) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.audio_volume == volume) and (self.audio_muted == (MultiviewerBoolSetting.ON if muted else MultiviewerBoolSetting.OFF)):
			return True
		frame = FrameV2IPMultiviewer.construct_set_audio_volume(mxr=self.device.registry, target=self.device, volume=volume, muted=muted)
		if frame is not None:
			if self.device.registry.transmit(frame.frame) != len(frame.frame):
				return False
			return True
		return False

	async def set_edid_template(self, edid:MultiviewerEDIDTemplate) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.edid_template == edid):
			return True
		frame = FrameV2IPMultiviewer.construct_set_edid_template(mxr=self.device.registry, target=self.device, edid=edid)
		if frame is not None:
			if self.device.registry.transmit(frame.frame) != len(frame.frame):
				return False
			return True
		return False

	async def set_remote_control(self, source:MultiviewerSource) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.remote_control == source):
			return True
		frame = FrameV2IPMultiviewer.construct_set_remote_control(mxr=self.device.registry, target=self.device, source=source)
		if frame is not None:
			if self.device.registry.transmit(frame.frame) != len(frame.frame):
				return False
			return True
		return False

	async def set_pip_size(self, size:MultiviewerPipSize) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.pip_size == size):
			return True
		frame = FrameV2IPMultiviewer.construct_set_pip_size(mxr=self.device.registry, target=self.device, size=size)
		if frame is not None:
			if self.device.registry.transmit(frame.frame) != len(frame.frame):
				return False
			return True
		return False

	async def set_pip_position(self, position:MultiviewerPipPosition) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.pip_position == position):
			return True
		frame = FrameV2IPMultiviewer.construct_set_pip_position(mxr=self.device.registry, target=self.device, position=position)
		if frame is not None:
			if self.device.registry.transmit(frame.frame) != len(frame.frame):
				return False
			return True
		return False

	async def set_screen_aspect(self, aspect:MultiviewerAspectRatio) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.screen_aspect == aspect):
			return True
		frame = FrameV2IPMultiviewer.construct_set_screen_aspect(mxr=self.device.registry, target=self.device, aspect=aspect)
		if frame is not None:
			if self.device.registry.transmit(frame.frame) != len(frame.frame):
				return False
			return True
		return False

	async def set_auto_switch(self, enable:bool) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.auto_switch == (MultiviewerBoolSetting.ON if enable else MultiviewerBoolSetting.OFF)):
			return True
		frame = FrameV2IPMultiviewer.construct_set_auto_switch(mxr=self.device.registry, target=self.device, enable=enable)
		if frame is not None:
			if self.device.registry.transmit(frame.frame) != len(frame.frame):
				return False
			return True
		return False

	async def set_output_mode(self, mode:MultiviewerOutputMode) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.output_mode == mode):
			return True
		frame = FrameV2IPMultiviewer.construct_set_output_mode(mxr=self.device.registry, target=self.device, mode=mode)
		if frame is not None:
			if self.device.registry.transmit(frame.frame) != len(frame.frame):
				return False
			return True
		return False

	async def set_output_itc_mode(self, mode:MultiviewerITCMode) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.output_itc_mode == mode):
			return True
		frame = FrameV2IPMultiviewer.construct_set_output_itc_mode(mxr=self.device.registry, target=self.device, mode=mode)
		if frame is not None:
			if self.device.registry.transmit(frame.frame) != len(frame.frame):
				return False
			return True
		return False

	async def set_hdcp_mode(self, mode:MultiviewerHDCPMode) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		if (self.hdcp_mode == mode):
			return True
		frame = FrameV2IPMultiviewer.construct_set_hdcp_mode(mxr=self.device.registry, target=self.device, mode=mode)
		if frame is not None:
			if self.device.registry.transmit(frame.frame) != len(frame.frame):
				return False
			return True
		return False

	async def set_connected_source(self, input:int, source:MxrDeviceUid|None) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		current = self.connected_source(input=input)
		if ((current is None) and (source is not None)) or ((current is not None) and (source is None)) or (current != source):
			frame = FrameV2IPMultiviewer.construct_set_connected_source(mxr=self.device.registry, target=self.device, input=input, source=source)
			if frame is not None:
				if self.device.registry.transmit(frame.frame) != len(frame.frame):
					return False
				return True
		return False

	async def auto_route(self) -> bool:
		if not self.device.is_oneip_multiviewer:
			return False
		frame = FrameV2IPMultiviewer.construct_auto_route(mxr=self.device.registry, target=self.device)
		if frame is not None:
			if self.device.registry.transmit(frame.frame) != len(frame.frame):
				return False
			return True
		return False
