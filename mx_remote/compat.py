######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################

"""
Names that live in different modules across the Python versions this package
supports. Import them from here so the version test is written once.
"""

import sys

if sys.version_info >= (3, 12):
    from typing import override
else:
    # typing.override arrived in 3.12; typing_extensions carries the same
    # decorator further back, and is a dependency only below that version.
    from typing_extensions import override

__all__ = ['override']
