##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

import csv
from ..const import *

class Svd:
    def __init__(self, data:list[int]) -> None:
        self._data = data

    @property
    def id(self) -> int:
        return int(self._data[0])

    @property
    def picture_aspect(self) -> int:
        return int(self._data[1])

    @property
    def pixel_aspect(self) -> int:
        return int(self._data[2])

    @property
    def horizontal_active(self) -> int:
        return int(self._data[3])

    @property
    def horizontal_total(self) -> int:
        return int(self._data[4])

    @property
    def vertical_active(self) -> int:
        return int(self._data[5])

    @property
    def vertical_total(self) -> int:
        return int(self._data[6])

    @property
    def refresh(self) -> int:
        return int(self._data[7])

    @property
    def interlaced(self) -> bool:
        return (int(self._data[8]) == 1)

    @property
    def multiplier(self) -> int:
        return int(self._data[9])

    def __str__(self) -> str:
        return f"{self.horizontal_active}x{self.vertical_active}@{self.refresh}Hz"

    def __repr__(self) -> str:
        return str(self)

class SvdMap:
    svd:dict[int, Svd] = {}

    def __init__(self) -> None:
        with open(f'{BASE_PATH}/proto/svd.csv', newline='') as csvfile:
            reader = csv.reader(csvfile, delimiter=';', quotechar='|')
            for row in reader:
                svd = Svd(row)
                self.svd[svd.id] = svd