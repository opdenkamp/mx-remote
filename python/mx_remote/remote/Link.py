from __future__ import annotations
import mx_remote.proto as proto
from typing import List

class LinkNode:
	''' One node of a link between 2 devices, defined by a serial and bay '''

	def __init__(self, mxr:'remote.Remote', serial:str, bay_name:str):
		self._mxr = mxr
		self._serial = serial
		self._bay_name = bay_name

	@property
	def mxr(self) -> 'remote.Remote':
		return self._mxr

	@property
	def serial(self) -> str:
		# device serial
		return self._serial

	@property
	def bay_name(self) -> str:
		# bay name
		return self._bay_name

	@property
	def configured(self) -> bool:
		# serial and name set
		return (len(self.serial) > 0) and (len(self.bay_name) > 0)

	@property
	def device(self) -> 'mx_remote.remote.Device.Device':
		# device instance for the serial in this node
		return self.mxr.get_by_serial(self.serial) if self.configured else None

	@property
	def bay(self) -> 'mx_remote.remote.Bay.Bay':
		# bay instance for the serial+name in this node
		remote_dev = self.device
		if (remote_dev is not None) and (self._bay_name is not None):
			return remote_dev.get_by_portname(self._bay_name)
		return None

	def __eq__(self, other:LinkNode) -> bool:
		return (self.serial == other.serial) and (self.bay_name == other.bay_name)

	def __neq__(self, other:LinkNode) -> bool:
		return (self.serial != other.serial) or (self.bay_name != other.bay_name)

class Link:
	''' Link between 2 bays on 2 devices '''

	def __init__(self, bay:'mx_remote.remote.Bay.Bay', link_data:proto.LinkConfig.LinkConfig):
		self._nodes = [LinkNode(bay.mxr, bay.dev.serial, bay.bay_name), \
				LinkNode(bay.mxr, link_data.linked_serial, link_data.linked_bay_name)]

	@property
	def mxr(self) -> 'remote.Remote':
		return self._nodes[0].mxr if len(self._nodes) != 0 else None

	@property
	def bays(self) -> List['mx_remote.remote.Bay.Bay']:
		# bays that can be resolved. if this only returns one entry, then the other end is offline
		rv = []
		for node in self._nodes:
			bay = node.bay
			if bay is not None:
				rv.append(bay)
		return rv

	@property
	def configured(self) -> bool:
		# link configured or not
		if len(self._nodes) != 2:
			return False
		for node in self._nodes:
			if not node.configured:
				return False
		return True

	@property
	def connected(self) -> bool:
		# both ends resolved
		if len(self._nodes) != 2:
			return False
		for node in self._nodes:
			if node.bay is None:
				return False
		return True

	@property
	def online(self) -> bool:
		# both ends online
		if len(self._nodes) != 2:
			return False
		for node in self._nodes:
			bay = node.bay
			if bay is None or not bay.online:
				return False
		return True

	@property
	def primary(self) -> 'mx_remote.remote.Bay.Bay':
		# source type bay for linked bays. if only 1 side has been registered, that bay will be returned
		bays = self.bays
		if len(bays) == 0:
			return None
		if len(bays) == 1:
			return bays[0]
		if bays[0].is_input:
			return bays[0]
		return bays[1]

	def is_primary(self, bay:'mx_remote.remote.Bay.Bay') -> bool:
		# check whether the given bay is the primary bay of this link
		primary = self.primary
		return (primary is not None) and (bay == primary)

	def other_bay(self, bay:'mx_remote.remote.Bay.Bay') -> 'mx_remote.remote.Bay.Bay':
		# return the other side of this link
		bays = self.bays
		if len(bays) < 2:
			return None
		if bays[0] == bay:
			return bays[1]
		if bays[1] == bay:
			return bays[0]
		return None

	def other_serial_bay(self, bay:'mx_remote.remote.Bay.Bay') -> Tuple[str,str]:
		# return the configuration for the other end of this link (serial + bay)
		if not self.configured:
			return (None, None)
		cbay = self._nodes[0].bay
		if (cbay is not None) and (cbay == bay):
			return (self._nodes[1].serial, self._nodes[1].bay_name)
		cbay = self._nodes[1].bay
		if (cbay is not None) and (cbay == bay):
			return (self._nodes[0].serial, self._nodes[0].bay_name)
		return (None, None)

	def other_serial_bay_str(self, bay:'mx_remote.remote.Bay.Bay') -> str:
		# return the link configuration for the given bay as string
		link_serial, link_bay = self.other_serial_bay(bay)
		if (link_serial is None) or (link_bay is None):
			return ""
		return "{} {}".format(link_serial, link_bay)

	def serial_bays(self) -> List[str]:
		# return this link configuration as list of strings
		rv = []
		primary = self.primary
		rv.append("{} {}".format(primary.serial, primary.bay_name))
		if self.configured:
			link_serial, link_bay = self.other_serial_bay(primary)
			rv.append("{} {}".format(link_serial, link_bay))
		return rv

	def update(self, bay:'mx_remote.remote.Bay.Bay', link:Link) -> None:
		# update this link configuration with the new data from mx_remote
		bays = self.bays
		other_bay = self.other_serial_bay_str(bay)
		other_bay_new = link.other_serial_bay_str(bay)
		if (len(other_bay) == 0) and (len(other_bay_new) > 0):
			# new link
			self._nodes = link._nodes
			for ubay in self.bays:
				ubay.link = self
			self.primary.mxr.on_bay_linked(self)
		elif (other_bay != other_bay_new):
			if (len(other_bay_new) == 0):
				# unlinked
				link_serial, link_bay = self.other_serial_bay(bay)
				for ubay in self.bays:
					ubay.link = self if ubay == bay else None
				self._nodes = link._nodes
				self.mxr.on_bay_unlinked(bay, link_serial, link_bay)
			else:
				# link changed
				obay = self.other_bay(bay)
				if obay is not None:
					obay.link = None
					self.mxr.on_bay_unlinked(obay, bay.dev.serial, bay.bay_name)
				self._nodes = link._nodes
				for ubay in self.bays:
					ubay.link = self
				self.primary.mxr.on_bay_linked(self)

	@property
	def is_audio(self) -> bool:
		# audio link
		ft = self.features_mask
		return (ft & proto.MX_LINK_FEATURE_AUDIO_OPTICAL) != 0 or \
				(ft & proto.MX_LINK_FEATURE_AUDIO_ANALOG) != 0

	@property
	def is_video(self) -> bool:
		# video link
		return (self.features_mask & proto.MX_LINK_FEATURE_VIDEO) != 0

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
		sb = self.serial_bays
		ob = other.serial_bays
		if len(sb) != len(ob):
			return False
		if (sb[0] == ob[0]):
			return (sb[1] == ob[1])
		if (sb[0] == ob[1]):
			return (sb[1] == ob[0])
		return False

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

