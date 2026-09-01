######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for changing a bay name on a device.'''

from .Constants import MXR_DEVICE_NAME_LEN
from .FrameBase import FrameBase
from ..Interface import DeviceRegistry, BayBase, DeviceBase, MxrDeviceUid

# mxr_bay_name_data is ALIGN(8): uid at 0, u16 port at 16, 16-byte name at 18,
# and six bytes of tail padding out to 40.
_WIRE_SIZE = 40

class FrameSetName(FrameBase):
    '''Change a bay name.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:BayBase, name:str) -> FrameBase|None:
        '''Build a bay name change frame for transmission.'''
        # 15, not 16: the receiver copies MXR_DEVICE_NAME_LEN - 1 bytes and
        # terminates, so a name filling the field is stored one short. Sending
        # all 16 means the bay ends up named something other than what was
        # asked for, with success reported either way.
        name = name[:MXR_DEVICE_NAME_LEN - 1]
        name_bytes = name.encode(encoding='ascii', errors='replace').ljust(MXR_DEVICE_NAME_LEN, b'\x00')
        payload = target.device.remote_id.byte_value + \
            bytes([(target.port >> 0) & 0xFF, (target.port >> 8) & 0xFF]) + \
            name_bytes
        # 40, not the 34 bytes the fields occupy: mxr_bay_name_data is an
        # 8-aligned struct, so it is 40 bytes wide and the receiver refuses
        # anything shorter than its own sizeof before reading a field. A frame
        # short by the six trailing pad bytes is dropped without a reply, which
        # looks exactly like a rename that was accepted and ignored.
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x22, protocol=0x11, payload=payload, size=_WIRE_SIZE)

    @property
    def target_uid(self) -> MxrDeviceUid|None:
        '''Device whose bay is being renamed.'''
        return self.payload_uuid(0)

    @property
    def target_device(self) -> DeviceBase|None:
        return self.mxr.get_by_uid(self.target_uid)

    @property
    def port(self) -> int|None:
        '''Port id of the bay being renamed (mbay_port_id, a u16).'''
        return self.payload_u16(16)

    @property
    def bay(self) -> BayBase|None:
        return self.payload_bay(device=self.target_device, idx=16, u16=True)

    @property
    def name(self) -> str|None:
        '''The new name, read from its fixed 16-byte field.

        The field carries no terminator of its own, so a name that fills it has
        none and must not be read as a C string: read it at its width. A sender
        that fills all MXR_DEVICE_NAME_LEN bytes is readable here, even though a
        receiver keeps only the first MXR_DEVICE_NAME_LEN - 1 of them.
        '''
        return self.payload_str(18, 16)

    def __str__(self) -> str:
        target = self.bay if (self.bay is not None) else self.target_device
        if (target is None):
            return f"set bay name: port {self.port} -> '{self.name}'"
        return f"set bay name: {target} -> '{self.name}'"
