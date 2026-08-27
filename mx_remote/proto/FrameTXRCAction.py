######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for transmitting remote control actions to a target bay.'''

from functools import cached_property
import warnings
from .FrameBase import FrameBase
from .Constants import RCAction
from ..Interface import BayBase, DeviceBase, DeviceRegistry
from ..Uid import MxrDeviceUid

# mxr_tx_action_data wire layout, identical to mxr_tx_key_data (0x0C) with an
# action code where the key sits:
#   0..16    mxr_uid target
#   16..18   u16 local_bay      mbay_port_id on the target device
#   18..20   u16 action         rc_perform_action_t
#
# Note the asymmetry with the RC_ACTION notification (0x0D): the transmit form
# carries a target uid, the notification does not, and its bay is a port on the
# sending device rather than on a target.

class FrameTXRCAction(FrameBase):
    '''A request for a specific bay on a target device to perform an action.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:BayBase, action:RCAction) -> FrameBase|None:
        '''Build an RC action frame for transmission to the target bay.'''
        payload = target.device.remote_id.byte_value
        payload += bytes([(target.port & 0xFF), ((target.port >> 8) & 0xFF), (int(action.value) & 0xFF), ((int(action.value) >> 8) & 0xFF)])
        return FrameBase.construct_base(mxr=mxr, opcode=0x0E, payload=payload)

    @cached_property
    def target_device(self) -> DeviceBase|None:
        '''Target device for the RC action.'''
        return self.mxr.get_by_uid(self.target_uid)

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        '''UID of the target device.'''
        return self.payload_uuid(0)

    @cached_property
    def bay(self) -> BayBase|None:
        '''Bay on the target device that should perform the action.'''
        return self.payload_bay(device=self.target_device, idx=16, u16=True)

    @cached_property
    def action(self) -> RCAction|None:
        '''Action the target bay is asked to perform.'''
        # u16 at 18, where construct() writes it - not a u8 at 20, which is past
        # the end of the 20-byte payload and always decoded as None
        if ((pl := self.payload_u16(18)) is None):
            return None
        try:
            return RCAction(pl)
        except ValueError:
            return None

    def process(self) -> None:
        '''No-op: a request to a target, not a report of something that happened.

        The target announces the action it actually performed as RC_ACTION
        (0x0D); treating the request as the event too would report it twice.
        '''
        pass

    def __str__(self) -> str:
        target = self.bay if (self.bay is not None) else self.target_uid
        return f"{target} rc action request: {self.action}"

def constructFrameTXRCAction(mxr:DeviceRegistry, target:BayBase, action:RCAction) -> FrameBase|None:
    warnings.warn("use FrameTXRCAction.construct() instead", DeprecationWarning)
    return FrameTXRCAction.construct(mxr=mxr, target=target, action=action)
