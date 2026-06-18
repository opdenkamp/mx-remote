######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Link management between bays on MX Remote devices.'''

from ..proto import LinkConfig
from ..proto import Constants as proto
from typing import Any, List, Tuple
from ..Interface import BayBase, MxrCallbacks

class Link:
	''' Link between 2 bays on 2 devices '''

	def __init__(self, bay:BayBase, link_data:LinkConfig.LinkConfig):
		self._bay = bay
		self._link = link_data

	@property
	def callbacks(self) -> MxrCallbacks:
		return self._bay.callbacks

	@property
	def bays(self) -> List[BayBase]:
		if self.configured:
			return [ self._link.remote_bay, self._link.linked_bay ]
		return [ self._bay ]

	@property
	def configured(self) -> bool:
		return (self._link is not None) and self._link.is_linked

	@property
	def connected(self) -> bool:
		return self.configured and (self._link.linked_bay is not None)

	@property
	def online(self) -> bool:
		return self.connected and (self._link.linked_bay.online)

	@property
	def primary(self) -> BayBase:
		'''Return the source-type bay for linked bays, or the only registered bay.'''
		if not self.connected:
			return self._bay
		if self._link.remote_bay.is_input:
			return self._link.remote_bay
		return self._link.linked_bay

	def is_primary(self, bay:BayBase) -> bool:
		'''Check whether the given bay is the primary bay of this link.'''
		primary = self.primary
		return (primary is not None) and (bay == primary)

	def other_bay(self, bay:BayBase) -> BayBase|None:
		'''Return the bay on the other side of this link.'''
		if not self.connected:
			return None
		if bay == self._link.linked_bay:
			return self._link.remote_bay
		return self._link.linked_bay

	def other_serial_bay(self, bay:BayBase) -> Tuple[str|None,str|None]:
		'''Return the serial and bay name for the other end of this link.'''
		other_bay = self.other_bay(bay)
		if other_bay is None:
			return (None, None)
		return (other_bay.device.serial, other_bay.port)

	def other_serial_bay_str(self, bay:BayBase) -> str:
		'''Return the link configuration for the given bay as a string.'''
		link_serial, link_bay = self.other_serial_bay(bay)
		if (link_serial is None) or (link_bay is None):
			return ""
		return f"{link_serial} {link_bay}"

	def serial_bays(self) -> List[str]:
		'''Return this link configuration as a list of serial+bay strings.'''
		rv = []
		primary = self.primary
		rv.append(f"{primary.device.serial} {primary.bay_name}")
		if self.configured:
			link_serial, link_bay = self.other_serial_bay(primary)
			rv.append(f"{link_serial} {link_bay}")
		return rv

	def update(self, config:LinkConfig) -> None:
		'''Update this link configuration with new data from mx_remote.'''
		link = Link(config.remote_bay, config)
		if (self.configured and not link.configured) or (self.other_bay(self._bay) != link.other_bay(self._bay)):
			self.callbacks.on_bay_unlinked(self._bay, self)
			self.callbacks.on_bay_unlinked(self.other_bay(self._bay), self)

		if (not self.configured and link.configured) or (self.other_bay(self._bay) != link.other_bay(self._bay)):
			self.callbacks.on_bay_linked(self._bay, link)
			self.callbacks.on_bay_linked(link.other_bay(self._bay), link)
		self._link = link._link

	@property
	def is_audio(self) -> bool:
		'''Return True if this link carries audio (optical or analog).'''
		ft = self.features_mask
		return proto.LinkFeature.AUDIO_OPTICAL in ft or proto.LinkFeature.AUDIO_ANALOG in ft

	@property
	def is_video(self) -> bool:
		'''Return True if this link carries HDMI video.'''
		return proto.LinkFeature.VIDEO_HDMI in self.features_mask

	@property
	def features(self) -> list[str]:
		'''Return human-readable names of features supported by this link.'''
		ft:list[str] = []
		m = self.features_mask
		if proto.LinkFeature.VIDEO_HDMI in m:
			ft.append("HDMI")
		if proto.LinkFeature.AUDIO_OPTICAL in m:
			ft.append("optical audio")
		if proto.LinkFeature.AUDIO_ANALOG in m:
			ft.append("analog audio")
		if proto.LinkFeature.IR in m:
			ft.append("IR")
		if proto.LinkFeature.RC in m:
			ft.append("RC")
		return ft

	@property
	def features_mask(self) -> proto.LinkFeature:
		'''Return features supported by this link as a bitmask.'''
		bays = self.bays
		if len(bays) < 2:
			return proto.LinkFeature(0)
		left = bays[0].features
		right = bays[1].features
		rv = proto.LinkFeature(0)
		if proto.BayFeaturesMask.HDMI_OUT in left:
			if proto.BayFeaturesMask.HDMI_IN in right:
				rv |= proto.LinkFeature.VIDEO_HDMI
		if proto.BayFeaturesMask.HDMI_IN in left:
			if proto.BayFeaturesMask.HDMI_OUT in right:
				rv |= proto.LinkFeature.VIDEO_HDMI
		if proto.BayFeaturesMask.AUDIO_DIG_OUT in left:
			if proto.BayFeaturesMask.AUDIO_DIG_IN in right:
				rv |= proto.LinkFeature.AUDIO_OPTICAL
		if proto.BayFeaturesMask.AUDIO_DIG_IN in left:
			if proto.BayFeaturesMask.AUDIO_DIG_OUT in right:
				rv |= proto.LinkFeature.AUDIO_OPTICAL
		if proto.BayFeaturesMask.AUDIO_ANA_OUT in left:
			if proto.BayFeaturesMask.AUDIO_ANA_IN in right:
				rv |= proto.LinkFeature.AUDIO_ANALOG
		if proto.BayFeaturesMask.AUDIO_ANA_IN in left:
			if proto.BayFeaturesMask.AUDIO_ANA_OUT in right:
				rv |= proto.LinkFeature.AUDIO_ANALOG
		if proto.BayFeaturesMask.IR_OUT in left:
			if proto.BayFeaturesMask.IR_IN in right:
				rv |= proto.LinkFeature.IR
		if proto.BayFeaturesMask.IR_IN in left:
			if proto.BayFeaturesMask.IR_OUT in right:
				rv |= proto.LinkFeature.IR
		if proto.BayFeaturesMask.RC_OUT in left:
			if proto.BayFeaturesMask.RC_IN in right:
				rv |= proto.LinkFeature.RC
		if proto.BayFeaturesMask.RC_IN in left:
			if proto.BayFeaturesMask.RC_OUT in right:
				rv |= proto.LinkFeature.RC
		return rv

	def __eq__(self, other:Any) -> bool:
		if not isinstance(other, Link):
			return False
		return (self.configured == other.configured) and \
			(((self._bay == other._bay) and (self.other_bay(self._bay) == other.other_bay(self._bay))) or \
				((self.other_bay(self._bay) == other._bay) and (self._bay == other.other_bay(self._bay))))

	def __str__(self) -> str:
		if not self.configured:
			return "{} not linked".format(str(self.primary))
		other = self.other_bay(self.primary)
		if other is None:
			link_serial, link_bay = self.other_serial_bay(self.primary)
			return "{} linked to ({} {}) - disconnected".format(str(self.primary), link_serial, link_bay)
		return "{} linked to {} - {}".format(str(self.primary), str(other), str(self.features))

