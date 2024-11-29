##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

""" constant definitions for mx_remote """
import os

VERSION = '2.0.0'
__version__ = VERSION

MX_BCAST_UDP_IP = '10.8.8.255'
MX_BCAST_UDP_PORT = 8811

MX_MCAST_UDP_IP = '224.8.8.8'
MX_MCAST_UDP_PORT = 8812

BASE_PATH = os.path.dirname(__file__)