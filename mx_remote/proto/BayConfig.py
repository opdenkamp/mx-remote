######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################

'''Bay configuration data parsed from bay config protocol frames.'''

from __future__ import annotations
from functools import cached_property
from .Constants import BayStatusMask, BayFeaturesMask, MxrSignalType, MXR_CFG_SIGNAL_STATUS_LEN
import struct

class BayConfig:
	''' Bay configuration for a remote device '''
	def __init__(self, payload:bytes) -> None:
		self.payload = payload

	@cached_property
	def port(self) -> int:
		'''Port number.'''
		return int(self.payload[0])

	@cached_property
	def modenum(self) -> int:
		'''Port mode number.'''
		return int(self.payload[1])

	@cached_property
	def mode(self) -> str:
		'''Port mode as string (Input/Output).'''
		nb = self.modenum
		if nb == 0:
			return 'Input'
		if nb == 1:
			return 'Output'
		return 'Unknown'

	@cached_property
	def is_input(self) -> bool:
		'''True if this is an input bay.'''
		return self.modenum == 0

	@cached_property
	def is_output(self) -> bool:
		'''True if this is an output bay.'''
		return self.modenum == 1

	@cached_property
	def bay(self) -> int:
		'''Bay number.'''
		return int(self.payload[2])

	@cached_property
	def video_source(self) -> int:
		'''Video source bay number.'''
		return int(self.payload[3])

	@cached_property
	def edid_profile(self) -> int:
		return ((int(self.payload[4]) & 0xF) << 8) | int(self.payload[3])

	@cached_property
	def rc_type(self) -> int:
		return ((int(self.payload[4]) >> 4) & 0xF)

	@cached_property
	def audio_source(self) -> int:
		'''Audio source bay number.'''
		return int(self.payload[4])

	@cached_property
	def bay_name(self) -> str:
		'''Bay name.'''
		return self.payload[5:21].split(b'\0',1)[0].decode('ascii', errors='replace')

	@cached_property
	def user_name(self) -> str:
		'''User-assigned name.'''
		return self.payload[21:37].split(b'\0',1)[0].decode('ascii', errors='replace')

	@cached_property
	def signal_type(self) -> str:
		'''Video signal description.

		mxr_cfg_signal is 14 bytes of description followed by a 2-byte
		mxr_signal_type, so reading 16 runs a full-width description into
		the type bytes.
		'''
		end = 37 + MXR_CFG_SIGNAL_STATUS_LEN
		return self.payload[37:end].split(b'\0',1)[0].decode('ascii', errors='replace')

	@cached_property
	def signal(self) -> MxrSignalType|None:
		'''Signal type this bay reports, or None on a short record.

		Bay config is broadcast for every bay, where a signal status report
		covers only its own, so this is the wider source of the same field.
		'''
		start = 37 + MXR_CFG_SIGNAL_STATUS_LEN
		if len(self.payload) < (start + 2):
			return None
		return MxrSignalType(self.payload[start:start + 2])

	@cached_property
	def status(self) -> BayStatusMask:
		'''Bay status.'''
		return BayStatusMask(struct.unpack('<L', self.payload[53:57])[0])

	@cached_property
	def features(self) -> BayFeaturesMask:
		'''Features mask.'''
		return BayFeaturesMask(struct.unpack('<L', self.payload[57:61])[0])

	def __str__(self) -> str:
		return f"{self.mode} {self.bay + 1} (port {self.port}): {self.user_name} - {self.signal_type}"

	def bay_match(self, other: BayConfig) -> bool:
		'''Check whether other is a configuration for the same bay as this one.'''
		return (self.port == other.port) and \
				(self.modenum == other.modenum) and \
				(self.bay == other.bay) and \
				(self.features == other.features)

