######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for THIRD_PARTY (opcode 0x55): messages applications
exchange over the mesh.'''

from functools import cached_property
from ..compat import override
from .Constants import ThirdPartyVendorFlag
from .FrameBase import FrameBase
from ..Interface import DeviceRegistry, ThirdPartyMessage, ThirdPartyVendor

# The flag byte at 0 and the three identifying bytes at 1, then the
# application's bytes to the end of the frame.
VENDOR_SIZE = 4

class FrameThirdParty(FrameBase):
	'''An application's own message, under its vendor id.'''
	@staticmethod
	def construct(mxr:DeviceRegistry, vendor:ThirdPartyVendor, payload:bytes) -> FrameBase|None:
		'''A message to every device: the vendor's flag byte and three
		identifying bytes, then payload as it was given.'''
		data = bytes([int(vendor.flags)]) + vendor.id + bytes(payload)
		return FrameBase.construct_base(mxr=mxr, opcode=0x55, payload=data)

	@cached_property
	def message(self) -> ThirdPartyMessage|None:
		'''The message, whatever its vendor: telling them apart is the
		application's. None for a payload too short for the vendor id.
		Everything after the id is the application's, so the length is a
		minimum and nothing past it is read.'''
		p = self.payload or b''
		if (len(p) < VENDOR_SIZE):
			return None
		vendor = ThirdPartyVendor(flags=ThirdPartyVendorFlag(p[0]), id=bytes(p[1:VENDOR_SIZE]))
		return ThirdPartyMessage(vendor=vendor, payload=bytes(p[VENDOR_SIZE:]), address=self.address)

	@override
	def process(self) -> None:
		'''Hand the message to the callbacks, as sent by the device it came from.'''
		if ((message := self.message) is not None) and ((dev := self.remote_device) is not None):
			dev.callbacks.on_third_party_message(dev, message)

	def __str__(self) -> str:
		if (self.message is None):
			return "third-party message <dropped>"
		return f"third-party message from {self.message}"
