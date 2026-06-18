######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for V2IP remote control link status.'''

from .FrameBase import FrameBase

class FrameV2IPLinkStatus(FrameBase):
    '''V2IP remote control link status notification.'''
    def __str__(self) -> str:
        return f"v2ip r/c link status"
