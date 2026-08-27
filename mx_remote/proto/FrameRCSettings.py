######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for remote control settings.'''

from functools import cached_property
from .FrameBase import FrameBase
from .Constants import RCStatus, RCType, MXR_RC_STATUS_NAME_LEN
from ..Interface import DeviceBase
from ..Uid import MxrDeviceUid
import socket
import struct

# mxr_rc_ctrl wire layout. mxr_rc_config is ALIGN(8) but not PACKED, and its
# anonymous bitfield block holds 18 bits in uint16_t containers - so reserved:10
# cannot fit the 8 bits left in the first container and opens a second one. That
# makes the block 4 bytes, not 2. Confirmed by offsetof assertions compiled
# against the MCUXpresso ARM GCC: == 12 builds, == 10 does not.
#
# SINGLE-SOURCED. That measurement has one origin and was relayed here, not
# reproduced. It is a good source - a compiler is a better authority on its own
# packing than any reasoning about the ABI - but nothing independent stands
# behind it, and the failure mode is quiet: a status_name two bytes out lands
# inside the string and yields a plausible truncated name, not garbage. So the
# symptom to act on is a status name that is merely odd - short, or missing its
# first characters - rather than one that is obviously broken. Waiting for
# garbage is waiting for something this bug cannot produce.
#
# One captured 0x45 frame from a unit with a non-empty driver status settles
# 10-vs-12 outright and would retire the question.
#
#   0..16    mxr_uid target
#   16..20   rc_target_t rc          (enum, 4 bytes)
#   20..24   ip_addr_t ip            (ip4_addr_t, a u32 in network order)
#   24..25   flags + rc_status       bits 0..3 flags, bits 4..7 rc_status
#   25..26   unused tail of container #1
#   26..28   container #2, reserved:10
#   28..44   char status_name[16]
#   44..48   tail padding to 48
#
# Everything meaningful in the bitfield block is in byte 24 alone. Do not read
# the block as one little-endian u16 and shift - that is right by accident today
# and wrong the moment `reserved` is spent.
_RC_OFFSET = 16
_IP_OFFSET = 20
_FLAGS_OFFSET = 24
_STATUS_NAME_OFFSET = 28
_STATUS_NAME_SIZE = MXR_RC_STATUS_NAME_LEN + 1

class FrameRCSettings(FrameBase):
    '''Remote control settings for one device, forwarded from a source to the master.'''
    @cached_property
    def target_uid(self) -> MxrDeviceUid | None:
        '''Device these settings belong to.'''
        return self.payload_uuid(0)

    @cached_property
    def target_device(self) -> DeviceBase | None:
        '''Device these settings belong to, if it is known to us.'''
        if ((uid := self.target_uid) is None):
            return None
        return self.mxr.get_by_uid(uid)

    @cached_property
    def rc_target(self) -> RCType | None:
        '''How the target is controlled (IR, CEC, Sky, TiVo, ...).'''
        if ((pl := self.payload_u32(_RC_OFFSET)) is None):
            return None
        try:
            return RCType(pl)
        except ValueError:
            # RC_TARGET_INTERNAL and anything added later: unknown, not an error
            return None

    @cached_property
    def ip(self) -> str | None:
        '''IP address of the controlled device, or None when unset.'''
        pl = self.payload_idx(_IP_OFFSET, _IP_OFFSET + 4)
        if (pl is None) or (len(pl) < 4) or (pl == bytes(4)):
            return None
        return socket.inet_ntoa(struct.pack('!L', int.from_bytes(pl, 'big')))

    @cached_property
    def _flags(self) -> int | None:
        return self.payload_u8(_FLAGS_OFFSET)

    def _flag(self, bit: int) -> bool | None:
        if ((flags := self._flags) is None):
            return None
        return ((flags & (1 << bit)) != 0)

    @cached_property
    def cec_enabled(self) -> bool | None:
        '''CEC control enabled on the target.'''
        return self._flag(0)

    @cached_property
    def cec_auto_on(self) -> bool | None:
        '''Target powers on automatically over CEC.'''
        return self._flag(1)

    @cached_property
    def rc_forward(self) -> bool | None:
        '''Remote control commands are forwarded to the target.'''
        return self._flag(2)

    @cached_property
    def ir_forward(self) -> bool | None:
        '''IR commands are forwarded to the target.'''
        return self._flag(3)

    @cached_property
    def rc_status(self) -> RCStatus | int | None:
        '''Driver state on the source.

        RCStatus.UNKNOWN means the source did not populate the field, which is
        what an older firmware sends - it is not a state. A value above the last
        defined one is returned as the raw int rather than clamped, so a
        firmware update cannot break a caller over an enum it has not seen.
        '''
        if ((flags := self._flags) is None):
            return None
        raw = ((flags >> 4) & 0xF)
        try:
            return RCStatus(raw)
        except ValueError:
            return raw

    @cached_property
    def status_name(self) -> str | None:
        '''Driver-reported status string, or None when the source reported none.

        The array is one byte longer than the longest value it can hold, so a
        full-length name still carries its terminator - but slice to the field
        first regardless, and never scan past it.
        '''
        name = self.payload_str(_STATUS_NAME_OFFSET, _STATUS_NAME_SIZE)
        if (name is None) or (len(name) == 0):
            return None
        return name

    def process(self) -> None:
        '''No-op: settings for a target, reported for visibility rather than cached.'''
        pass

    def __str__(self) -> str:
        target = self.target_device if (self.target_device is not None) else self.target_uid
        parts = [f"target: {self.rc_target}"]
        if (self.ip is not None):
            parts.append(f"ip: {self.ip}")
        if (self.status_name is not None):
            parts.append(f"name: {self.status_name}")
        parts.append(f"status: {self.rc_status}")
        flags = [n for n, v in (("cec", self.cec_enabled), ("cec auto-on", self.cec_auto_on),
                                ("rc forward", self.rc_forward), ("ir forward", self.ir_forward)) if v]
        if flags:
            parts.append(", ".join(flags))
        return f"{target} remote control settings - " + " ".join(f"({p})" for p in parts)
