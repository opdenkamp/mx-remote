######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for remote control settings.'''

from .FrameBase import FrameBase

class FrameRCSettings(FrameBase):
    '''Remote control settings notification.'''
    def process(self) -> None:
        '''No-op; RC settings are informational only.'''
        pass

    def __str__(self) -> str:
        return f"{str(self.remote_device)} remote control settings"
