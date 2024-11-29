##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

class PDUOutletState:
	''' pdu outlet state '''
	OFF = 0
	ON = 1
	REBOOTING = 2
	
	def __init__(self, state: int):
		self._state = state

	@property
	def is_on(self) -> bool:
		# outlet powered on
		return (self._state == self.ON)

	@property
	def is_off(self) -> bool:
		# outlet powered off
		return (self._state == self.OFF) or self.is_rebooting

	@property
	def is_rebooting(self) -> bool:
		# outlet rebooting
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
	def __init__(self, frame):
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
		# current (A)
		return self._current

	@property
	def voltage(self) -> float:
		# voltage (V)
		return self._voltage

	@property
	def power(self) -> float:
		# power consumption (W)
		return self._power

	@property
	def dissipation(self) -> float:
		# power dissipation (W)
		return self._dissipation

	@property
	def frequency(self) -> float:
		# AC frequency
		return self._frequency

	@property
	def outlets(self) -> list[PDUOutletState]:
		# list of all outlets defined in this frame
		return self._outlets

	def outlet(self, outlet) -> PDUOutletState:
		# get the state of a single outlet
		return self._outlets[outlet] if outlet < 8 else None

	def __str__(self) -> str:
		return "current = {}A, voltage = {}V, power = {}W, diss = {}W, pf = {}, freq = {}Hz, outlets = {}". \
			format(str(self.current), str(self.voltage), str(self.power), str(self.dissipation), str(self.power_factor), str(self.frequency), str(self.outlets))

