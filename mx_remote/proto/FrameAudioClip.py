######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame reporting audio clipping on an amplifier bay.'''

from functools import cached_property
from .FrameBase import FrameBase
from ..Interface import BayBase

# mxr_audio_clip_data wire layout:
#   0..1   u8 local_bay   port id of the clipping bay on the sending device
#   1..2   u8 clip        clipping value

class FrameAudioClip(FrameBase):
    '''Audio clipping detected on a bay of the sending device.

    A notification only, emitted by ProAmp8 amplifiers. Nothing in the firmware
    receives it, so a client decoding it is its only consumer. The bay is a port
    on the sending device, not a target.
    '''
    @cached_property
    def bay(self) -> BayBase|None:
        '''Bay on the sending device that is clipping.'''
        return self.payload_bay(device=self.remote_device, idx=0)

    @cached_property
    def clip(self) -> int|None:
        '''Clipping value.'''
        return self.payload_u8(1)

    def process(self) -> None:
        '''No-op: a transient notification with no bay state behind it.

        There is no cached clipping level on a bay to update - the report says
        clipping happened, not that the bay is now in a clipping state - so this
        is decoded for visibility rather than folded into the device cache.
        '''
        pass

    def __str__(self) -> str:
        return f"{self.bay} audio clipping: {self.clip}"
