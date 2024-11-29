##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from ..Interface import MxrCallbacks
import aiohttp

class State:
    def __init__(self, callbacks:MxrCallbacks|None=None, http_session:aiohttp.ClientSession|None=None) -> None:
        if callbacks is None:
            self._callbacks = MxrCallbacks()
        else:
            self._callbacks = callbacks
        self._close_session = (http_session is not None)
        self._http_session = http_session

    @property
    def http_session(self) -> aiohttp.ClientSession:
        if self._http_session is None:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    @property
    def callbacks(self) -> MxrCallbacks:
        return self._callbacks
