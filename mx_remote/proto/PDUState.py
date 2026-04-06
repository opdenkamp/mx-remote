##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''PDU (Power Distribution Unit) state and outlet status parsing.'''

from typing import Any

class PDUOutletState:
	'''State of a single PDU outlet (on, off, or rebooting).'''
	OFF = 0
	ON = 1
	REBOOTING = 2
	
	def __init__(self, state: int):
		self._state = state

	@property
	def is_on(self) -> bool:
		'''Whether the outlet is powered on.'''
		return (self._state == self.ON)

	@property
	def is_off(self) -> bool:
		'''Whether the outlet is powered off or rebooting.'''
		return (self._state == self.OFF) or self.is_rebooting

	@property
	def is_rebooting(self) -> bool:
		'''Whether the outlet is currently rebooting.'''
		return (self._state == self.REBOOTING)

	def __str__(self) -> str:
		if self._state == self.ON:
			return "ON"
		elif self._state == self.OFF:
			return "OFF"
		elif self._state == self.REBOOTING:
			return "REBOOTING"
		return "Unknown"

	def __repr__(self) -> str:
		return str(self)

class PDUState:
	'''Aggregated PDU state including power readings and outlet states.'''

	def __init__(self, frame:Any) -> None:
		self._current     = frame.current
		self._voltage     = frame.voltage
		self._power       = frame.power
		self._dissipation = frame.dissipation
		self._frequency   = frame.frequency

		self._outlets = []
		ptr = 0
		while ptr < 8:
			self._outlets.append(PDUOutletState(frame.outlet_state(ptr)))
			ptr = ptr + 1

	@property
	def current(self) -> float:
		'''Current draw in amperes.'''
		return self._current

	@property
	def voltage(self) -> float:
		'''Voltage in volts.'''
		return self._voltage

	@property
	def power(self) -> float:
		'''Power consumption in watts.'''
		return self._power

	@property
	def dissipation(self) -> float:
		'''Power dissipation in watts.'''
		return self._dissipation

	@property
	def frequency(self) -> float:
		'''AC frequency in hertz.'''
		return self._frequency

	@property
	def outlets(self) -> list[PDUOutletState]:
		'''List of all outlet states in this frame.'''
		return self._outlets

	def outlet(self, outlet:int) -> PDUOutletState|None:
		'''Get the state of a single outlet by index, or None if out of range.'''
		return self._outlets[outlet] if outlet < 8 else None

	def __str__(self) -> str:
		return "current = {}A, voltage = {}V, power = {}W, diss = {}W, pf = {}, freq = {}Hz, outlets = {}". \
			format(str(self.current), str(self.voltage), str(self.power), str(self.dissipation), str(self.power_factor), str(self.frequency), str(self.outlets))

