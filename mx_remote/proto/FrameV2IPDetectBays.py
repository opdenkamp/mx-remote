######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame asking V2IP devices to redetect their bays.'''

from .FrameBase import FrameBase
from ..Interface import DeviceRegistry

class FrameV2IPDetectBays(FrameBase):
    '''A broadcast request for V2IP devices to redetect their bays.

    Carries no payload. Every V2IP unit registers the opcode, but the handler
    body is empty in current firmware, so receiving one has no effect at all -
    decode it for visibility, not for consequence. It is only ever sent by the
    /v2ip/detect endpoint on a controller.
    '''
    @staticmethod
    def construct(mxr:DeviceRegistry) -> FrameBase|None:
        '''Build a bay detection request for transmission.'''
        return FrameBase.construct_base(mxr=mxr, opcode=0x21)

    def process(self) -> None:
        '''No-op: the firmware handler for this opcode has an empty body.'''
        pass

    def __str__(self) -> str:
        return f"{self.remote_device} requested V2IP bay detection"
