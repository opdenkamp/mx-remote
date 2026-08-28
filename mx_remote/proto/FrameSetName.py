######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for changing a bay name on a device.'''

from .FrameBase import FrameBase
from ..Interface import DeviceRegistry, BayBase, DeviceBase, MxrDeviceUid

class FrameSetName(FrameBase):
    '''Change a bay name.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:BayBase, name:str) -> FrameBase|None:
        '''Build a bay name change frame for transmission.'''
        if len(name) > 16:
            name = name[:16]
        name_bytes = name.encode(encoding='ascii').ljust(16, b'\x00')
        payload = target.device.remote_id.byte_value + \
            bytes([(target.port >> 0) & 0xFF, (target.port >> 8) & 0xFF]) + \
            name_bytes
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x22, protocol=0x11, payload=payload)

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
        none and must not be read as a C string. Note the firmware keeps only the
        first 15 characters: mbay_apply_name is handed a copy truncated to
        MXR_DEVICE_NAME_LEN - 1, so a 16-character name arrives whole and is
        stored short.
        '''
        return self.payload_str(18, 16)

    def __str__(self) -> str:
        target = self.bay if (self.bay is not None) else self.target_device
        if (target is None):
            return f"set bay name: port {self.port} -> '{self.name}'"
        return f"set bay name: {target} -> '{self.name}'"
