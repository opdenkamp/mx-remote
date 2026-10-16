######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for BAY_CONTENT (opcode 0x51): what the source on an input is
showing, as a unit with a source driver reports it.'''

from functools import cached_property
from ..compat import override
from .Constants import BAY_CONTENT_KEY_MAX, BAY_CONTENT_VALUE_MAX
from .FrameBase import FrameBase
from ..Interface import BayBase, BayContent, BayContentField

# The input's port is a u16 at 0, and every field behind it is a key and a
# value, each NUL terminated, packed back to back up to the end of the payload.
# A report with no fields says the input shows nothing now. Units send it on
# change and repeat it on every broadcast, so there is no request.
_CONTENT_PORTS = 12
'''The ports a unit reports content for are below this.'''

_KEY_BYTES = frozenset(b'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-')

def clean_key(raw:bytes) -> str:
    '''A key as a unit keeps it: letters, digits, _ and - only, cut to
    BAY_CONTENT_KEY_MAX bytes.'''
    return bytes(b for b in raw if b in _KEY_BYTES)[:BAY_CONTENT_KEY_MAX].decode('ascii')

def clean_value(raw:bytes) -> str:
    '''A value as a unit keeps it: control characters, " and \\ dropped, then
    every byte that is not part of a valid UTF-8 character, then the rest cut to
    BAY_CONTENT_VALUE_MAX bytes before a character that would not fit whole.'''
    kept = bytes(b for b in raw if (b >= 0x20) and (b not in (0x7F, ord('"'), ord('\\'))))
    text = kept.decode('utf-8', errors='ignore')
    return text.encode('utf-8')[:BAY_CONTENT_VALUE_MAX].decode('utf-8', errors='ignore')

class FrameBayContent(FrameBase):
    '''What the source on one of the sender's inputs is showing.'''
    @cached_property
    def port(self) -> int|None:
        '''The input's port, None for a frame too short to name one.'''
        return self.payload_u16(0)

    @cached_property
    def content(self) -> BayContent:
        '''The fields, each cleaned as a receiving unit cleans it, so this shows
        what a unit's own API would. A field that is empty once cleaned, or
        whose key an earlier field already gave, is dropped, and so is a value
        no NUL terminates.'''
        pieces = (self.payload or b'')[2:].split(b'\0')
        fields:list[BayContentField] = []
        # split() yields what follows the last NUL as one more piece, so a
        # value is terminated only when another piece comes after it.
        for at in range(0, len(pieces) - 2, 2):
            key, value = clean_key(pieces[at]), clean_value(pieces[at + 1])
            if (key == '') or (value == '') or any(f.key == key for f in fields):
                continue
            fields.append(BayContentField(key=key, value=value))
        return BayContent(fields)

    @cached_property
    def bay(self) -> BayBase|None:
        '''The input the content is about, None for a port no unit running the
        module has an input on.'''
        if ((port := self.port) is None) or (port >= _CONTENT_PORTS):
            return None
        return self.payload_bay(device=self.remote_device, idx=0, u16=True)

    @override
    def process(self) -> None:
        '''Record the content against the input it is about.'''
        if ((bay := self.bay) is not None):
            bay.on_mxr_update(self.content)

    def __str__(self) -> str:
        return f"bay content {self.bay}: {self.content}"
