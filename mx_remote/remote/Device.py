######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Device implementation for MX Remote network devices (matrix, OneIP, amplifier).'''

from .Bay import Bay, _AUDIO_FOLLOWS_SINCE
from ..Interface import (
	MxrCallbacks,
	OneIPStreamSources,
	OneIPPtpMessages,
	OneIPPtpState,
	OneIPDownmix,
	OneIPDscpConfig,
	UnitNetConfig,
	UnitStatus,
	AmpDolbySettings,
	DeviceStatus,
	DeviceOneIPDetails,
	DeviceOneIPSink,
	SystemTemperature,
	OneIPStreamSourcesList,
	Multiviewer,
	AudioEndpoint,
	AudioEndpoints,
	AudioFeatures,
	AudioChangeSource,
	AudioLinks,
	DeviceOneIPScalingSettings,
	OneIPDeviceSettings,
	OneIPPowerSaveSchedule,
	OneIPVlan,
	OneIPTestcard,
	OneIPSinkSdp,
	OneIPPrivacy,
	OsdSync,
	OsdSyncReport,
	OsdMessage,
	OneIPTestSync,
	OneIPTestTone,
	TimeZone,
	DeviceClock,
	OneIPOutputMode,
	OneIPScalingSettings,
	MeshControllerReport,
	BayMirrorStatus,
	FilteredDevices,
	oneip_stream_valid,
)
from ..proto.BayConfig import BayConfig
from ..proto.FrameHello import FrameHello
from ..proto.FrameMeshOperation import AUTO_ADDRESSES_PROTOCOL, MeshOperation, FrameMeshOperation
from ..proto.FrameMirrorStatus import FrameMirrorStatus
from ..proto.FrameFilterStatus import FrameFilterStatus
from ..proto.FrameV2IPTiling import FrameV2IPTiling
from ..proto.FrameV2IPSourceSwitch import FrameV2IPSourceSwitch
from ..proto.FrameRCSettings import FrameRCSettings
from ..proto.FrameV2IPStats import FrameV2IPStats
from ..proto.FrameNetworkStatus import NetworkPortStatus, NetworkPortStatusImpl
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
from ..Uid import MxrDeviceUid, MxrBayUid
from typing import Any, Callable
from ..compat import override
from dataclasses import replace
from datetime import datetime
from enum import Enum
import ipaddress
import logging
import time

from ..Interface import DeviceBase, BayBase, DeviceRegistry
from ..proto.FrameBase import FrameBase
from ..proto.Constants import (MXR_PROTOCOL_VERSION_SLOW_HELLO, ONEIP_DOWNMIX_LFE_MAX, ONEIP_LOCALE_UNKNOWN, OSD_MESSAGE_TEXT_MAX, OsdMessageFlag, OsdMessagePriority, BayFeaturesMask, DeviceFeature, Endpoints, MxrSignalType, OneIPDeviceSetting, OneIPVideoProcessorFeature, OneIPVlanFlag,
                              OneIPTestPattern, OneIPToneMode,
                              MXR_SCALING_FLAG_AUTO_SCALING, MXR_SCALING_FLAG_MODE_VALID,
                              MXR_SCALING_FLAG_OPTIONS_VALID, MXR_SCALING_FLAG_OPTIONS2_VALID,
                              MXR_SCALING_FLAG_MATCH_SOURCE, MXR_SCALING_FLAG_SKIP_420,
                              MXR_SCALING_OPTIONS2_SETTINGS, ONEIP_DEVICE_SETTING_SWITCHES,
                              ONEIP_IR_PROFILE_MAX, ONEIP_IR_PROFILE_NOT_SET, ONEIP_VLAN_PORT_SFP,
                              ONEIP_DEVICE_SETTINGS_BLOCK, ONEIP_DSCP_MAX,
                              ONEIP_PTP_DOMAIN_MAX, ONEIP_SDP_MAX, OneIPPowerSaveLevel, OneIPPtpFlag, OneIPPtpMode, UnitCommandFlag,
                              UnitCommandKind, UnitFlag, ONEIP_SOURCE_FILTER_MAX, MXR_RC_STATUS_MAX,
                              MXR_RC_STATUS_NAME_LEN, RCType)
from ..proto.FrameUnitCommand import FrameUnitCommand
from ..proto.FrameV2IPAudio import AUDIO_LAYOUT_SINCE, AUDIO_REPORT_GUARD, AudioEndpointImpl, FrameV2IPAudio
from ..proto.FrameV2IPDeviceConfiguration import FrameV2IPDeviceConfiguration
from ..proto.FrameV2IPPowerSave import FrameV2IPPowerSave
from ..proto.FrameV2IPOsdSync import FrameV2IPOsdSync, OSD_KIND_MESSAGE_REQUEST, OSD_KIND_MESSAGE_SET
from ..proto.FrameV2IPPrivacy import FrameV2IPPrivacy
from ..proto.FrameV2IPSinkSdp import (FrameV2IPSinkSdp, SdpDescriptionPage, SDP_DESCRIPTION_PROTOCOL, SDP_PAGE_TIMEOUT,
                                      SDP_REQUEST, SDP_REQUEST_DESCRIPTION, SDP_SCREEN, SDP_STOP)
from ..proto.FrameV2IPTestcard import (FrameV2IPTestcard, TESTCARD_REQUEST, TESTCARD_SET,
                                       TESTCARD_PART_PATTERN, TESTCARD_PART_TONE, TESTCARD_PART_SYNC)

_LOGGER = logging.getLogger(__name__)

FIXED_PORTS_SINCE = 0x2B
'''The protocol from which a OneIP unit numbers its ports PortLayout.FIXED.'''

_ONEIP_BAYS = 127
'''The bays a OneIP unit numbers in each direction.'''

_SPLIT_FIRST = 16
'''The bays of each direction that come first in PortLayout.SPLIT.'''

class PortLayout(Enum):
	'''How a OneIP unit numbers the ports of its bays.'''
	FIXED = 0
	'''Input n on port n, output n on port 127 + n.'''
	SPLIT = 1
	'''Inputs 0-15 on ports 0-15 and outputs 0-15 on 16-31, then inputs 16-126
	on 32-142 and outputs 16-126 on 143-253.'''

	def decode(self, port:int) -> tuple[bool, int]|None:
		'''Whether port is an input's, and that bay's number. A port past the
		last output reads as an output numbered past the last bay, which encode()
		gives no port.'''
		if (self == PortLayout.FIXED and 0 <= port <= 126) or (self == PortLayout.SPLIT and 0 <= port <= 15):
			return (True, port)
		if (self == PortLayout.SPLIT) and (16 <= port <= 31):
			return (False, port - 16)
		if (self == PortLayout.SPLIT) and (32 <= port <= 142):
			return (True, port - 16)
		if (port < 127):
			return None
		return (False, port - 127)

	def encode(self, is_input:bool, bay:int) -> int|None:
		'''The port of input or output bay, None past the last bay.'''
		if not (0 <= bay < _ONEIP_BAYS):
			return None
		if (self == PortLayout.FIXED):
			return bay if is_input else (bay + 127)
		if (bay < _SPLIT_FIRST):
			return bay if is_input else (bay + _SPLIT_FIRST)
		return (bay + _SPLIT_FIRST) if is_input else (bay + 127)

_SCALING_WRITE_PROTOCOL = 0x2F
'''The protocol from which a unit applies a scaling write from management.'''

PATH_WINDOW = 120.0
'''How long a frame by one endpoint counts as proof that a device is heard by
it, in seconds.'''

FORGET_WINDOWS = 3
'''How many offline windows of silence a device is forgotten after, as a unit
forgets one.'''

