######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''What this client announces of itself as a dedicated mesh controller, such as
a router, in its CONTROLLER_STATE (0x58) hello.'''

from ..Interface import ControllerHello
from ..proto.Constants import ControllerRole
from ..Uid import MxrDeviceUid

HELLO_EVERY = 10.0
'''How often a dedicated controller sends its CONTROLLER_STATE hello, right
after a hello to every unit, in seconds.'''

class OwnController:
    '''The role and primary this client announces as a dedicated controller,
    and when its hello last went out.'''

    def __init__(self) -> None:
        self.role:ControllerRole|int = ControllerRole.NONE
        self.primary:MxrDeviceUid|None = None
        self.generation = 0
        self.sent:float|None = None
        '''When the hello last went out, None since the sockets opened.'''

    def hello(self) -> ControllerHello:
        '''The hello this client sends.'''
        return ControllerHello(role=self.role, generation=self.generation, primary=self.primary)

    def due(self, now:float) -> bool:
        '''Whether the hello that follows a hello to every unit goes now, which
        then counts as sent. Until a unit has had one it does not know this
        client is a dedicated controller, so the first follows the first
        hello.'''
        if (self.sent is not None) and ((now - self.sent) < HELLO_EVERY):
            return False
        self.sent = now
        return True
