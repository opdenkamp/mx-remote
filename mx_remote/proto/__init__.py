######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################

"""
mx_remote.proto - MX Remote protocol implementation.

Contains frame definitions, constants, and serialization/deserialization
logic for the MX Remote UDP protocol. Frames are created via the Factory
module and processed by the Remote class.
"""

from .Constants import *
