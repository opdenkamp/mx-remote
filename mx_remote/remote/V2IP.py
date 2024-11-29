##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

import logging
from ..Interface import DeviceV2IPDetailsBase, V2IPStreamSource

_LOGGER = logging.getLogger(__name__)

class DeviceV2IPDetails(DeviceV2IPDetailsBase):
	def __init__(self) -> None:
		self._video = None
		self._audio = None
		self._anc = None
		self._arc = None
		self._tx_rate = None

	@property
	def has_config(self) -> bool:
		return (self._video is not None) and (self._audio is not None) and (self._arc is not None)

	@property
	def video(self) -> V2IPStreamSource|None:
		return self._video

	@video.setter
	def video(self, source:V2IPStreamSource) -> None:
		if source != self._video:
			_LOGGER.debug(f"changed: {str(source)}")
			self._video = source

	@property
	def audio(self) -> V2IPStreamSource:
		return self._audio

	@audio.setter
	def audio(self, source:V2IPStreamSource) -> None:
		if source != self._audio:
			_LOGGER.debug(f"changed: {str(source)}")
			self._audio = source

	@property
	def anc(self) -> V2IPStreamSource:
		return self._anc

	@anc.setter
	def anc(self, source:V2IPStreamSource) -> None:
		if source != self._anc:
			_LOGGER.debug(f"changed: {str(source)}")
			self._anc = source

	@property
	def arc(self) -> V2IPStreamSource:
		return self._arc

	@arc.setter
	def arc(self, source:V2IPStreamSource) -> None:
		if source != self._arc:
			_LOGGER.debug(f"changed: {str(self._arc)} -> {str(source)}")
			self._arc = source

	@property
	def tx_rate(self) -> int:
		return self._tx_rate

	@tx_rate.setter
	def tx_rate(self, rate:int) -> None:
		self._tx_rate = rate

	def __eq__(self, value: object) -> bool:
		if not isinstance(value, DeviceV2IPDetailsBase):
			return False
		return (self.video == value.video) \
			and (self.audio == value.audio) \
			and (self.anc == value.anc) \
			and (self.arc == value.arc) \
			and (self.tx_rate == value.tx_rate)

	def __str__(self) -> str:
		return f"{self.video} {self.audio} {self.anc} {self.arc}"