######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''A dedicated mesh controller's CONTROLLER_STATE (0x58): the hello this client
sends as one, the parts of its state it serves, and the parts of another's it
pulls.'''

from ..Interface import ControllerHello, ControllerPart, DeviceBase
from ..proto.Constants import ControllerRole
from ..proto.FrameControllerState import DATA_MAX, KIND_DATA, KIND_REQUEST, WINDOW_MAX, StateHeader
from ..proto.FrameMeshConfig import crc32
from ..Uid import MxrDeviceUid

HELLO_EVERY = 10.0
'''How often a dedicated controller sends its CONTROLLER_STATE hello, right
after a hello to every unit, in seconds.'''

PULL_RETRY = 2.0
'''How long a pull waits for data before asking again from the first byte it
does not have, in seconds.'''

PULL_ASKS = 10
'''How many asks in a row without a byte of progress a pull makes before it
gives up.'''

class OwnController:
    '''What this client announces of itself as a dedicated controller, and
    serves to another.'''

    def __init__(self) -> None:
        self.role:ControllerRole|int = ControllerRole.NONE
        self.primary:MxrDeviceUid|None = None
        self.generation = 0
        self.parts:list[tuple[int, bytes, int]] = []
        '''Each part, its bytes and their crc32, in the order the hello lists
        them.'''
        self.sent:float|None = None
        '''When the hello last went out, None since the sockets opened.'''

    def hello(self) -> ControllerHello:
        '''The hello this client sends.'''
        return ControllerHello(role=self.role, generation=self.generation, primary=self.primary,
                               parts=tuple(ControllerPart(part=part, length=len(data), crc=crc)
                                           for part, data, crc in self.parts))

    def due(self, now:float) -> bool:
        '''Whether the hello that follows a hello to every unit goes now, which
        then counts as sent. Until a unit has had one it does not know this
        client is a dedicated controller, so the first follows the first
        hello.'''
        if (self.sent is not None) and ((now - self.sent) < HELLO_EVERY):
            return False
        self.sent = now
        return True

    def answer(self, request:StateHeader) -> list[tuple[StateHeader, bytes]]:
        '''The data frames answering request: the window it asks for, at most
        WINDOW_MAX bytes, in frames of at most DATA_MAX. One frame without bytes
        for a request past the end, and for one of a generation no longer held,
        which carries the current generation. A part not held is answered as an
        empty one.'''
        data, crc = next(((d, c) for part, d, c in self.parts if (part == request.part)), (b'', crc32(b'')))
        def frame(offset:int, chunk:bytes=b'') -> tuple[StateHeader, bytes]:
            return (StateHeader(kind=KIND_DATA, part=request.part, generation=self.generation, offset=offset,
                                length=len(data), crc=crc), chunk)
        if (request.generation != self.generation) or (request.offset >= len(data)):
            return [frame(request.offset)]
        end = min(len(data), request.offset + min(request.length, WINDOW_MAX))
        return [frame(offset, data[offset:min(offset + DATA_MAX, end)])
                for offset in range(request.offset, end, DATA_MAX)]

class ControllerPull:
    '''One part of another dedicated controller's state being pulled.'''

    def __init__(self, device:DeviceBase, part:int, generation:int, length:int, crc:int, now:float) -> None:
        self.device = device
        self.part = part
        self.generation = generation
        self.length = length
        self.crc = crc
        self.data = bytearray()
        self.window_end = 0
        '''The end of the window last asked for.'''
        self.last = now
        '''When it last asked or took bytes.'''
        self.idle_asks = 0
        '''Asks since the last byte taken.'''
        self.broken = False
        '''A frame out of order or of another generation ended the window, and
        it asked again: further such frames, the rest of that window, are
        dropped until the answer starts.'''

    def ask(self, now:float) -> StateHeader:
        '''The request for the next window, from the first byte it does not
        have.'''
        offset = len(self.data)
        count = min(self.length - offset, WINDOW_MAX)
        self.window_end = offset + count
        self.last = now
        return StateHeader(kind=KIND_REQUEST, part=self.part, generation=self.generation, offset=offset, length=count)

    def take(self, header:StateHeader, data:bytes, now:float, asks:list[StateHeader]) -> bool|None:
        '''Take one data frame: None while pulling, True once whole with its
        crc32 matching, False when the pull failed. A request it raises is
        added to asks.'''
        if (header.generation != self.generation):
            # No bytes and the current generation: the sender no longer holds
            # the one asked for.
            return False if not data else self._restart(now, asks)
        if (header.length != self.length) or (header.crc != self.crc):
            # Not the part its hello described.
            return False
        if not data or (header.offset != len(self.data)):
            return self._restart(now, asks)
        self.data += data[:self.length - len(self.data)]
        self.broken = False
        self.last = now
        self.idle_asks = 0
        if (len(self.data) == self.length):
            return (crc32(bytes(self.data)) == self.crc)
        if (len(self.data) >= self.window_end):
            asks.append(self.ask(now))
        return None

    def retry(self, now:float, asks:list[StateHeader]) -> bool|None:
        '''Ask again after PULL_RETRY without data: None while pulling, False
        once PULL_ASKS asks went without progress.'''
        if ((now - self.last) < PULL_RETRY):
            return None
        if (self.idle_asks >= PULL_ASKS):
            return False
        self.idle_asks += 1
        self.broken = False
        asks.append(self.ask(now))
        return None

    def _restart(self, now:float, asks:list[StateHeader]) -> bool|None:
        '''A frame out of order, or bytes of another generation, end the
        window: ask again from the first byte it does not have, once until the
        answer starts arriving.'''
        if not self.broken:
            if (self.idle_asks >= PULL_ASKS):
                return False
            self.idle_asks += 1
            self.broken = True
            asks.append(self.ask(now))
        return None
