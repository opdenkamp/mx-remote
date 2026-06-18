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
from .Data import VolumeMuteStatus, MuteStatus
from ..Interface import BayBase, DeviceBase, DeviceRegistry
from ..Uid import MxrDeviceUid

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
        payload += bytes([0, 0, 0]) # padding
        return FrameBase.construct_base(mxr=mxr, opcode=0x14, protocol=0x11, payload=payload)

    @cached_property
    def target_device(self) -> DeviceBase|None:
        '''Target device for the volume change.'''
        return self.mxr.get_by_uid(self.target_uid)

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        '''UID of the target device.'''
        return self.payload_uuid(0)

    @cached_property
    def bay(self)  -> BayBase|None:
        '''Bay on which the volume changed.'''
        portnum = self.payload_u16(16)
        if (portnum is None):
            return None
        dev = self.remote_device
        if (dev is None):
            return
        return dev.get_by_portnum(portnum)

    @cached_property
    def volume_left(self) -> int|None:
        '''Left channel volume percentage.'''
        r = self.payload_u8(18)
        if (r is None) or (r > 100):
            return None
        return r

    @cached_property
    def volume_right(self) -> int|None:
        '''Right channel volume percentage.'''
        r = self.payload_u8(19)
        if (r is None) or (r > 100):
            return None
        return r

    @cached_property
    def muted(self) -> MuteStatus|None:
        '''Mute status.'''
        r = self.payload_u8(20)
        if (r is None):
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
