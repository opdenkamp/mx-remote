######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for transmitting remote control keys to a target bay.'''

from functools import cached_property
from .FrameBase import FrameBase
from .Constants import RCKey
from ..Interface import BayBase, DeviceBase, DeviceRegistry
from ..Uid import MxrDeviceUid

# mxr_tx_key_data wire layout, identical to mxr_tx_action_data (0x0E) with a key
# code where the action sits:
#   0..16    mxr_uid target
#   16..18   u16 local_bay      mbay_port_id on the target device
#   18..20   u16 key            rc_key_t
#
# Note the asymmetry with the RC_KEY notification (0x0B): the transmit form
# carries a target uid, the notification does not, and its bay is a port on the
# sending device rather than on a target.

class FrameTXRCKey(FrameBase):
    '''A request for a specific bay on a target device to emit a key.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:BayBase, key:RCKey) -> FrameBase|None:
        '''Build an RC key frame for transmission to the target bay.'''
        payload = target.device.remote_id.byte_value
        payload += bytes([(target.port & 0xFF), ((target.port >> 8) & 0xFF),
                          (int(key.value) & 0xFF), ((int(key.value) >> 8) & 0xFF)])
        return FrameBase.construct_base(mxr=mxr, opcode=0x0C, payload=payload)

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        '''UID of the device the key is addressed to.'''
        return self.payload_uuid(0)

    @cached_property
    def target_device(self) -> DeviceBase|None:
        '''Device the key is addressed to, if it is known to us.'''
        if ((uid := self.target_uid) is None):
            return None
        return self.mxr.get_by_uid(uid)

    @cached_property
    def bay(self) -> BayBase|None:
        '''Bay on the target device that should emit the key.'''
        return self.payload_bay(device=self.target_device, idx=16, u16=True)

    @cached_property
    def key(self) -> RCKey|None:
        '''Key the target bay is asked to emit.'''
        if ((pl := self.payload_u16(18)) is None):
            return None
        try:
            return RCKey(pl)
        except ValueError:
            return None

    def process(self) -> None:
        '''No-op: a request to a target, not a report of something that happened.

        The target announces the key it actually emitted as RC_KEY (0x0B).
        '''
        pass

    def __str__(self) -> str:
        target = self.bay if (self.bay is not None) else self.target_uid
        return f"{target} rc key request: {repr(self.key)}"
