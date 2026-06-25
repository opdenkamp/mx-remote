######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################

"""
Network and version constants for mx_remote.

Default communication modes:
    Multicast: 224.8.8.8:8812 (default)
    Broadcast: <interface broadcast address>:8811
"""
import os

VERSION = '4.7.8'
__version__ = VERSION

MX_BCAST_UDP_PORT = 8811
"""UDP port used in broadcast mode."""

MX_MCAST_UDP_IP = '224.8.8.8'
"""Multicast group IP address for device discovery (default)."""

MX_MCAST_UDP_PORT = 8812
"""UDP port used in multicast mode (default)."""

V2IP_UDP_PORT_VIDEO = 50020
"""Default destination UDP port for a V2IP video stream (firmware ``V2IP_UDP_PORT_VIDEO``)."""

V2IP_UDP_PORT_ANC = 50021
"""Default destination UDP port for a V2IP ancillary stream (firmware ``V2IP_UDP_PORT_ANC``)."""

V2IP_UDP_PORT_AUDIO = 50022
"""Default destination UDP port for a V2IP audio stream (firmware ``V2IP_UDP_PORT_AUDIO``)."""

BASE_PATH = os.path.dirname(__file__)
