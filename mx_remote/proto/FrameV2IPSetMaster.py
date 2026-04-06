##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Protocol frame for V2IP master device assignment.'''

from .FrameBase import FrameBase

class FrameV2IPSetMaster(FrameBase):
    '''V2IP master device status notification.'''
    def __str__(self) -> str:
        return f"v2ip master status"
