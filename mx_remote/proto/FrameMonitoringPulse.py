######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for SYS_MONITORING_PULSE (opcode 0x2B).

A controller broadcasts this to tell every unit to check its update server for
new firmware now. Payload is empty.
'''

from .FrameBase import FrameBase

class FrameMonitoringPulse(FrameBase):
    '''Monitoring pulse: every unit checks its update server for new firmware.'''

    def __str__(self) -> str:
        return f"monitoring pulse from {self.remote_device}"