_UPLINK_REPORT_LEN = 144
'''The length a unit requires of a network status report before it takes the
IGMP querier from it.'''

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
		# Whether the device's bays have come into use, as a unit judges it: by
		# a OneIP device's source list, or by any other device's primary bay
		# list, since it registered, last announced a reboot or last went
		# offline.
		self._bays_arrived = False
		self._last_ping = datetime.now()
		# When a frame from this device last arrived by multicast, and by
		# broadcast, as time.time().
		self._heard_multicast:float|None = None
		self._heard_broadcast:float|None = None
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
		self._v2ip_ptp:OneIPPtpState|None = None
		self._v2ip_downmix:OneIPDownmix|None = None
		self._v2ip_locale:int|None = None
		self._v2ip_preview:str|None = None
		self._unit_status:UnitStatus|None = None
		self._v2ip_testcard:OneIPTestcard|None = None
		self._v2ip_sink_sdp:OneIPSinkSdp|None = None
		self._v2ip_sink_description:str|None = None
		# The pages of a description the output is still sending: its whole
		# length, the bytes received so far from offset 0, and when the last
		# page arrived.
		self._v2ip_sink_description_pages:tuple[int, bytes, float]|None = None
		self._v2ip_privacy:OneIPPrivacy|None = None
		self._osd_sync:OsdSync|None = None
		self._osd_sync_report:OsdSyncReport|None = None
		self._osd_message:OsdMessage|None = None
		self._time_zone:TimeZone|None = None
		self._clock:DeviceClock|None = None
		self._mesh_master_uid:MxrDeviceUid|None = None
		self._mesh_controller_report:MeshControllerReport|None = None
		# The source device behind each OneIP bay, by bay mode and number. Held
		# here as well as on the bays because a device may send its mappings
		# before the bay configuration that creates those bays, and a bay that
		# arrives later picks its mapping up from here.
		# Bay mapping pages whose first port names no bay yet, by that port. A
		# page runs on by bay number from the bay at its first port, so it cannot
		# be filed until that bay's configuration says which one it is.
		self._v2ip_versions:dict[FirmwareType,FirmwareVersion] = {}
		self._audio_endpoints:AudioEndpoints|None = None
		# Whether the audio module uses the layout of released firmware up to
		# 4.4.2, as the device's own features report showed; None before one.
		self._audio_legacy:bool|None = None
		# When this client last sent the device an audio command, and when the
		# device's features report was last taken, as time.time() read them.
		self._audio_commanded:float|None = None
		self._audio_reported:float|None = None
		self._sys_status:int|None = None
		self._sys_message:str|None = None
		self._topology:list[TopologyEntry]|None = None
		# The last topology list as it arrived, padding included, which is
		# what a unit compares the next one against.
		self._topology_raw = b''
		# The IGMP querier the last uplink report named, as a unit stores it.
		self._igmp_querier:str|None = None
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
	def offline_window(self) -> int:
		'''How long the device may stay silent before it counts as offline, in
		seconds, which a unit sets by the protocol the device announces.'''
		if (self.protocol >= MXR_PROTOCOL_VERSION_SLOW_HELLO):
			return 60
		if (self.protocol >= 0x20):
			return 15
		return 180

	@property
	def online(self) -> bool:
		'''Check whether this device has pinged recently.'''
		return ((datetime.now() - self._last_ping).total_seconds() < self.offline_window)

	@property
	def forgotten(self) -> bool:
		'''Whether the device has been silent for FORGET_WINDOWS offline
		windows, after which a unit forgets it.'''
		return ((datetime.now() - self._last_ping).total_seconds() >= (self.offline_window * FORGET_WINDOWS))

	def keep_alive(self) -> None:
		'''Note a frame from the device: one still counted alive stays so,
		whatever the frame carries. Once it has gone silent long enough to count
		as offline, only a hello brings it back.'''
		if self.online:
			self._last_ping = datetime.now()

	@property
	@override
	def bays_online(self) -> bool:
		return self._bays_arrived and self.online

	@property
	@override
	def multicast(self) -> bool|None:
		if not getattr(self._registry, 'paths_known', False):
			return None
		return not self.broadcast_only(time.time())

	@property
	@override
	def raw_name(self) -> bytes:
		return self._hello.raw_device_name

	@property
	@override
	def raw_version(self) -> bytes:
		return self._hello.raw_version

	@property
	@override
	def raw_serial(self) -> bytes:
		return self._hello.raw_serial

	@property
	@override
	def igmp_querier(self) -> str|None:
		return self._igmp_querier

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

	def heard_on(self, path:Endpoints, stamped:float) -> None:
		'''Record that a frame from this device arrived by path at stamped.'''
		if (path == Endpoints.MULTICAST):
			self._heard_multicast = stamped
		elif (path == Endpoints.BROADCAST):
			self._heard_broadcast = stamped

	def broadcast_only(self, now:float) -> bool:
		'''Whether no frame from this device has arrived by multicast within
		PATH_WINDOW, as a unit judges a peer it must also reach by broadcast.'''
		return (self._heard_multicast is None) or ((now - self._heard_multicast) >= PATH_WINDOW)

	def heard_broadcast_lately(self, now:float) -> bool:
		'''Whether a frame from this device arrived by broadcast within PATH_WINDOW.'''
		return (self._heard_broadcast is not None) and ((now - self._heard_broadcast) < PATH_WINDOW)

	def heard_path(self, now:float) -> Endpoints:
		'''The endpoint this device is heard by, as a unit picks the one for a
		frame meant for it alone: broadcast while it is broadcast-only.'''
		return Endpoints.BROADCAST if self.broadcast_only(now) else Endpoints.MULTICAST

	def check_online(self) -> None:
		# A bay list from a device gone silent still brings its bays in, and
		# the next pass takes them out again, as a unit's does.
		if not self.online:
			self._bays_arrived = False
		if self.online != self._online:
			self._online = not self._online
			if not self._online:
				self._await_config()
			self.callbacks.on_device_online_status_changed(self, self._online)
			self.call_callbacks()

	def _await_config(self) -> None:
		'''Treat the device as undescribed until it sends its bays again, as a
		unit does for one that went offline or rebooted.'''
		self._have_config = False
		self._bay_config_received = False
		self._bays_arrived = False

	@override
	def note_link_config(self) -> None:
		'''Note that the device has reported its link configuration.'''
		if self._link_config_received:
			return
		self._link_config_received = True
		self._check_config_complete()

	@override
	def note_bays_listed(self) -> None:
		'''Note a primary bay list holding a record. A unit takes a OneIP
		device's bays as arrived with its source list instead.'''
		if not self.is_oneip:
			self._bays_arrived = True

	def note_topology(self, raw:bytes) -> bool:
		'''Record a topology list as it arrived, returning whether it differs
		byte for byte from the last, which is when a unit reshapes its
		registry by it.'''
		if (raw == self._topology_raw):
			return False
		self._topology_raw = raw
		return True

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
		# Whatever it lists, as a unit takes it: a device that is not a OneIP
		# one is not brought online by this frame.
		if self.is_oneip:
			self._bays_arrived = True
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
	def oneip_ptp(self) -> OneIPPtpState|None:
		return self._v2ip_ptp

	@property
	@override
	def oneip_downmix(self) -> OneIPDownmix|None:
		return self._v2ip_downmix

	@property
	@override
	def oneip_locale(self) -> int|None:
		return self._v2ip_locale

	@property
	@override
	def oneip_preview(self) -> str|None:
		return self._v2ip_preview

	@property
	@override
	def unit_status(self) -> UnitStatus|None:
		return self._unit_status

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
	def mesh_controller_report(self) -> MeshControllerReport|None:
		'''What this device last announced about itself as a mesh controller,
		None until it has.'''
		return self._mesh_controller_report

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

	@property
	def port_layout(self) -> 'PortLayout':
		'''How the unit numbers its bays' ports, as its protocol says.'''
		return PortLayout.FIXED if (self.protocol >= FIXED_PORTS_SINCE) else PortLayout.SPLIT

	def local_bay(self, is_input:bool) -> BayBase|None:
		'''The unit's own bay 0 in the given direction, which its mesh bays on
		other units stand for.'''
		for bay in self.bays.values():
			if bay.is_local and (bay.is_input if is_input else bay.is_output):
				return bay
		return None

	def routed_source(self, port:int) -> BayBase|int|None:
		'''The bay a routing report names by port: the bay, or for a OneIP
		unit's input port with no bay yet the port itself, since a unit sends
		its bay configuration ahead of the mappings that create its mesh bays.
		None for a port that names no input.'''
		if ((bay := self.get_by_portnum(port)) is not None):
			return bay
		if self.is_oneip and ((decoded := self.port_layout.decode(port)) is not None) and decoded[0]:
			return port
		return None

	def _apply_v2ip_bay_mapping_page(self, first_port:int, page:list[MxrDeviceUid]) -> None:
		'''Take one page of the unit's OneIP bay mappings: the unit owning each
		bay from the one on first_port on.

		The entries run on by bay number in the direction of the first bay,
		which is a run of ports only in some numberings. The unit's own bays
		come from its bay configuration, and an entry naming the unit itself is
		one of them. Every other entry is a mesh bay, which a page creates. A
		zero uid maps nothing: released firmware counts more bays than it has,
		and sends one for each extra. The page ends past the last bay.
		'''
		layout = self.port_layout
		if ((decoded := layout.decode(first_port)) is None):
			return
		is_input, first = decoded
		for offset, owner in enumerate(page):
			if ((port := layout.encode(is_input, first + offset)) is None):
				break
			if owner.empty or (owner == self.remote_id):
				continue
			bay = self.get_by_portnum(port)
			if (bay is None):
				bay = Bay.mesh(dev=self, port=port, is_input=is_input, number=first + offset, owner=owner)
				self.bays[port] = bay
				self.callbacks.on_bay_registered(bay)
				self._adopt_pending_routes(bay)
				self.call_callbacks()
			elif (bay.oneip_uid != owner):
				# The bay now describes another unit's bay, under that one's name.
				bay.oneip_uid = owner # pyright: ignore[reportAttributeAccessIssue]
				self.callbacks.on_name_changed(bay, bay.user_name)
				self.call_callbacks()

	def _adopt_pending_routes(self, source:BayBase) -> None:
		'''Hand a newly created bay to the outputs whose route named its port
		before it existed.'''
		for bay in self.bays.values():
			if isinstance(bay, Bay):
				bay.adopt_pending_source(source)

	def _may_have_restarted(self, hello_frame:FrameHello) -> bool:
		'''Whether a hello shows the device may have restarted since it was
		last heard: it was offline, its reboot toggle flipped, or it is about
		to reboot.'''
		before = self._hello.features or DeviceFeature(0)
		now = hello_frame.features or DeviceFeature(0)
		return (not self.online) \
			or ((DeviceFeature.BOOT_BIT in before) != (DeviceFeature.BOOT_BIT in now)) \
			or (DeviceFeature.STATUS_REBOOTING in now)

	def _on_mxr_mesh_operation(self, frame:FrameMeshOperation) -> None:
		'''A mesh operation this device sent.

		Its membership report names the controller it follows, and its controller
		report is filed only when it is about this device itself. Every other
		operation reaches the caller as it arrived, so a controller can follow
		promotions and registrations it did not send.'''
		if ((message := frame.message) is None):
			return
		if (message.operation == MeshOperation.REPORT_MEMBERSHIP):
			self.mesh_master = message.target
		elif (message.operation == MeshOperation.REPORT_CONTROLLER):
			report = frame.controller_report
			if (message.target == self.remote_id) and (report != self._mesh_controller_report):
				self._mesh_controller_report = report
				self.call_callbacks()
		else:
			self.callbacks.on_mesh_operation(self, message)

	def _on_mxr_hello(self, hello_frame:FrameHello) -> None:
		# received a new hello frame from this device. update local info
		# A source unit's video processor picks a new key generator every boot,
		# and the reports it sent while it could not be heard are lost, so what
		# it reported before would decrypt its new streams as noise.
		dropped = (self._v2ip_privacy is not None) and self._may_have_restarted(hello_frame)
		if dropped:
			self._v2ip_privacy = None
		self._last_ping = datetime.now()
		changed = (self._hello != hello_frame)
		# A unit about to reboot says so in its hello, and what it said about
		# its bays holds only until it has said it again.
		if (hello_frame.features is not None) and (DeviceFeature.STATUS_REBOOTING in hello_frame.features):
			self._await_config()
		self._hello = hello_frame
		self._rebooting = False
		if changed:
			# tell callbacks that this device changed
			self.callbacks.on_device_config_changed(self)
			self.call_callbacks()
		elif dropped:
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
		# A record with an empty name describes no bay: a unit sends one, all
		# zero, for an input it cannot number. So is a record for a OneIP bay
		# standing for another unit: what it says about that unit's bay is never
		# refreshed, and the bay is built from the bay mappings instead.
		if (data.bay_name == '') or (BayFeaturesMask.ONEIP_SOURCE_REMOTE in data.features) \
				or (BayFeaturesMask.ONEIP_SINK_REMOTE in data.features):
			return
		bay = self.get_by_portnum(data.port)
		isnew = (bay is None)
		if bay is None:
			bay = Bay(dev=self, data=data)
			self.bays[data.port] = bay
		bay.on_mxr_update(data)
		# A unit maps its own OneIP bay to itself.
		if bay.is_oneip_source or bay.is_oneip_sink:
			bay.oneip_uid = self.remote_id # pyright: ignore[reportAttributeAccessIssue]
		if isnew:
			self.callbacks.on_bay_registered(bay)
			self._adopt_pending_routes(bay)
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

	@property
	@override
	def audio_endpoints(self) -> AudioEndpoints|None:
		return self._audio_endpoints

	@property
	@override
	def audio_reported(self) -> float|None:
		return self._audio_reported

	def audio_commanded(self) -> None:
		'''Record that an audio command to the device has just gone out, which
		starts AUDIO_REPORT_GUARD.'''
		self._audio_commanded = time.time()

	def _audio_guarded(self, received:float|None) -> bool:
		'''Whether a report received then falls within AUDIO_REPORT_GUARD of
		the last audio command; one stamped before the command does too.'''
		return (received is not None) and (self._audio_commanded is not None) \
			and (max(received - self._audio_commanded, 0.0) < AUDIO_REPORT_GUARD)

	def hold_audio_route(self, sink:int, source:int) -> None:
		'''Hold a sent route of endpoint source alone to endpoint sink as the
		device's routing, until it reports its endpoints again; nothing for a
		sink that reported no routes.'''
		ep = self.audio_endpoint_by_id(sink)
		if not isinstance(ep, AudioEndpointImpl) or (ep.in_routes_supported is None) or (source >= 32):
			return
		if (ep.in_routes != (1 << source)):
			ep.in_routes = (1 << source)
			self.call_callbacks()

	def _hold_audio_switch(self, endpoint:int, feature:int, on:bool) -> None:
		'''Hold a sent mute, trigger or lock as the endpoint's status, until the
		device reports its endpoints again; nothing for one that reported no
		status.'''
		ep = self.audio_endpoint_by_id(endpoint)
		if (ep is None) or (ep.status is None):
			return
		bits = (ep.status.value | feature) if on else (ep.status.value & ~feature)
		if (bits != ep.status.value):
			ep.status = AudioFeatures(value=bits)
			self.call_callbacks()

	@property
	def audio_legacy(self) -> bool:
		'''Whether the audio module speaks the layout of released firmware up to
		4.4.2: as its features report showed, or before one, for a unit below
		AUDIO_LAYOUT_SINCE.'''
		if (self._audio_legacy is not None):
			return self._audio_legacy
		return self.protocol < AUDIO_LAYOUT_SINCE

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
			self._on_mxr_mesh_operation(data)
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
		elif isinstance(data, UnitStatus):
			if (self._unit_status != data):
				self._unit_status = data
				self.call_callbacks()
		elif isinstance(data, OneIPPtpState):
			# A block without its valid bit is the device reporting no state.
			ptp = data if (OneIPPtpFlag.VALID in data.flags) else None
			if (self._v2ip_ptp != ptp):
				self._v2ip_ptp = ptp
				self.call_callbacks()
		elif isinstance(data, FrameV2IPDeviceConfiguration):
			self._on_oneip_downmix(data.downmix, reported=data.target_self)
			if data.carries_locale:
				self._on_oneip_locale(data.locale, reported=data.target_self)
			# Only the device reports where it sends its preview.
			if data.target_self and (self._v2ip_preview != data.preview):
				self._v2ip_preview = data.preview
				self.call_callbacks()
		elif isinstance(data, OneIPTestcard):
			if (self._v2ip_testcard != data):
				self._v2ip_testcard = data
				self.call_callbacks()
		elif isinstance(data, OsdSync):
			self._osd_sync = data
			self.callbacks.on_osd_sync(self, data)
			self.call_callbacks()
		elif isinstance(data, OsdSyncReport):
			if (self._osd_sync_report != data):
				self._osd_sync_report = data
				self.callbacks.on_osd_sync_report(self, data)
		elif isinstance(data, OsdMessage):
			if (self._osd_message != data):
				self._osd_message = data
				self.callbacks.on_osd_message_changed(self, data)
				self.call_callbacks()
		elif isinstance(data, OneIPSinkSdp):
			changed = (self._v2ip_sink_sdp != data)
			self._v2ip_sink_sdp = data
			if not data.active:
				# A description is reported when a stream starts, so one that
				# has stopped leaves none behind it.
				self._v2ip_sink_description_pages = None
				changed |= (self._v2ip_sink_description is not None)
				self._v2ip_sink_description = None
			if changed:
				self.call_callbacks()
		elif isinstance(data, SdpDescriptionPage):
			self._on_sink_description_page(data)
		elif isinstance(data, OneIPPrivacy):
			if (self._v2ip_privacy != data):
				self._v2ip_privacy = data
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
			self._apply_v2ip_bay_mapping_page(first_port, data.bays)
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
			if self._audio_guarded(data.received):
				return
			if (data.received is not None):
				self._audio_reported = data.received
			# A device answers a lock by re-sending its tree, so a report whose
			# only change is an endpoint's status is still a change.
			previous = self._audio_endpoints
			changed = (previous is None) or (previous != data) or not previous.same_status(data)
			self._audio_endpoints = data
			if (data.legacy_layout is not None):
				self._audio_legacy = data.legacy_layout
			if (self.is_oneip_tz or self.is_oneip_tx):
				first_input = self.first_input
				first_ep = data.tree_first_output
				if (first_input is not None):
					first_input.audio_endpoint = first_ep # pyright: ignore[reportAttributeAccessIssue]
				# A OneIP unit's own input is its first, but a multiviewer's
				# outputs are all mesh sinks it shows, owned by other units.
				first_output = self.first_output
				first_ep = data.tree_first_input
				if (first_output is not None) and first_output.is_local:
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
			if self._audio_guarded(data.received):
				return
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
		# A unit takes the querier from a whole uplink report of the current
		# layout alone, and keeps it across the reports of its other ports.
		if isinstance(status, NetworkPortStatusImpl) and (len(status.data) >= _UPLINK_REPORT_LEN) \
				and status.features_status.port_uplink:
			self._igmp_querier = status.querier
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
		'''Send a reboot command to the device.

		A device on protocol 0x2C or later takes it only from its mesh
		controller or a management application, which this client announces
		itself as.'''
		frame = FrameReboot.construct(mxr=self.registry, target=self)
		if frame is not None:
			if self.registry.transmit(frame.frame) != len(frame.frame):
				return False
			self._rebooting = True
			return True
		return False

	async def clear_unit_status(self) -> bool:
		'''Clear this unit's current system status. The terms of
		upgrade_unit_video_processor() apply.'''
		return self._unit_command(UnitCommandKind.CLEAR_STATUS)

	async def upgrade_unit_video_processor(self, force:bool=False) -> bool:
		'''Upgrade this unit's video processor to the latest image it holds, or
		flash that image again when force is set and it already runs it.

		Nothing acknowledges it: unit_status reads what the unit reports next.
		False for a device that is not a OneIP unit, and for one below 0x2C,
		which predates the command.
		'''
		flags = UnitCommandFlag.FORCE if force else UnitCommandFlag(0)
		return self._unit_command(UnitCommandKind.VIDEO_PROCESSOR_UPGRADE, flags)

	async def set_unit_dhcp(self) -> bool:
		'''Switch this unit to an IP configuration from DHCP. The terms of
		set_unit_network() apply.'''
		return self._unit_command(UnitCommandKind.NET_CONFIG, UnitCommandFlag.DHCP, UnitNetConfig())

	async def set_unit_network(self, network:UnitNetConfig) -> bool:
		'''Give this unit a static IP configuration.

		The address must be one a unit can hold and the netmask a run of ones
		from the top; anything else is refused before it is sent.

		The unit applies the change at once and reverts it unless its mesh
		controller, hearing the unit report it, confirms it in time.
		unit_status.network_pending says whether it still waits, and
		confirm_unit_network() confirms it. Otherwise as
		upgrade_unit_video_processor().
		'''
		if not network.is_valid():
			_LOGGER.warning(f"not setting network [{network}] on {self}: not an address and netmask a unit can hold")
			return False
		return self._unit_command(UnitCommandKind.NET_CONFIG, network=network)

	async def confirm_unit_network(self) -> bool:
		'''Keep this unit's pending IP configuration, as its mesh controller does
		when it hears the unit at its new address. The terms of
		upgrade_unit_video_processor() apply.'''
		return self._unit_command(UnitCommandKind.NET_CONFIRM)

	async def locate_unit(self, timed:bool=False) -> bool:
		'''Locate this unit: its board-ID LED flashes, and an output shows
		"Locate Device" on its display. For 30 s when timed is set, until
		stop_locating_unit() otherwise.

		Refused until the unit has reported its status, and for one whose report
		lacks UnitFlag.LOCATE_SUPPORTED. The cached status takes UnitFlag.LOCATE
		at once, as the mesh controller's copy does; the unit reports its own
		within 2 s, and again when a timed locate ends. Otherwise as
		upgrade_unit_video_processor().
		'''
		return self._locate(UnitCommandFlag.LOCATE_TIMED if timed else UnitCommandFlag.LOCATE_ON)

	async def stop_locating_unit(self) -> bool:
		'''Stop locating this unit. As locate_unit().'''
		return self._locate(UnitCommandFlag(0))

	def _locate(self, flags:UnitCommandFlag) -> bool:
		'''The one send behind the locate methods.'''
		if ((status := self._unit_status) is None):
			_LOGGER.warning(f"not locating {self}: it has not reported its status")
			return False
		if (UnitFlag.LOCATE_SUPPORTED not in status.flags):
			_LOGGER.warning(f"not locating {self}: it cannot be located")
			return False
		if not self._unit_command(UnitCommandKind.LOCATE, flags):
			return False
		located = int(status.flags) & ~int(UnitFlag.LOCATE)
		if flags:
			located |= int(UnitFlag.LOCATE)
		self.on_mxr_update(replace(status, flags=UnitFlag(located)))
		return True

	def _unit_command(self, command:UnitCommandKind, flags:UnitCommandFlag=UnitCommandFlag(0),
	                  network:UnitNetConfig|None=None) -> bool:
		'''The one send behind the unit command methods.'''
		if not self.is_oneip:
			_LOGGER.warning(f"not sending {command.name} to {self}: not a OneIP unit")
			return False
		frame = FrameUnitCommand.construct(mxr=self.registry, target=self, command=command,
		                                   flags=flags, network=network)
		if (frame is None):
			return False
		return (self.registry.transmit(frame.frame) == len(frame.frame))

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
		return (self.registry.transmit(frame.frame, to=self) == len(frame.frame))

	async def mesh_promote(self) -> bool:
		'''Promote this device to mesh controller.'''
		frame = FrameMeshOperation.construct(mxr=self.registry, target=self, operation=MeshOperation.PROMOTE_CONTROLLER)
		if frame is not None:
			if self.registry.transmit(frame.frame) != len(frame.frame):
				return False
			return True
		return False

	async def auto_assign_oneip_source_addresses(self) -> bool:
		'''Hand this OneIP source's stream addresses back to automatic assignment,
		undoing addresses that were set on it by hand.

		The device takes this only from management, which this client announces
		itself as. Nothing acknowledges it: the device's next configuration
		report carries the addresses it ends up with, and oneip_details reads
		them.

		Refused for a device that is not a OneIP source, and for one below
		protocol 0x2B, which predates the operation and ignores it.
		'''
		if (self.features is None) or (DeviceFeature.ONEIP_SOURCE not in self.features):
			_LOGGER.warning(f"not handing the addresses of {self} back to automatic assignment: it is not a OneIP source")
			return False
		if (self.protocol != 0) and (self.protocol < AUTO_ADDRESSES_PROTOCOL):
			_LOGGER.warning(f"not handing the addresses of {self} back to automatic assignment: it advertises "
			                f"protocol {self.protocol:02X} and the operation needs {AUTO_ADDRESSES_PROTOCOL:02X}")
			return False
		frame = FrameMeshOperation.construct(mxr=self.registry, target=self, operation=MeshOperation.AUTO_ADDRESSES)
		if (frame is None):
			return False
		return self.registry.transmit(frame.frame) == len(frame.frame)

	def _oneip_output(self, what:str) -> BayBase|None:
		'''This device's output bay, which holds what is set about a OneIP
		output, or None with a warning when it is not a OneIP output whose bay
		has been reported.'''
		if not self.is_oneip_sink:
			_LOGGER.warning(f"not setting {what} on {self}: not a OneIP output")
			return None
		if ((bay := self.first_output) is None):
			_LOGGER.warning(f"not setting {what} on {self}: its output bay has not been reported")
			return None
		return bay

	async def set_oneip_mirroring(self, mirrored:'DeviceBase|None') -> bool:
		'''Have this OneIP output mirror another, or None to stop mirroring.

		Every unit hears it and keeps it, and the output follows the one it
		mirrors. A unit takes it only from its mesh controller or a management
		application. Refused unless both are OneIP outputs whose bays have been
		reported, and unless they differ. The output's mirroring reads what was
		set once the frame is away, until its own report replaces it.
		'''
		if ((bay := self._oneip_output("mirroring")) is None):
			return False
		if (mirrored is not None):
			if (mirrored.remote_id == self.remote_id):
				_LOGGER.warning(f"not setting mirroring on {self}: an output cannot mirror itself")
				return False
			if not isinstance(mirrored, Device) or (mirrored._oneip_output("mirroring") is None):
				return False
		frame = FrameMirrorStatus.construct(mxr=self.registry, target=self,
		                                    mirrored=(mirrored.remote_id if (mirrored is not None) else None))
		if (frame is None) or (self.registry.transmit(frame.frame) != len(frame.frame)):
			return False
		bay.on_mxr_update(BayMirrorStatus(MxrBayUid(mirrored.remote_id, 0)) if (mirrored is not None)
		                  else BayMirrorStatus())
		return True

	async def set_oneip_source_filter(self, filtered:list[MxrDeviceUid]) -> bool:
		'''Replace the list of sources this OneIP output may not show.

		A unit takes it only from its mesh controller or a management
		application, and only whole, so a list longer than
		ONEIP_SOURCE_FILTER_MAX is refused, as is a device that is not a OneIP
		output with a reported bay. The output's filtered list reads what was set
		once the frame is away.
		'''
		if (len(filtered) > ONEIP_SOURCE_FILTER_MAX):
			_LOGGER.warning(f"not setting the source filter on {self}: {len(filtered)} sources, "
			                f"and one frame holds {ONEIP_SOURCE_FILTER_MAX}")
			return False
		if ((bay := self._oneip_output("the source filter")) is None):
			return False
		frame = FrameFilterStatus.construct(mxr=self.registry, target=self, filtered=filtered)
		if (frame is None) or (self.registry.transmit(frame.frame) != len(frame.frame)):
			return False
		bay.on_mxr_update(FilteredDevices(b''.join(MxrDeviceUid(u).byte_value for u in filtered)))
		return True

	async def set_oneip_tiling(self, pos_x:int, pos_y:int, width:int, height:int) -> bool:
		'''Set the part of a video wall this OneIP output shows: the window of
		the picture it crops and scales up, each value 16 bits.

		The output takes it only from its mesh controller or a management
		application, and a video wall module loaded on it replaces it within a
		second. Refused unless this is a OneIP output.
		'''
		if not self.is_oneip_sink:
			_LOGGER.warning(f"not setting tiling on {self}: not a OneIP output")
			return False
		if not all(0 <= v <= 0xFFFF for v in (pos_x, pos_y, width, height)):
			_LOGGER.warning(f"not setting tiling on {self}: each value must fit 16 bits")
			return False
		frame = FrameV2IPTiling.construct(mxr=self.registry, target=self, pos_x=pos_x, pos_y=pos_y,
		                                  width=width, height=height)
		if (frame is None):
			return False
		return (self.registry.transmit(frame.frame) == len(frame.frame))

	def _own_source_streams(self, what:str) -> OneIPStreamSources|None:
		'''The streams this unit advertises for an input of its own, rather
		than for a mesh bay standing for another unit's, or None with a warning
		when it has none or has not reported them.'''
		if ((bay := self.first_input) is None) or not bay.is_local:
			_LOGGER.warning(f"not {what} {self}: it has no input of its own")
			return None
		if ((streams := self.oneip_source(bay)) is None):
			_LOGGER.warning(f"not {what} {self}: it has not reported its stream addresses")
			return None
		return streams

	def _send_source_switch(self, video:str, audio:str, power_on:bool) -> bool:
		'''Send this OneIP output a source switch naming the given groups.'''
		frame = FrameV2IPSourceSwitch.construct(mxr=self.registry, target=self, video=video, audio=audio,
		                                        power_on=power_on)
		if (frame is None):
			return False
		return (self.registry.transmit(frame.frame) == len(frame.frame))

	@override
	async def route_oneip_unit(self, video:DeviceBase, audio:DeviceBase|None=None, power_on:bool=True) -> bool:
		'''Route this OneIP output to the streams a source unit advertises for
		its own input, as a mesh controller does.

		The frame names the stream addresses, so the output plays them whether
		or not it lists the source. With audio, the audio comes from that
		unit's own input in the same frame; without, it follows the video as
		for Bay.select_video_source. power_on has the output power its display
		on with the switch. Refused unless this is a OneIP output and each
		source has reported the streams of an input of its own.
		'''
		if not self.is_oneip_sink:
			_LOGGER.warning(f"not routing {self}: not a OneIP output")
			return False
		if not isinstance(video, Device) or ((streams := video._own_source_streams("routing from")) is None):
			return False
		if (audio is not None):
			if not isinstance(audio, Device) or ((audio_streams := audio._own_source_streams("taking audio from")) is None):
				return False
			audio_ip = audio_streams.audio.ip
		elif (self.protocol < _AUDIO_FOLLOWS_SINCE):
			# see Bay.select_video_source: these units route no audio otherwise
			audio_ip = streams.audio.ip
		else:
			audio_ip = '0.0.0.0'
		return self._send_source_switch(video=streams.video.ip, audio=audio_ip, power_on=power_on)

	@override
	async def route_oneip_unit_with_arc(self, video:DeviceBase, arc_owner:DeviceBase, power_on:bool=True) -> bool:
		'''Route this OneIP output to a source unit's own video, with the audio
		another unit's output returns to the mesh (its audio return group), as
		a mesh controller sends a route whose audio is an output.

		The frame is the one route_oneip_unit sends, with the audio address set
		to the audio return group arc_owner last reported for its output
		(oneip_details.arc).

		Such a route plays no audio: the output resolves the group to
		arc_owner's audio return, but audio return is compiled out of OneIP
		firmware. This sends exactly what a controller does all the same.

		Refused unless this is a OneIP output, the source has reported the
		streams of an input of its own, and arc_owner has reported a usable
		audio return group.
		'''
		if not self.is_oneip_sink:
			_LOGGER.warning(f"not routing {self}: not a OneIP output")
			return False
		if not isinstance(video, Device) or ((streams := video._own_source_streams("routing from")) is None):
			return False
		details = arc_owner.oneip_details
		arc = details.arc if (details is not None) else None
		if not oneip_stream_valid(arc):
			_LOGGER.warning(f"not routing {self}: {arc_owner} has not reported a usable audio return group")
			return False
		return self._send_source_switch(video=streams.video.ip, audio=arc.ip, power_on=power_on) # pyright: ignore[reportOptionalMemberAccess]

	@override
	async def unroute_oneip_unit(self) -> bool:
		'''Unroute this OneIP output, as a mesh controller does: the frame names
		no streams. Refused unless this is a OneIP output.'''
		if not self.is_oneip_sink:
			_LOGGER.warning(f"not unrouting {self}: not a OneIP output")
			return False
		return self._send_source_switch(video='0.0.0.0', audio='0.0.0.0', power_on=True)

	async def set_rc_settings(self, rc_target:RCType|int, ip:str|None, cec_enabled:bool, cec_auto_on:bool,
	                          forward_rc:bool, forward_ir:bool, rc_status:int=0, status_name:str='') -> bool:
		'''Change this OneIP unit's remote control and CEC settings.

		The unit applies the control method, the controlled device's address
		(None for none) and the four switches, then reports its settings; the
		driver state and status text are its own to report and it ignores them
		here. It takes the change only from its mesh controller or a management
		application. Refused unless this is a OneIP unit, rc_status fits
		MXR_RC_STATUS_MAX, and status_name is at most MXR_RC_STATUS_NAME_LEN
		ASCII bytes without a NUL.
		'''
		if not (0 <= rc_status <= MXR_RC_STATUS_MAX) or (len(status_name) > MXR_RC_STATUS_NAME_LEN) \
				or ('\0' in status_name) or not status_name.isascii() or not (0 <= int(rc_target) <= 0xFF):
			_LOGGER.warning(f"not setting remote control settings on {self}: "
			                f"a method, driver state or status text that does not fit its field")
			return False
		if (ip is not None):
			try:
				ipaddress.IPv4Address(ip)
			except ValueError:
				_LOGGER.warning(f"not setting remote control settings on {self}: {ip!r} is not an IPv4 address")
				return False
		if not self.is_oneip:
			_LOGGER.warning(f"not setting remote control settings on {self}: not a OneIP unit")
			return False
		frame = FrameRCSettings.construct(mxr=self.registry, target=self, rc_target=int(rc_target), ip=ip,
		                                  cec_enabled=cec_enabled, cec_auto_on=cec_auto_on,
		                                  forward_rc=forward_rc, forward_ir=forward_ir,
		                                  rc_status=rc_status, status_name=status_name)
		if (frame is None):
			return False
		return (self.registry.transmit(frame.frame) == len(frame.frame))

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

	async def set_oneip_skip_420(self, enabled:bool) -> bool:
		'''Have this sink skip its check that the display lists 4:2:0, or check
		again.

		One validity bit covers this and the sink's match-source setting, so the
		write restates match-source as the sink last reported it, off when it
		reported none. Otherwise as set_oneip_auto_scaling().
		'''
		scaling = self._cached_scaling
		written = MXR_SCALING_FLAG_OPTIONS2_VALID
		if enabled:
			written |= MXR_SCALING_FLAG_SKIP_420
		if (scaling.match_source is True):
			written |= MXR_SCALING_FLAG_MATCH_SOURCE
		def applied(cached:DeviceOneIPScalingSettings) -> OneIPScalingSettings:
			flags = (cached.flags & ~MXR_SCALING_OPTIONS2_SETTINGS) | written
			return OneIPScalingSettings(mode=cached.mode, refresh=cached.refresh, flags=flags)
		return self._send_v2ip_scaling(mode=MxrSignalType(bytes(2)), refresh=0,
		                               written=written, applied=applied)

	async def set_oneip_dscp(self, marking:OneIPDscpConfig) -> bool:
		'''Mark the streams this OneIP source sends with the DSCP values of
		marking, all three at once.

		A device applies a marking only when all three streams carry one, so a
		marking that leaves a stream out, or one above ONEIP_DSCP_MAX, is refused
		before anything is sent, as is a device that does not announce a source.
		Nothing acknowledges the frame; oneip_details.dscp reads the marking
		written until the device reports its own.
		'''
		why = None
		if not marking.complete:
			why = 'a marking leaves a stream out'
		elif any(not (0 <= m <= ONEIP_DSCP_MAX) for m in (marking.video, marking.audio, marking.anc)):
			why = f'a DSCP above {ONEIP_DSCP_MAX}'
		elif (self.features is None) or (DeviceFeature.ONEIP_SOURCE not in self.features):
			why = 'markings need a OneIP source'
		if (why is not None):
			_LOGGER.warning(f"not marking the streams of {self}: {why}")
			return False
		frame = FrameV2IPDeviceConfiguration.construct_dscp(
			mxr=self.registry, target=self, target_uid=self.remote_id,
			video=marking.video, audio=marking.audio, anc=marking.anc)
		if (frame is None) or (self.registry.transmit(frame.frame) != len(frame.frame)):
			return False
		if (self._v2ip_details is None) or (self._v2ip_details.dscp != marking):
			self.oneip_details = DeviceOneIPDetails(video=None, audio=None, anc=None, arc=None,
			                                        tx_rate=None, scaling=None, dscp=marking)
		return True

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
		if (self.protocol < _SCALING_WRITE_PROTOCOL):
			_LOGGER.warning(f"not setting scaling on {self}: its firmware drops a scaling write from management")
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

	async def set_oneip_ptp_mode(self, mode:OneIPPtpMode) -> bool:
		'''Set the PTP mode this OneIP device runs.

		A mode this library does not name is refused, since a device ignores it.
		The terms of set_oneip_setting() apply.
		'''
		if not (OneIPPtpMode.OFF <= mode <= OneIPPtpMode.AUTO):
			_LOGGER.warning(f"not setting PTP mode {mode} on {self}: no such mode")
			return False
		return self._send_v2ip_settings(OneIPDeviceSettings(
			valid=OneIPDeviceSetting.PTP_MODE, ptp_mode=mode))

	async def set_oneip_ptp_domain(self, domain:int) -> bool:
		'''Set the PTP domain this OneIP device runs in, at most
		ONEIP_PTP_DOMAIN_MAX. The terms of set_oneip_setting() apply.'''
		if not (0 <= domain <= ONEIP_PTP_DOMAIN_MAX):
			_LOGGER.warning(f"not setting PTP domain {domain} on {self}: no such domain")
			return False
		return self._send_v2ip_settings(OneIPDeviceSettings(
			valid=OneIPDeviceSetting.PTP_DOMAIN, ptp_domain=domain))

	async def set_oneip_ptp_priority1(self, priority1:int) -> bool:
		'''Set the priority1 this OneIP device announces as a PTP grandmaster,
		lower winning. The terms of set_oneip_setting() apply.'''
		if not (0 <= priority1 <= 0xFF):
			_LOGGER.warning(f"not setting PTP priority1 {priority1} on {self}: the field holds 0 to 255")
			return False
		return self._send_v2ip_settings(OneIPDeviceSettings(
			valid=OneIPDeviceSetting.PTP_PRIORITY1, ptp_priority1=priority1))

	async def set_oneip_power_save(self, enabled:bool) -> bool:
		'''Switch this OneIP device's power save on, so it powers down by itself
		to the level it picks, or off, so it powers down only when asked.

		On is written as a mesh controller writes it: both POWER_SAVE_DISABLED,
		clear, and POWER_SAVE_LEVEL, at 0, so a device whose firmware takes the
		level as its setting returns to its own default. The terms of
		set_oneip_setting() apply.
		'''
		return self._send_v2ip_settings(OneIPDeviceSettings.power_save_switch(enabled))

	async def set_oneip_power_save_level(self, level:OneIPPowerSaveLevel) -> bool:
		'''Write the level this OneIP device powers down to in power save, which
		switches power save on.

		A device picks its level itself and ignores the one written, except one
		whose firmware predates picking it, which takes the level as its
		setting. A level that unit does not offer is one its unit_status
		reports without UnitPowerSave.SUPPORTED. A level this library does not
		name is refused. The level is not cached: oneip_settings reads what the
		device reports. set_oneip_power_save() switches power save on or off
		without naming a level. The terms of set_oneip_setting() apply.
		'''
		if not (OneIPPowerSaveLevel.NONE <= level <= OneIPPowerSaveLevel.OFF):
			_LOGGER.warning(f"not setting power save level {level} on {self}: no such level")
			return False
		return self._send_v2ip_settings(OneIPDeviceSettings(
			valid=OneIPDeviceSetting.POWER_SAVE_LEVEL, power_save_level=level))

	async def set_oneip_ptp_messages(self, which:OneIPDeviceSetting, messages:OneIPPtpMessages) -> bool:
		'''Set how this OneIP device paces its PTP messages, its SAP timings,
		its streams' TTL and its output's rotation: the values of messages
		behind the bits of which, each one of ONEIP_DEVICE_SETTINGS_BLOCK.

		A DSCP above ONEIP_DSCP_MAX, a stream TTL outside 1 to 255 and a
		rotation that is not 0 or a multiple of the step the device reports are
		refused, since a device ignores them. The step is the device's own,
		and messages.sink_rotation_step is not sent. The terms of
		set_oneip_setting() apply.
		'''
		which = OneIPDeviceSetting(which)
		if (int(which) == 0) or ((which & ~ONEIP_DEVICE_SETTINGS_BLOCK) != 0):
			_LOGGER.warning(f"not setting {which!r} on {self}: only the settings of ONEIP_DEVICE_SETTINGS_BLOCK are carried here")
			return False
		if (OneIPDeviceSetting.PTP_DSCP in which) and not (0 <= messages.dscp <= ONEIP_DSCP_MAX):
			_LOGGER.warning(f"not setting PTP DSCP {messages.dscp} on {self}: above {ONEIP_DSCP_MAX}")
			return False
		if (OneIPDeviceSetting.STREAM_TTL in which) and not (1 <= messages.stream_ttl <= 0xFF):
			_LOGGER.warning(f"not setting stream TTL {messages.stream_ttl} on {self}: outside 1 to 255")
			return False
		if (OneIPDeviceSetting.SINK_ROTATION in which):
			own = (self._v2ip_settings.ptp_messages if (self._v2ip_settings is not None) else None) or OneIPPtpMessages()
			if not own.takes_sink_rotation(messages.sink_rotation):
				_LOGGER.warning(f"not turning the output of {self} by {messages.sink_rotation} degrees: "
				                f"it turns by steps of {own.sink_rotation_step}")
				return False
		return self._send_v2ip_settings(OneIPDeviceSettings(valid=which, ptp_messages=messages))

	def _on_oneip_downmix(self, downmix:OneIPDownmix|None, reported:bool) -> None:
		'''Take the downmix a configuration carries as the device takes it: a
		report replaces the one held, None included, and another sender's write
		is applied only to a device that reports a downmix, and never to what
		only the device reports.'''
		if not reported:
			if (downmix is None) or (self._v2ip_downmix is None):
				return
			downmix = self._v2ip_downmix.written(downmix)
		if (self._v2ip_downmix != downmix):
			self._v2ip_downmix = downmix
			self.call_callbacks()

	def _on_oneip_locale(self, locale:int|None, reported:bool) -> None:
		'''Take the locale a configuration carries as the device takes it: a
		report replaces the one held, None included, and another sender's write
		is applied only to a device that reports a locale, since one without
		locales ignores it.'''
		if not reported and ((locale is None) or (self._v2ip_locale is None)):
			return
		if (self._v2ip_locale != locale):
			self._v2ip_locale = locale
			self.call_callbacks()

	async def set_oneip_locale(self, locale:int) -> bool:
		'''Set the locale this OneIP device runs, by its number: its position in
		the list of locales the device's /system/locale names.

		A device stores and loads a locale it knows and ignores one it does not,
		so a locale is sent also to a device that has not reported its settings
		yet. Refused before anything is sent for ONEIP_LOCALE_UNKNOWN or a number
		that is not a byte, and for a device whose settings arrived without a
		locale, as its firmware has none. The locale is cached once the frame is
		sent, and the device's next report replaces it.
		'''
		why = None
		if not (0 <= locale < ONEIP_LOCALE_UNKNOWN):
			why = 'no such locale'
		elif (self._v2ip_settings is not None) and (self._v2ip_locale is None):
			why = "the device's firmware has no locales"
		if (why is not None):
			_LOGGER.warning(f"not setting locale {locale} on {self}: {why}")
			return False
		frame = FrameV2IPDeviceConfiguration.construct_locale(
			mxr=self.registry, target=self, target_uid=self.remote_id, locale=locale)
		if (frame is None) or (self.registry.transmit(frame.frame) != len(frame.frame)):
			return False
		self._on_oneip_locale(locale, reported=True)
		return True

	async def set_oneip_downmix(self, downmix:OneIPDownmix) -> bool:
		'''Set how this OneIP device's output mixes 5.1 and 7.1 PCM down to
		stereo: the mode, level and LFE percent of downmix, which the device
		applies together. Its status is the device's to report, and is not
		sent.

		Refused before anything is sent for a mode, level or LFE percent out of
		range, and unless the device reports a downmix, which one whose output
		cannot mix down never does. The new downmix is cached once the frame is
		sent, with no status until the device's next report says how it mixes.
		'''
		why = None
		if not downmix.is_valid():
			why = f'no such mode or level, or an LFE above {ONEIP_DOWNMIX_LFE_MAX} percent'
		elif (self._v2ip_settings is None):
			why = 'it has not reported its settings'
		elif ((reported := self._v2ip_downmix) is None):
			why = 'its output does not mix down'
		if (why is not None):
			_LOGGER.warning(f"not changing the downmix of {self}: {why}")
			return False
		frame = FrameV2IPDeviceConfiguration.construct_downmix(
			mxr=self.registry, target=self, target_uid=self.remote_id, downmix=downmix)
		if (frame is None) or (self.registry.transmit(frame.frame) != len(frame.frame)):
			return False
		# The device hasn't said how it mixes the new settings yet.
		self._on_oneip_downmix(replace(reported.written(downmix), status=None), reported=True)
		return True

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

	async def confirm_oneip_vlan(self) -> bool:
		'''Confirm the VLAN configuration this OneIP device runs pending, as its
		mesh controller does, so the device keeps it rather than reverting it.

		The frame echoes the configuration the device last reported, its trunk
		flag included, with CONFIRM in place of what only a device reports. A
		device repeats its report every 3 s while the change is pending and
		stores a confirmation only while it is, so a confirmation lost or sent
		twice is answered by the next report. It takes it only from its mesh
		controller or a management application. Refused unless the device
		announces DeviceFeature.VLAN and has last reported a pending
		configuration.
		'''
		why = None
		if (self.features is None) or (DeviceFeature.VLAN not in self.features):
			why = 'the device does not take VLANs'
		elif ((reported := self._v2ip_vlan) is None):
			why = 'it has not reported its VLAN configuration'
		elif not reported.is_pending:
			why = 'it has no VLAN change pending'
		if (why is not None):
			_LOGGER.warning(f"not confirming the VLAN configuration of {self}: {why}")
			return False
		confirmed = replace(reported, active_uplink=0, revert_s=0,
		                    flags=(OneIPVlanFlag.VALID | OneIPVlanFlag.CONFIRM | (reported.flags & OneIPVlanFlag.TRUNK)))
		frame = FrameV2IPDeviceConfiguration.construct_vlan(
			mxr=self.registry, target=self, target_uid=self.remote_id, vlan=confirmed)
		if (frame is None):
			return False
		return self.registry.transmit(frame.frame) == len(frame.frame)

	async def request_oneip_power_save(self, suspend:bool) -> bool:
		'''Ask this OneIP unit to enter power save, or to leave it: 0x41 naming
		the unit. It takes the request only from its mesh controller or a
		management application, and one that cannot power down ignores it.

		This asks for a state now; set_oneip_power_save() switches the setting
		that lets the unit power down by itself.
		Remote.request_all_oneip_power_save() asks every unit.
		'''
		frame = FrameV2IPPowerSave.construct(mxr=self.registry, target=self,
		                                     target_uid=self.remote_id, suspend=suspend)
		if (frame is None):
			return False
		return self.registry.transmit(frame.frame) == len(frame.frame)

	async def set_audio_endpoint_locked(self, endpoint:int, locked:bool) -> bool:
		'''Lock or unlock the audio source of one of this device's audio
		endpoints: while it is locked, a video route change leaves the endpoint's
		audio source alone.

		Refused unless the endpoint reports AudioFeatures.FEATURE_AUDIO_LOCK,
		which is the only one the device acts on. Once the frame is away, the
		endpoint's audio_locked reads the new state until the device reports its
		endpoints again, and its reports are ignored for AUDIO_REPORT_GUARD.
		'''
		ep = self.audio_endpoint_by_id(endpoint)
		if (ep is None) or not ep.features.support_audio_lock:
			_LOGGER.warning(f"not locking audio endpoint {endpoint} of {self}: it cannot lock its audio source")
			return False
		frame = FrameV2IPAudio.construct_lock(mxr=self.registry, target=self.remote_id,
		                                      endpoint_id=endpoint, locked=locked)
		if (frame is None) or (self.registry.transmit(frame.frame, to=self) != len(frame.frame)):
			return False
		self.audio_commanded()
		self._hold_audio_switch(endpoint, AudioFeatures.FEATURE_AUDIO_LOCK, locked)
		return True

	async def request_oneip_testcard(self) -> bool:
		'''Ask this OneIP sink for its test card, which it reports straight back
		into oneip_testcard.

		Refused unless the sink's video processor has reported
		OneIPVideoProcessorFeature.RTOS. A sink with it but without the module
		that draws the test card does not answer.
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

	@property
	@override
	def osd_sync(self) -> OsdSync|None:
		return self._osd_sync

	@property
	@override
	def osd_sync_report(self) -> OsdSyncReport|None:
		return self._osd_sync_report

	@property
	@override
	def osd_message(self) -> OsdMessage|None:
		return self._osd_message

	async def request_osd_message(self) -> bool:
		'''Ask this unit for the message on its output, which osd_message reads
		once the unit answers. Refused for a device that is not a OneIP output.'''
		return self._send_osd_message(OSD_KIND_MESSAGE_REQUEST)

	async def show_osd_message(self, text:str, logo:int=-1,
	                           priority:OsdMessagePriority=OsdMessagePriority.NORMAL) -> bool:
		'''Show a message on this unit's output, in place of any it has.

		text is markup of at most OSD_MESSAGE_TEXT_MAX bytes, with no control
		character; empty, the logo shows alone. logo is shown with it: 0 the
		built-in logo, -1 none, 1 to 5 a logo slot.

		The unit takes it from management, which this client announces itself
		as, and holds it until it restarts. It answers with the message it then
		has, which osd_message reads, flagged OsdMessageFlag.REFUSED when its
		video processor has no message layer. Refused here for a device that
		is not a OneIP output, and for a logo, priority or text the unit would
		refuse.
		'''
		data = text.encode('utf-8')
		why = None
		if not (-1 <= logo <= 5):
			why = 'a logo of -1 to 5'
		elif not (OsdMessagePriority.LOW <= priority <= OsdMessagePriority.TOP):
			why = 'no such message priority'
		elif (len(data) > OSD_MESSAGE_TEXT_MAX):
			why = f'a message of at most {OSD_MESSAGE_TEXT_MAX} bytes'
		elif any((b < 0x20) for b in data):
			why = 'a control character in a message'
		if (why is not None):
			_LOGGER.warning(f"not showing a message on {self}: {why}")
			return False
		return self._send_osd_message(OSD_KIND_MESSAGE_SET, OsdMessageFlag.SET, logo, priority, data)

	async def clear_osd_message(self) -> bool:
		'''Take the message down from this unit's output. As show_osd_message().'''
		return self._send_osd_message(OSD_KIND_MESSAGE_SET)

	def _send_osd_message(self, kind:int, flags:OsdMessageFlag=OsdMessageFlag(0), logo:int=0,
	                      priority:OsdMessagePriority=OsdMessagePriority.LOW, text:bytes=b'') -> bool:
		'''The one send behind the message commands, to a OneIP output.'''
		if not self.is_oneip_sink:
			_LOGGER.warning(f"not sending an overlay message command to {self}: it is not a OneIP output")
			return False
		frame = FrameV2IPOsdSync.construct_message(mxr=self.registry, target=self, target_uid=self.remote_id,
		                                           kind=kind, flags=flags, logo=logo, priority=priority, text=text)
		if (frame is None):
			return False
		return self.registry.transmit(frame.frame, to=self) == len(frame.frame)

	@property
	@override
	def oneip_sink_sdp(self) -> OneIPSinkSdp|None:
		return self._v2ip_sink_sdp

	async def play_oneip_sdp(self, sdp:str) -> bool:
		'''Have this OneIP output play the stream a session description describes.

		The description goes out in pages of up to 1 KB, and the output plays it
		once the last page is in. It takes them only from its mesh controller or
		a management application, which this client announces itself as.
		Nothing acknowledges the pages: oneip_sink_sdp reads what the output
		reports next. Refused for an empty description or one longer than
		ONEIP_SDP_MAX bytes, which an output drops after the last page, for a
		device that is not a OneIP output, and for one below protocol 0x2E.
		'''
		data = sdp.encode('utf-8')
		if not (1 <= len(data) <= ONEIP_SDP_MAX):
			_LOGGER.warning(f"not playing a session description on {self}: {len(data)} bytes, not 1 to {ONEIP_SDP_MAX}")
			return False
		if not self.is_oneip_sink:
			_LOGGER.warning(f"not playing a session description on {self}: it is not a OneIP output")
			return False
		pages = FrameV2IPSinkSdp.construct_pages(mxr=self.registry, target=self, target_uid=self.remote_id, sdp=data)
		if (pages is None):
			return False
		return all(self.registry.transmit(page.frame) == len(page.frame) for page in pages)

	async def stop_oneip_sdp(self) -> bool:
		'''Stop the stream this OneIP output plays from a session description. As
		play_oneip_sdp().'''
		return self._send_sink_sdp_command(SDP_STOP, 0)

	async def set_oneip_sdp_screen(self, screen:int) -> bool:
		'''Set what this OneIP output shows while it plays audio alone, as the
		wire value. As play_oneip_sdp().'''
		if not (0 <= screen <= 0xFF):
			_LOGGER.warning(f"not setting screen {screen} on {self}: the field holds 0 to 255")
			return False
		return self._send_sink_sdp_command(SDP_SCREEN, screen)

	async def request_oneip_sink_sdp(self) -> bool:
		'''Ask this OneIP output what it plays from a session description now,
		rather than at its next report, which comes at least once a minute. As
		play_oneip_sdp().'''
		return self._send_sink_sdp_command(SDP_REQUEST, 0)

	@property
	@override
	def oneip_sink_description(self) -> str|None:
		return self._v2ip_sink_description

	async def request_oneip_sink_description(self) -> bool:
		'''Ask this OneIP output what it plays from a session description and for
		the description itself, which oneip_sink_description then reads. An
		output that plays none sends its status alone.

		Refused below protocol 0x31, where an output ignores the ask for the
		description. Otherwise as play_oneip_sdp().'''
		if (self.protocol != 0) and (self.protocol < SDP_DESCRIPTION_PROTOCOL):
			_LOGGER.warning(f"not asking {self} for its session description: protocol {self.protocol:#04x} "
			                f"predates it")
			return False
		return self._send_sink_sdp_command(SDP_REQUEST, SDP_REQUEST_DESCRIPTION)

	def _on_sink_description_page(self, page:SdpDescriptionPage) -> None:
		'''Put together the description this output reports playing, one page
		at a time, as a unit puts together the pages it is sent.

		A page at offset 0 starts a description of 1 to ONEIP_SDP_MAX bytes.
		Every later page has to continue it: at the offset received so far, for
		the same length, within SDP_PAGE_TIMEOUT of the page before. Anything
		else drops the pages received, and the description is kept once its
		last byte is in.'''
		pending = self._v2ip_sink_description_pages
		self._v2ip_sink_description_pages = None
		if (page.offset == 0):
			if not (1 <= page.total <= ONEIP_SDP_MAX):
				return
			data = b''
		elif (pending is not None) and (pending[0] == page.total) and (len(pending[1]) == page.offset) \
				and (page.timestamp - pending[2] <= SDP_PAGE_TIMEOUT):
			data = pending[1]
		else:
			return
		if (len(data) + len(page.text) > page.total):
			return
		data += page.text
		if (len(data) < page.total):
			self._v2ip_sink_description_pages = (page.total, data, page.timestamp)
			return
		description = data.decode('utf-8', errors='replace')
		if (self._v2ip_sink_description != description):
			self._v2ip_sink_description = description
			self.call_callbacks()

	@property
	@override
	def oneip_privacy(self) -> OneIPPrivacy|None:
		return self._v2ip_privacy

	async def request_oneip_privacy(self) -> bool:
		'''Ask this OneIP source unit how its streams are encrypted now, rather
		than at its next report, which comes at least once a minute and whenever
		they change. Refused for a device that is not a OneIP source, and for
		one below protocol 0x30, which predates the report.'''
		if (self.features is None) or (DeviceFeature.ONEIP_SOURCE not in self.features):
			_LOGGER.warning(f"not asking {self} how its streams are encrypted: it is not a OneIP source")
			return False
		frame = FrameV2IPPrivacy.construct_request(mxr=self.registry, target=self, target_uid=self.remote_id)
		if (frame is None):
			return False
		return self.registry.transmit(frame.frame) == len(frame.frame)

	def _send_sink_sdp_command(self, kind:int, value:int) -> bool:
		'''The one send behind the session description commands.'''
		if not self.is_oneip_sink:
			_LOGGER.warning(f"not sending a session description command to {self}: it is not a OneIP output")
			return False
		frame = FrameV2IPSinkSdp.construct_command(mxr=self.registry, target=self, target_uid=self.remote_id,
		                                           kind=kind, value=value)
		if (frame is None):
			return False
		return self.registry.transmit(frame.frame) == len(frame.frame)

	def _send_v2ip_testcard(self, kind:int, parts:int, testcard:OneIPTestcard) -> bool:
		'''The one send behind the test card commands. Nothing is cached: the
		sink answers every frame with its test card.'''
		if ((features := self._v2ip_features) is None):
			_LOGGER.warning(f"not sending a test card frame to {self}: its video processor has reported no features")
			return False
		if (OneIPVideoProcessorFeature.RTOS not in features):
			_LOGGER.warning(f"not sending a test card frame to {self}: it cannot draw a test card")
			return False
		frame = FrameV2IPTestcard.construct(mxr=self.registry, target=self, target_uid=self.remote_id,
		                                    kind=kind, parts=parts, testcard=testcard)
		if (frame is None):
			return False
		return self.registry.transmit(frame.frame, to=self) == len(frame.frame)

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
		self._merge_v2ip_settings(settings.as_applied_to(reported))
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
