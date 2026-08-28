######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for EDID profile change commands.'''

from .FrameBase import FrameBase
from ..Interface import DeviceRegistry, DeviceBase, EdidProfile, MxrDeviceUid
from .Constants import decode_enum

class FrameEDIDProfile(FrameBase):
    '''Change an EDID profile on a target device.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:DeviceBase, profile:EdidProfile) -> FrameBase|None:
        '''Build an EDID profile change frame for transmission.'''
        payload = target.remote_id.byte_value + \
            bytes([(profile.value >> 0) & 0xFF, (profile.value >> 8) & 0xFF]) + \
            bytes([0 for _ in range(6)])
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x34, payload=payload)

    @property
    def target_uid(self) -> MxrDeviceUid|None:
        '''Device whose EDID profile is being set.'''
        return self.payload_uuid(0)

    @property
    def target_device(self) -> DeviceBase|None:
        return self.mxr.get_by_uid(self.target_uid)

    @property
    def profile_raw(self) -> int|None:
        '''Profile as carried on the wire, before mapping to a local one.'''
        return self.payload_u16(16)

    @property
    def profile(self) -> EdidProfile|None:
        '''Requested EDID profile.

        A value this build has no member for reads as EdidProfile.UNKNOWN rather
        than raising or being folded into a real profile. Read profile_raw when
        the distinction matters.
        '''
        return decode_enum(EdidProfile, self.profile_raw)

    def __str__(self) -> str:
        # The frame names no bay because it never needs to: the receiver applies it
        # to MBAY_ID_0, its own input bay, so a device is the whole address.
        target = self.target_device if (self.target_device is not None) else self.target_uid
        profile = f"{self.profile} ({self.profile_raw})" \
            if (self.profile == EdidProfile.UNKNOWN) else str(self.profile)
        return f"set edid profile: {target} input 0 -> {profile}"
