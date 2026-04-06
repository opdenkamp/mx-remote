##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################
'''Protocol frame for debug commands.'''

from .FrameBase import FrameBase

class FrameDebug(FrameBase):
    '''Debug command frame for diagnostic purposes.'''
    def process(self) -> None:
        '''No-op; debug frames require no cache update.'''
        pass

    def __str__(self) -> str:
        return f"{str(self.remote_device)} debug command"
