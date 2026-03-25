##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

"""
mx_remote - Python 3 library for interfacing with MX Remote compatible devices.

Provides device discovery, video/audio routing, volume control, remote control
key passthrough, V2IP (OneIP) streaming, and multiviewer control over a local
network using UDP multicast or broadcast.

Main entry point:
    >>> import mx_remote
    >>> mx = mx_remote.Remote()
    >>> await mx.start_async()

Key classes:
    Remote          Main component that manages network connections and device registry.
    DeviceBase      A discovered device on the network (matrix, OneIP unit, amplifier).
    BayBase         A single input or output port on a device.
    MxrCallbacks    Subclass to receive notifications on state changes.

See README.md for full usage documentation.
"""

from .remote.Remote import Remote
from .Interface import *
from .const import VERSION
from .proto.Constants import MXR_PROTOCOL_VERSION, RCKey, RCAction, RCType
from .main import mxr_console, mxr_main, proto_parser