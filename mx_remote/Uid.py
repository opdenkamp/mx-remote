##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

import logging
import json
_LOGGER = logging.getLogger(__name__)
class MxrDeviceUid:
    ''' Unique ID of an mx_remote device on the network'''

    def __init__(self, value: object) -> None:
        if isinstance(value, MxrDeviceUid):
            self._value = value._value
            return
        if isinstance(value, str):
            spl = value.split(".")
            if len(spl) < 4:
                raise Exception(f"invalid uid {value}")
            self._value = []
            for part in spl:
                self._value += int(part, 16).to_bytes(4, 'little')
            self._value = bytes(self._value)
        elif isinstance(value, bytes):
            if len(value) == 0:
                self._value = None
            elif len(value) < 16:
                raise Exception(f"invalid uid length {len(value)}")
            else:
                self._value = value
        else:
            raise Exception(f"invalid uid type {str(type(value))}")

    def toJson(self):
        return json.dumps(self, default=lambda o: o.__dict__)

    @property
    def value(self) -> str:
        ''' value as human readble string '''
        return ''.join('%02x'%i for i in reversed(self._value[0:4])) + '.' + \
            ''.join('%02x'%i for i in reversed(self._value[4:8])) + '.' + \
            ''.join('%02x'%i for i in reversed(self._value[8:12])) + '.' + \
            ''.join('%02x'%i for i in reversed(self._value[12:16]))

    @property
    def empty(self) -> bool:
        ''' True if all 0 '''
        for v in self._value:
            if int(v) != 0:
                return False
        return True

    @property
    def byte_value(self) -> bytes:
        ''' value as bytes '''
        return self._value

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return str(self)

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, value: object) -> bool:
        if isinstance(value, str) or isinstance(value, MxrDeviceUid):
            return str(self) == str(value)
        return False

    def __hash__(self) -> int:
        return hash(str(self))

class MxrBayUidOld:
    def __init__(self, serial:str, port_name:str) -> None:
        self._serial = serial
        self._port_name = port_name

    @property
    def serial(self) -> str:
        return self._serial

    @property
    def port_name(self) -> str:
        return self._port_name

    @property
    def empty(self) -> bool:
        return (len(self.serial) == 0) or (len(self.port_name) == 0)

    def __str__(self) -> str:
        return f"{self.serial}:{self.port_name}"

    def __eq__(self, value: object) -> bool:
        if isinstance(value, str):
            return (str(self) == value)
        if isinstance(value, MxrBayUidOld):
            return (self.serial == value.serial) and (self.port_name == value.port_name)
        return False

    def __hash__(self) -> int:
        return hash(str(self))

class MxrBayUid:
    def __init__(self, device:MxrDeviceUid, port_number:int) -> None:
        self._device = device
        self._port = port_number

    @property
    def device(self) -> MxrDeviceUid:
        return self._device

    @property
    def port(self) -> int:
        return self._port

    def __hash__(self) -> int:
        return hash(str(self))

    def __str__(self) -> str:
        return f"{str(self.device)}:{self.port}"

    def __repr__(self) -> str:
        return str(self)    

    def __eq__(self, value: object) -> bool:
        if isinstance(value, str):
            return (str(self) == value)
        if not isinstance(value, MxrBayUid):
            return False
        return (self.device == value.device) and (self.port == value.port)

    def __hash__(self) -> int:
        return hash(str(self))
