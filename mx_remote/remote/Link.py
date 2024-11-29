##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from __future__ import annotations
from ..proto import LinkConfig
from ..proto import Constants as proto
from typing import List, Tuple
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
		# source type bay for linked bays. if only 1 side has been registered, that bay will be returned
		if not self.connected:
			return self._bay
		if self._link.remote_bay.is_input:
			return self._link.remote_bay
		return self._link.linked_bay

	def is_primary(self, bay:BayBase) -> bool:
		# check whether the given bay is the primary bay of this link
		primary = self.primary
		return (primary is not None) and (bay == primary)

	def other_bay(self, bay:BayBase) -> BayBase:
		# return the other side of this link
		if not self.connected:
			return None
		if bay == self._link.linked_bay:
			return self._link.remote_bay
		return self._link.linked_bay

	def other_serial_bay(self, bay:BayBase) -> Tuple[str,str]:
		# return the configuration for the other end of this link (serial + bay)
		other_bay = self.other_bay(bay)
		if other_bay is None:
			return (None, None)
		return (other_bay.device.serial, other_bay.port)

	def other_serial_bay_str(self, bay:BayBase) -> str:
		# return the link configuration for the given bay as string
		link_serial, link_bay = self.other_serial_bay(bay)
		if (link_serial is None) or (link_bay is None):
			return ""
		return f"{link_serial} {link_bay}"

	def serial_bays(self) -> List[str]:
		# return this link configuration as list of strings
		rv = []
		primary = self.primary
		rv.append(f"{primary.device.serial} {primary.bay_name}")
		if self.configured:
			link_serial, link_bay = self.other_serial_bay(primary)
			rv.append(f"{link_serial} {link_bay}")
		return rv

	def update(self, config:LinkConfig) -> None:
		link = Link(config.remote_bay, config)
		# update this link configuration with the new data from mx_remote
		if (self.configured and not link.configured) or (self.other_bay(self._bay) != link.other_bay(self._bay)):
			self.callbacks.on_bay_unlinked(self._bay, self)
			self.callbacks.on_bay_unlinked(self.other_bay(self._bay), self)

		if (not self.configured and link.configured) or (self.other_bay(self._bay) != link.other_bay(self._bay)):
			self.callbacks.on_bay_linked(self._bay, link)
			self.callbacks.on_bay_linked(link.other_bay(self._bay), link)
		self._link = link._link

	@property
	def is_audio(self) -> bool:
		# audio link
		ft = self.features_mask
		return (ft & proto.MX_LINK_FEATURE_AUDIO_OPTICAL) != 0 or \
				(ft & proto.MX_LINK_FEATURE_AUDIO_ANALOG) != 0

	@property
	def is_video(self) -> bool:
		# video link
		return (self.features_mask & proto.MX_LINK_FEATURE_VIDEO_HDMI) != 0

	@property
	def features(self) -> List[str]:
		# features supported by this link (strings)
		ft = []
		m = self.features_mask
		if (m & proto.MX_LINK_FEATURE_VIDEO_HDMI):
			ft.append("HDMI")
		if (m & proto.MX_LINK_FEATURE_AUDIO_OPTICAL):
			ft.append("optical audio")
		if (m & proto.MX_LINK_FEATURE_AUDIO_ANALOG):
			ft.append("analog audio")
		if (m & proto.MX_LINK_FEATURE_IR):
			ft.append("IR")
		if (m & proto.MX_LINK_FEATURE_RC):
			ft.append("RC")
		return ft

	@property
	def features_mask(self) -> int:
		# features supported by this link (bitmask)
		bays = self.bays
		if len(bays) < 2:
			return 0
		left = bays[0].features_mask
		right = bays[1].features_mask
		rv = 0
		if (left & proto.MX_BAY_FEATURE_HDMI_OUT):
			if (right & proto.MX_BAY_FEATURE_HDMI_IN):
				rv |= proto.MX_LINK_FEATURE_VIDEO_HDMI
		if (left & proto.MX_BAY_FEATURE_HDMI_IN):
			if (right & proto.MX_BAY_FEATURE_HDMI_OUT):
				rv |= proto.MX_LINK_FEATURE_VIDEO_HDMI
		if (left & proto.MX_BAY_FEATURE_AUDIO_DIG_OUT):
			if (right & proto.MX_BAY_FEATURE_AUDIO_DIG_IN):
				rv |= proto.MX_LINK_FEATURE_AUDIO_OPTICAL
		if (left & proto.MX_BAY_FEATURE_AUDIO_DIG_IN):
			if (right & proto.MX_BAY_FEATURE_AUDIO_DIG_OUT):
				rv |= proto.MX_LINK_FEATURE_AUDIO_OPTICAL
		if (left & proto.MX_BAY_FEATURE_AUDIO_ANA_OUT):
			if (right & proto.MX_BAY_FEATURE_AUDIO_ANA_IN):
				rv |= proto.MX_LINK_FEATURE_AUDIO_ANALOG
		if (left & proto.MX_BAY_FEATURE_AUDIO_ANA_IN):
			if (right & proto.MX_BAY_FEATURE_AUDIO_ANA_OUT):
				rv |= proto.MX_LINK_FEATURE_AUDIO_ANALOG
		if (left & proto.MX_BAY_FEATURE_IR_OUT):
			if (right & proto.MX_BAY_FEATURE_IR_IN):
				rv |= proto.MX_LINK_FEATURE_IR
		if (left & proto.MX_BAY_FEATURE_IR_IN):
			if (right & proto.MX_BAY_FEATURE_IR_OUT):
				rv |= proto.MX_LINK_FEATURE_IR
		if (left & proto.MX_BAY_FEATURE_RC_OUT):
			if (right & proto.MX_BAY_FEATURE_RC_IN):
				rv |= proto.MX_LINK_FEATURE_RC
		if (left & proto.MX_BAY_FEATURE_RC_IN):
			if (right & proto.MX_BAY_FEATURE_RC_OUT):
				rv |= proto.MX_LINK_FEATURE_RC
		return rv

	def __eq__(self, other:Link) -> bool:
		return (self.configured == other.configured) and \
			(((self._bay == other._bay) and (self.other_bay(self._bay) == other.other_bay(self._bay))) or \
				((self.other_bay(self._bay) == other._bay) and (self._bay == other.other_bay(self._bay))))

	def __str__(self) -> str:
		primary = self.primary
		if primary is None:
			return "bay link incomplete"
		if not self.configured:
			return "{} not linked".format(str(primary))
		other = self.other_bay(primary)
		if other is None:
			link_serial, link_bay = self.other_serial_bay(primary)
			return "{} linked to ({} {}) - disconnected".format(str(primary), link_serial, link_bay)
		return "{} linked to {} - {}".format(str(primary), str(other), str(self.features))

