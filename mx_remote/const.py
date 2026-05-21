##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################

"""
Network and version constants for mx_remote.

Default communication modes:
    Multicast: 224.8.8.8:8812 (default)
    Broadcast: <interface broadcast address>:8811
"""
import os

VERSION = '4.7.6'
__version__ = VERSION

MX_BCAST_UDP_PORT = 8811
"""UDP port used in broadcast mode."""

MX_MCAST_UDP_IP = '224.8.8.8'
"""Multicast group IP address for device discovery (default)."""

MX_MCAST_UDP_PORT = 8812
"""UDP port used in multicast mode (default)."""

BASE_PATH = os.path.dirname(__file__)
