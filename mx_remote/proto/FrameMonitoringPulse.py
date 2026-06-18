######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for SYS_MONITORING_PULSE (opcode 0x2B).

A controller broadcasts this to ask peers to send their monitoring data to
PMS now. Payload is empty.
'''

from .FrameBase import FrameBase

class FrameMonitoringPulse(FrameBase):
    '''Monitoring pulse: trigger peers to send monitoring data immediately.'''

    def __str__(self) -> str:
        return f"monitoring pulse from {self.remote_device}"
