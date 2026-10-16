######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for bay status updates (signal, features, status flags).'''

from functools import cached_property
from .Constants import BayStatusMask, BayFeaturesMask, MXR_CFG_SIGNAL_STATUS_LEN
from .FrameBase import FrameBase
from .FrameHeader import FrameHeader
from ..Interface import BayBase, SignalStatus
import logging

_LOGGER = logging.getLogger(__name__)

# Width of one mxr_bay_status record: 28 bytes of fields, padded to 8.
BAY_STATUS_RECORD = 32

class FrameBayStatus(FrameBase):
    '''Bay status report including signal type, status flags, and feature mask.

    A frame packs one record per bay the sender reports. The properties read
    the record at offset, so the frame itself is its first record and records
    holds a view of each.'''
    def __init__(self, header:FrameHeader, timestamp:float|None=None, offset:int=0) -> None:
        super().__init__(header=header, timestamp=timestamp)
        self._offset = offset

    @cached_property
    def records(self) -> list['FrameBayStatus']:
        '''One view per whole bay record, this frame first; a unit ignores
        bytes behind the last.'''
        size = len(self.payload) if (self.payload is not None) else 0
        if (size < BAY_STATUS_RECORD):
            return []
        return [self] + [FrameBayStatus(header=self.header, timestamp=self.timestamp, offset=offset)
                         for offset in range(BAY_STATUS_RECORD, size - BAY_STATUS_RECORD + 1, BAY_STATUS_RECORD)]

    @cached_property
    def bay(self) -> BayBase|None:
        '''Bay this status record applies to.'''
        return self.payload_bay(device=self.remote_device, idx=self._offset, u16=True)

    @cached_property
    def signal_type(self) -> str|None:
        '''Signal type description string.'''
        return self.payload_str(self._offset + 2, MXR_CFG_SIGNAL_STATUS_LEN)

    @cached_property
    def status(self) -> BayStatusMask|None:
        '''Bay status flags bitmask.'''
        pl = self.payload_u32(self._offset + 20)
        if (pl is None):
            return None
        return BayStatusMask(pl)

    @cached_property
    def features(self) -> BayFeaturesMask|None:
        '''Bay features bitmask.'''
        pl = self.payload_u32(self._offset + 24)
        if pl is not None:
            return BayFeaturesMask(pl)
        return None

    def process(self) -> None:
        '''Update the local device cache with every record's bay status.'''
        for record in self.records:
            record._process_record()

    def _process_record(self) -> None:
        '''Apply this record's status, features and signal info to its bay.'''
        if self.bay is None:
            _LOGGER.debug("bay not registered yet")
            return

        if (self.features is not None):
            self.bay.on_mxr_update(self.features)

        if (self.status is not None):
            self.bay.on_mxr_update(self.status)
            if BayStatusMask.SIGNAL_DETECTED not in self.status or not self.bay.device.is_oneip:
                self.bay.on_mxr_update(SignalStatus(detected=BayStatusMask.SIGNAL_DETECTED in self.status, description=self.signal_type))

    def __str__(self) -> str:
        return ', '.join(f"bay status {r.bay} signal '{r.signal_type}' status {r.status} features {r.features}"
                         for r in self.records)
