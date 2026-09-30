######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame carrying the time zone of a mesh.'''

from functools import cached_property
from ..compat import override
from .FrameBase import FrameBase
from ..Interface import DeviceRegistry, TimeZone

# Payload: the IANA name in a 48-byte field, then the POSIX rule in a 64-byte
# one, each NUL-terminated inside its field.
#
# The mesh controller announces it with every periodic broadcast, and each
# device of the mesh keeps its clock and its power save windows by it. A device
# takes one only from the controller or a management application. A controller
# without a time zone announces both fields empty, and its members keep UTC.
TIME_ZONE_NAME_LEN = 48
'''Bytes a time zone's IANA name takes on the wire, its terminating NUL included.'''
TIME_ZONE_RULE_LEN = 64
'''Bytes a time zone's POSIX rule takes on the wire, its terminating NUL included.'''

def _fits(value:str, length:int) -> bool:
    raw = value.encode('utf-8')
    return (0 < len(raw) < length) and (b'\0' not in raw)

class FrameTimeZone(FrameBase):
    '''The time zone a device announces for its mesh.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, zone:str, rule:str) -> FrameBase|None:
        '''Build the broadcast that sets the time zone of every device hearing it.

        None when either string is empty, holds a NUL, or leaves no room in its
        field for the terminating NUL.'''
        if not _fits(zone, TIME_ZONE_NAME_LEN) or not _fits(rule, TIME_ZONE_RULE_LEN):
            return None
        return FrameTimeZone._construct(mxr=mxr, zone=zone, rule=rule)

    @staticmethod
    def construct_clear(mxr:DeviceRegistry) -> FrameBase|None:
        '''Build the broadcast that clears the time zone of every device hearing
        it: both fields empty, which construct() refuses.'''
        return FrameTimeZone._construct(mxr=mxr, zone='', rule='')

    @staticmethod
    def _construct(mxr:DeviceRegistry, zone:str, rule:str) -> FrameBase|None:
        payload = zone.encode('utf-8').ljust(TIME_ZONE_NAME_LEN, b'\0') \
            + rule.encode('utf-8').ljust(TIME_ZONE_RULE_LEN, b'\0')
        return FrameBase.construct_base(mxr=mxr, opcode=0x4B, payload=payload)

    @cached_property
    def time_zone(self) -> TimeZone|None:
        '''The announced time zone, None for a frame too short to hold both fields.'''
        p = self.payload
        if (p is None) or (len(p) < (TIME_ZONE_NAME_LEN + TIME_ZONE_RULE_LEN)):
            return None
        def field(raw:bytes) -> str:
            return raw.split(b'\0', 1)[0].decode('utf-8', errors='replace')
        return TimeZone(zone=field(p[:TIME_ZONE_NAME_LEN]),
                        rule=field(p[TIME_ZONE_NAME_LEN:TIME_ZONE_NAME_LEN + TIME_ZONE_RULE_LEN]))

    @override
    def process(self) -> None:
        '''Record the time zone against the device that announced it.'''
        if ((tz := self.time_zone) is not None) and (self.remote_device is not None):
            self.remote_device.on_mxr_update(tz)

    def __str__(self) -> str:
        return f"time zone {self.time_zone}"
