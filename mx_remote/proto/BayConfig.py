##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from __future__ import annotations
from .Constants import BayStatusMask
import struct

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
	def edid_profile(self) -> int:
		return ((int(self.payload[4]) & 0xF) << 8) | int(self.payload[3])

	@property
	def rc_type(self) -> int:
		return ((int(self.payload[4]) > 4) & 0xF)

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
		return f"{self.mode} {self.bay + 1} (port {self.port}): {self.user_name} - {self.signal_type}"

	def bay_match(self, other: BayConfig) -> bool:
		# check whether other is a configuration for the same bay as this one
		return (self.port == other.port) and \
				(self.modenum == other.modenum) and \
				(self.bay == other.bay) and \
				(self.features == other.features)

