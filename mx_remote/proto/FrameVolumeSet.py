######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for setting bay volume and mute status.'''

from __future__ import annotations
from functools import cached_property
from .FrameBase import FrameBase
from .Data import VolumeMuteStatus, MuteStatus, MXR_AUDIO_DONT_CHANGE
from ..Interface import BayBase, DeviceBase, DeviceRegistry
from ..Uid import MxrDeviceUid

# mxr_set_volume_request is ALIGN(8): target uid at 0, u16 bay at 16, left
# volume at 18, right volume at 19, mute at 20, and three bytes of tail padding
# out to 24.
#
# Units old enough to predate the widening of the bay id address the target by
# serial and carry a one-byte bay, which puts the three settings at 17, 18 and
# 19 and makes the whole payload 20 bytes. Both forms stamp the same protocol
# floor, so the length is what separates them.
_WIRE_SIZE = 24
_LEGACY_SIZE = 20

class FrameVolumeSet(FrameBase):
    '''Bay volume set command and notification frame.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:BayBase, volume:VolumeMuteStatus) -> FrameBase|None:
        '''Build a volume set frame for transmission.'''
        payload = bytearray()
        payload += target.device.remote_id.byte_value
        payload.append(target.port & 0xFF)
        payload.append((target.port >> 8) & 0xFF)
        payload += volume.value
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x14, protocol=0x11,
                                        payload=payload, size=_WIRE_SIZE)

    @cached_property
    def target_device(self) -> DeviceBase|None:
        '''Target device for the volume change.'''
        return self.mxr.get_by_uid(self.target_uid)

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        '''UID of the target device.'''
        return self.payload_uuid(0)

    @cached_property
    def _legacy(self) -> bool:
        '''Whether the sender used the one-byte bay id addressed by serial.

        The legacy form is exactly _LEGACY_SIZE bytes, so anything longer is the
        current one - a sender that stops after the fields it set, without the
        tail padding out to _WIRE_SIZE, still reads as current.
        '''
        pl = self.payload
        return (pl is not None) and (len(pl) <= _LEGACY_SIZE)

    @cached_property
    def bay(self)  -> BayBase|None:
        '''Bay on which the volume changed.

        The port belongs to the device the payload addresses, not to the one
        that sent the frame: a controller sets the volume of a bay it does not
        own, and the two uids differ for every such frame.
        '''
        dev = self.target_device
        if (dev is None):
            return None
        portnum = self.payload_u8(16) if self._legacy else self.payload_u16(16)
        if (portnum is None):
            return None
        return dev.get_by_portnum(portnum)

    def _volume(self, idx:int) -> int|None:
        r = self.payload_u8(idx)
        if (r is None) or (r > 100):
            return None
        return r

    @cached_property
    def volume_left(self) -> int|None:
        '''Left channel volume percentage, or None when the sender set none.'''
        return self._volume(17 if self._legacy else 18)

    @cached_property
    def volume_right(self) -> int|None:
        '''Right channel volume percentage, or None when the sender set none.'''
        return self._volume(18 if self._legacy else 19)

    @cached_property
    def muted(self) -> MuteStatus|None:
        '''Mute status, or None when the sender asked for it to be left alone.'''
        r = self.payload_u8(19 if self._legacy else 20)
        if (r is None) or (r == MXR_AUDIO_DONT_CHANGE):
            return None
        return MuteStatus(r)

    def process(self) -> None:
        '''Update the local device cache with the new volume and mute status.'''
        bay = self.bay
        if bay is None:
            return
        muted = self.muted
        muted_left = muted.left if (muted is not None) else None
        muted_right = muted.right if (muted is not None) else None
        bay.on_mxr_update(VolumeMuteStatus(self.volume_left, self.volume_right, muted_left, muted_right))

    def __str__(self) -> str:
        return f"volume bay:{str(self.bay)} volume:{self.volume_left}/{self.volume_right} muted:{self.muted}"
