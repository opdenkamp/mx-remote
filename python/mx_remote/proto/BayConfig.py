from __future__ import annotations
import logging
import struct
from typing import Any

class BayStatusMask:
	FAULT = (1 << 0)
	HIDDEN = (1 << 1)
	POWERED = (1 << 2)
	SIGNAL_DETECTED = (1 << 3)
	HPD_DETECTED = (1 << 4)
	SIGNAL_SCRAMBLED =(1 << 5)
	HDBT_CONNECTED = (1 << 6)
	CEC_DETECTED = (1 << 7)
	POWERED_ON = (1 << 8)
	POWERED_OFF = (1 << 9)
	AUDIO_ARC_HDMI = (1 << 10)
	AUDIO_ARC_OPTICAL = (1 << 11)
	AUDIO_ARC_ANALOG = (1 << 12)

	def __init__(self, mask:int):
		self._mask = mask

	@property
	def fault(self) -> bool:
		# bay is faulty
		return (self._mask & self.FAULT) != 0

	@property
	def hidden(self) -> bool:
		# bay is hidden
		return (self._mask & self.HIDDEN) != 0

	@property
	def powered(self) -> bool:
		# PoE powered on
		return (self._mask & self.POWERED) != 0

	@property
	def signal_detected(self) -> bool:
		# signal detected
		return (self._mask & self.SIGNAL_DETECTED) != 0

	@property
	def hpd_detected(self) -> bool:
		# hotplug detected
		return (self._mask & self.HPD_DETECTED) != 0

	@property
	def hdbt_connected(self) -> bool:
		# HDBaseT connected
		return (self._mask & self.HDBT_CONNECTED) != 0

	@property
	def cec_detected(self) -> bool:
		# CEC capable device connected to this bay
		return (self._mask & self.CEC_DETECTED) != 0

	@property
	def powered_on(self) -> bool:
		# device is powered on
		return (self._mask & self.POWERED_ON) != 0

	@property
	def powered_off(self) -> bool:
		# device is powered off
		return (self._mask & self.POWERED_OFF) != 0

	@property
	def audio_arc_hdmi(self) -> bool:
		# HDMI ARC active
		return (self._mask & self.AUDIO_ARC_HDMI) != 0

	@property
	def audio_arc_optical(self) -> bool:
		# optical ARC active
		return (self._mask & self.AUDIO_ARC_OPTICAL) != 0

	@property
	def audio_arc_analog(self) -> bool:
		# analog ARC active
		return (self._mask & self.AUDIO_ARC_ANALOG) != 0

	def __str__(self) -> str:
	  rv = ""
	  if self.fault:
		  rv += " [fault]"
	  if self.hidden:
		  rv += " [hidden]"
	  if self.powered:
		  rv += " [powered]"
	  if self.signal_detected:
		  rv += " [signal]"
	  if self.hpd_detected:
		  rv += " [hpd]"
	  if self.hdbt_connected:
		  rv += " [hdbt]"
	  if self.cec_detected:
		  rv += " [cec]"
	  if self.powered_on:
		  rv += " [powered on]"
	  if self.powered_off:
		  rv += " [powered off]"
	  if self.audio_arc_hdmi:
		  rv += " [hdmi arc]"
	  if self.audio_arc_optical:
		  rv += " [optical arc]"
	  if self.audio_arc_analog:
		  rv += " [analog arc]"
	  if len(rv) != 0:
		  return rv[1:]
	  return "[none]"


	def __eq__(self, mask:int) -> bool:
		return self._mask == mask._mask

	def __ne__(self, mask:int) -> bool:
		return self._mask != mask._mask

class BayConfig:
	''' Bay configuration for a remote device '''
	def __init__(self, payload:bytes):
		self.payload = payload

	@property
	def port(self) -> int:
		# port number
		return int(self.payload[0])

	@property
	def modenum(self) -> int:
		# port mode number
		return int(self.payload[1])

	@property
	def mode(self) -> str:
		# port mode
		nb = self.modenum
		if nb == 0:
			return 'Input'
		if nb == 1:
			return 'Output'
		return 'Unknown'

	@property
	def is_input(self) -> bool:
		# input bay
		return self.modenum == 0

	@property
	def is_output(self) -> bool:
		# output bay
		return self.modenum == 1

	@property
	def bay(self) -> int:
		# bay number
		return int(self.payload[2])

	@property
	def video_source(self) -> int:
		# video source bay number
		return int(self.payload[3])

	@property
	def audio_source(self) -> int:
		# audio source bay number
		return int(self.payload[4])

	@property
	def bay_name(self) -> str:
		# bay name
		return self.payload[5:21].split(b'\0',1)[0].decode('ascii')

	@property
	def user_name(self) -> str:
		# user set name
		return self.payload[21:37].split(b'\0',1)[0].decode('ascii')

	@property
	def signal_type(self) -> str:
		# video signal type
		return self.payload[37:53].split(b'\0',1)[0].decode('ascii')

	@property
	def status(self) -> BayStatusMask:
		# bay status
		return BayStatusMask(struct.unpack('<L', self.payload[53:57])[0])

	@property
	def features(self) -> int:
		# features mask
		return struct.unpack('<L', self.payload[57:61])[0]

	def __str__(self) -> str:
		return "{} {}: {}".format(self.mode, str(self.bay + 1), self.user_name)

	def bay_match(self, other: BayConfig) -> bool:
		# check whether other is a configuration for the same bay as this one
		return (self.port == other.port) and \
				(self.modenum == other.modenum) and \
				(self.bay == other.bay) and \
				(self.features == other.features)

