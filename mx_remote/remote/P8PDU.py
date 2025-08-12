##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from ..proto.PDUState import PDUState
from typing import Any, List

class PDUOutlet:
    ''' One of the 8 PDU outlets '''

    def __init__(self, pdu: Any, port: int, state: PDUState):
        self._pdu = pdu
        self._port = port
        self._state = state

    @property
    def port(self) -> int:
        # port number
        return self._port

    @property
    def state(self) -> PDUState:
        return self._state

    @state.setter
    def state(self, val: PDUState):
        self._state = val

    @property
    def is_on(self) -> bool:
        return self._state.is_on

    @property
    def is_off(self) -> bool:
        return self._state.is_off

    @property
    def is_rebooting(self) -> bool:
        return self._state.is_rebooting

    async def turn_on(self):
        return await self._pdu.dev.get_api('power/on/{}'.format(self.port))

    async def turn_off(self):
        return await self._pdu.dev.get_api('power/off/{}'.format(self.port))

    def __str__(self) -> str:
        return str(self._state)

    def __repr__(self) -> str:
        return "{}={}".format(str(self._port), str(self))

class PDU:
    ''' Optional PDU connected to a matrix '''
    def __init__(self, dev, init_val:PDUState):
        self._dev = dev
        self._val = None
        self._outlets = []
        self.on_mxr_update(init_val)

    @property
    def dev(self):
        return self._dev

    @property
    def mxr(self) -> Any:
        # mxremote instance
        return self._dev.mxr

    @property
    def connected(self) -> bool:
        voltage = self.voltage
        return (voltage is not None) and (voltage > 0.0)

    @property
    def current(self) -> float:
        if self._val is None:
            return None
        return self._val.current

    @property
    def voltage(self) -> float:
        if self._val is None:
            return None
        return self._val.voltage

    @property
    def power(self) -> float:
        if self._val is None:
            return None
        return self._val.power

    @property
    def dissipation(self) -> float:
        if self._val is None:
            return None
        return self._val.dissipation

    @property
    def power_factor(self) -> float:
        if self._val is None:
            return None
        return self._val.power_factor

    @property
    def frequency(self) -> float:
        if self._val is None:
            return None
        return self._val.frequency

    @property
    def outlets(self) -> List[PDUOutlet]:
        if self._val is None:
            return None
        return self._outlets

    def outlet(self, port) -> PDUOutlet:
        if self._val is None:
            return None
        return self._outlets[port]

    def on_mxr_update(self, pdu_state:PDUState) -> None:
        changed = self._val is None or (self._val != pdu_state)
        is_new = (len(self._outlets) == 0)
        self._val = pdu_state
        port = 0
        for outlet in pdu_state.outlets:
            if is_new:
                self._outlets.append(PDUOutlet(self, port, outlet))
            else:
                self._outlets[port].state = outlet
            port = port + 1
        if changed and not is_new:
            # tell callbacks that this device changed
            self.mxr.on_pdu_changed(self)

    def __str__(self) -> str:
        return "current = {}A, voltage = {}V, power = {}W, diss = {}W, freq = {}Hz, outlets = {}".format(str(self.current), str(self.voltage), str(self.power), str(self.dissipation), str(self.frequency), str(self.outlets))

    def __repr__(self) -> str:
        return str(self)

    def __eq__(self, other) -> bool:
        return isinstance(other, PDU) and \
            (self.dev == other.dev)

    def __ne__(self, other) -> bool:
        return (not isinstance(other, PDU)) or \
            (self.dev != other.dev)
