######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for a unit's health and IP configuration.'''

from functools import cached_property
import ipaddress
import struct
from ..compat import override
from .Constants import UNIT_MAX_TEMPERATURES, UnitFlag
from .FrameBase import FrameBase
from ..Interface import UnitNetConfig, UnitStatus

# mxr_unit_status, 104 bytes, naturally aligned so without padding:
#     0       u32 flags
#     4..24   u32 uptime, boot count, reboot count, encoder and decoder health
#    24..44   IP configuration: address, netmask, gateway, two DNS servers,
#             network byte order
#    44       u16 fan RPM
#    46       u8 fan duty, u8 system status, u8 net revert seconds,
#             u8 temperature count
#    50..56   up to six i8 temperatures
#    56..104  status message
#
# The report grows at the back, so a frame is read as far as it goes and the
# fields it does not reach read as zero.
UNIT_STATUS_SIZE = 104
_MESSAGE_AT = 50 + UNIT_MAX_TEMPERATURES

def parse_net_config(data:bytes) -> UnitNetConfig:
    '''Five addresses in network byte order, 20 bytes.'''
    return UnitNetConfig(*(str(ipaddress.IPv4Address(data[i:i + 4])) for i in range(0, 20, 4)))

class FrameUnitStatus(FrameBase):
    '''A unit's report of its own health and IP configuration.'''
    @cached_property
    def status(self) -> UnitStatus:
        '''The report, with what the frame does not reach read as zero.'''
        p = (self.payload or b'').ljust(UNIT_STATUS_SIZE, b'\0')
        flags, uptime, boots, reboots, encoder, decoder = struct.unpack_from('<6I', p, 0)
        flags = UnitFlag(flags)
        fan_rpm, fan_duty, status, revert, count = struct.unpack_from('<HBBBB', p, 44)
        count = min(count, UNIT_MAX_TEMPERATURES)
        message = p[_MESSAGE_AT:UNIT_STATUS_SIZE].split(b'\0', 1)[0].decode('ascii', errors='replace')
        return UnitStatus(flags=flags, uptime=uptime,
                          boot_count=(boots if (UnitFlag.BOOT_COUNT in flags) else None),
                          reboot_count=reboots, encoder_health=encoder, decoder_health=decoder,
                          network=parse_net_config(p[24:44]),
                          fan_rpm=(fan_rpm if (UnitFlag.FAN_SPEED in flags) else None),
                          fan_duty=fan_duty, status=status, net_revert_s=revert,
                          temperatures=struct.unpack_from(f'<{count}b', p, 50),
                          status_message=message)

    @override
    def process(self) -> None:
        '''Record the report against the unit that sent it.'''
        if ((dev := self.remote_device) is not None):
            dev.on_mxr_update(self.status)

    def __str__(self) -> str:
        return f"unit status {self.status}"
