######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for a command to one unit.'''

from functools import cached_property
import ipaddress
from .Constants import UnitCommandFlag, UnitCommandKind
from .FrameBase import FrameBase
from .FrameUnitStatus import parse_net_config
from ..Interface import DeviceBase, DeviceRegistry, UnitNetConfig, _wire_enum
from ..Uid import MxrDeviceUid

# mxr_unit_command, 20 bytes: the uid of the unit at 0, the command at 16, its
# flags at 17, and two reserved bytes. A NET_CONFIG appends the IP
# configuration as five addresses in network byte order, 40 bytes in all, DHCP
# included.
#
# A unit takes a command only from its mesh controller or a management
# application, which this client announces itself as.
UNIT_COMMAND_SIZE = 20
_NET_CONFIG_SIZE = 20

class FrameUnitCommand(FrameBase):
    '''A command for one unit.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, target:DeviceBase, command:UnitCommandKind,
                  flags:UnitCommandFlag=UnitCommandFlag(0), network:UnitNetConfig|None=None) -> FrameBase|None:
        '''Build a command for target. None for a device below 0x2C, which
        predates the command.'''
        payload = target.remote_id.byte_value + bytes([int(command), int(flags), 0, 0])
        if (network is not None):
            payload += b''.join(ipaddress.IPv4Address(a).packed for a in network.addresses)
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x50, payload=payload)

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        '''The unit the command is for.'''
        return self.payload_uuid(0)

    @cached_property
    def command(self) -> UnitCommandKind|int|None:
        '''What it asks; a raw int for a command this library does not name.'''
        if (self.payload is None) or (len(self.payload) < UNIT_COMMAND_SIZE):
            return None
        return _wire_enum(UnitCommandKind, self.payload[16])

    @cached_property
    def flags(self) -> UnitCommandFlag|None:
        '''The command's flags.'''
        if (self.payload is None) or (len(self.payload) < UNIT_COMMAND_SIZE):
            return None
        return UnitCommandFlag(self.payload[17])

    @cached_property
    def network(self) -> UnitNetConfig|None:
        '''The IP configuration a NET_CONFIG carries, when the frame holds one.'''
        if (self.payload is None) or (len(self.payload) < (UNIT_COMMAND_SIZE + _NET_CONFIG_SIZE)):
            return None
        return parse_net_config(self.payload[UNIT_COMMAND_SIZE:UNIT_COMMAND_SIZE + _NET_CONFIG_SIZE])

    def __str__(self) -> str:
        if (self.command is None):
            return "unit command (short)"
        name = self.command.name.lower() if isinstance(self.command, UnitCommandKind) else self.command
        net = f" [{self.network}]" if (self.network is not None) else ""
        return f"unit command {name} for {self.uid_to_user_string(self.target_uid)} flags {self.flags!r}{net}"
