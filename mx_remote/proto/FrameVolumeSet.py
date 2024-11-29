##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

from __future__ import annotations
from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from .Data import VolumeMuteStatus, MuteStatus
from ..Interface import BayBase, DeviceBase, DeviceRegistry
from .FrameBase import append_payload_str
from ..Uid import MxrDeviceUid

class FrameVolumeSet(FrameBase):
    ''' bay volume change information frame '''
    def __init__(self, header:FrameHeader):
        super().__init__(header)

    def construct(mxr:DeviceRegistry, target:BayBase, volume:VolumeMuteStatus) -> FrameBase:
        payload = bytearray()
        payload += target.device.remote_id.byte_value
        payload.append(target.port & 0xFF)
        payload.append((target.port >> 8) & 0xFF)
        payload += volume.value
        payload += bytes([0, 0, 0]) # padding
        frame:FrameBase = FrameBase.construct_frame(mxr=mxr, opcode=0x14, protocol=0x11)
        frame.payload = bytes(payload)
        return frame

    @property
    def target_device(self) -> DeviceBase:
        return self.mxr.get_by_uid(self.target_uid)

    @property
    def target_uid(self) -> MxrDeviceUid:
        return MxrDeviceUid(self.payload[0:16])

    @property
    def bay(self)  -> BayBase:
        # bay on which the volume changed
        portnum = ((self.payload[17] << 8) | self.payload[16])
        dev = self.remote_device
        if dev is None:
            return
        return dev.get_by_portnum(portnum)

    @property
    def volume_left(self) -> int:
        # left channel volume %
        r = int(self.payload[18])
        if r > 100:
            return None
        return r

    @property
    def volume_right(self) -> int:
        # right channel volume %
        r = int(self.payload[19])
        if r > 100:
            return None
        return r

    @property
    def muted(self) -> MuteStatus:
        # mute status
        return MuteStatus(self.payload[20])

    def process(self) -> None:
        # update the local cache
        bay = self.bay
        if bay is None:
            return
        muted = self.muted
        muted_left = muted.left if (muted is not None) else None
        muted_right = muted.right if (muted is not None) else None
        bay.on_mxr_volume_update(VolumeMuteStatus(self.volume_left, self.volume_right, muted_left, muted_right))

    def __str__(self) -> str:
        return f"volume bay:{str(self.bay)} volume:{self.volume_left}/{self.volume_right} muted:{self.muted}"
