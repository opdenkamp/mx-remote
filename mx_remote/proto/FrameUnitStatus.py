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
from .Constants import UNIT_MAX_TEMPERATURES, UNIT_POWER_SAVE_LEVELS, UnitFlag, UnitPowerSave
from .FrameBase import FrameBase
from ..Interface import DeviceRegistry, UnitNetConfig, UnitStatus

# mxr_unit_status, 108 bytes of fields that ALIGN(8) rounds up to 112:
#     0       u32 flags
#     4..24   u32 uptime, boot count, reboot count, encoder and decoder health
#    24..44   IP configuration: address, netmask, gateway, two DNS servers,
#             network byte order
#    44       u16 fan RPM
#    46       u8 fan duty, u8 system status, u8 net revert seconds,
#             u8 temperature count
#    50..56   up to six i8 temperatures
#    56..104  status message
#   104..108  what the unit offers at each power save level, from REDUCED up
#   108..112  padding
#
# The report grows at the back, so a frame is read as far as it goes and the
# fields it does not reach read as zero.
_MESSAGE_AT = 50 + UNIT_MAX_TEMPERATURES
_POWER_SAVE_AT = _MESSAGE_AT + 48
UNIT_STATUS_SIZE = _POWER_SAVE_AT + UNIT_POWER_SAVE_LEVELS
UNIT_STATUS_SENT = 112
'''Width of the report a unit sends, padding included.'''
UNIT_STATUS_MESSAGE_LEN = 48
'''Bytes of the status message, not NUL-terminated when full.'''

def parse_net_config(data:bytes) -> UnitNetConfig:
    '''Five addresses in network byte order, 20 bytes.'''
    return UnitNetConfig(*(str(ipaddress.IPv4Address(data[i:i + 4])) for i in range(0, 20, 4)))

class FrameUnitStatus(FrameBase):
    '''A unit's report of its own health and IP configuration.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, status:UnitStatus) -> FrameBase|None:
        '''The report a unit sends, to every device: each field at its offset,
        a boot count or fan speed of None as zero, the message NUL-padded to
        its 48 bytes and the padding zero. The caller refuses temperatures and
        a message too long for their fields.'''
        n = status.network
        p = struct.pack('<6I', int(status.flags), status.uptime, status.boot_count or 0, status.reboot_count,
                        status.encoder_health, status.decoder_health)
        p += b''.join(ipaddress.IPv4Address(a).packed for a in (n.ip, n.netmask, n.gateway, n.dns1, n.dns2))
        temperatures = status.temperatures
        p += struct.pack('<HBBBB', status.fan_rpm or 0, status.fan_duty, status.status, status.net_revert_s,
                         len(temperatures))
        p += struct.pack(f'<{len(temperatures)}b', *temperatures).ljust(UNIT_MAX_TEMPERATURES, b'\0')
        p += status.status_message.encode('utf-8').ljust(UNIT_STATUS_MESSAGE_LEN, b'\0')
        p += bytes(int(level) for level in status.power_save[:UNIT_POWER_SAVE_LEVELS])
        return FrameBase.construct_base(mxr=mxr, opcode=0x4F, payload=p.ljust(UNIT_STATUS_SENT, b'\0'))

    @cached_property
    def status(self) -> UnitStatus:
        '''The report, with what the frame does not reach read as zero.'''
        p = (self.payload or b'').ljust(UNIT_STATUS_SIZE, b'\0')
        flags, uptime, boots, reboots, encoder, decoder = struct.unpack_from('<6I', p, 0)
        flags = UnitFlag(flags)
        fan_rpm, fan_duty, status, revert, count = struct.unpack_from('<HBBBB', p, 44)
        count = min(count, UNIT_MAX_TEMPERATURES)
        # Empty rather than zero for a unit that predates the levels: it says
        # nothing about them, not that it supports none.
        power_save = () if (len(self.payload or b'') < UNIT_STATUS_SIZE) else \
            tuple(UnitPowerSave(b) for b in p[_POWER_SAVE_AT:UNIT_STATUS_SIZE])
        message = p[_MESSAGE_AT:_POWER_SAVE_AT].split(b'\0', 1)[0].decode('ascii', errors='replace')
        return UnitStatus(flags=flags, uptime=uptime,
                          boot_count=(boots if (UnitFlag.BOOT_COUNT in flags) else None),
                          reboot_count=reboots, encoder_health=encoder, decoder_health=decoder,
                          network=parse_net_config(p[24:44]),
                          fan_rpm=(fan_rpm if (UnitFlag.FAN_SPEED in flags) else None),
                          fan_duty=fan_duty, status=status, net_revert_s=revert,
                          temperatures=struct.unpack_from(f'<{count}b', p, 50),
                          status_message=message, power_save=power_save)

    @override
    def process(self) -> None:
        '''Record the report against the unit that sent it.'''
        if ((dev := self.remote_device) is not None):
            dev.on_mxr_update(self.status)

    def __str__(self) -> str:
        return f"unit status {self.status}"
