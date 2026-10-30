######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame listing a device's OneIP stream sources, whole or paged.'''

from functools import cached_property
from .V2IPConfig import V2IPConfig
from .FrameBase import FrameBase
from .V2IPConfig import V2IPStreamSourcesImpl
from ..Interface import DeviceRegistry, MxrDeviceUid, OneIPStreamSources, OneIPStreamSourcesList
import socket
import struct

# One source record, and the header a paged list puts in front of its records:
# where in the sender's list this page starts, how many records that list held
# when the page was built, and four reserved bytes.
_RECORD_SIZE = 40
_PAGE_HEADER_SIZE = 8

_RECORDS_PER_PAGE = 36
'''Records one frame carries: as many as fit the largest payload behind the
page header.'''

ONEIP_SOURCE_LIST_MAX = 0xFFFF
'''The longest source list the pages can number.'''

def _record(source:OneIPStreamSources) -> bytes:
    '''A source's uid, then each stream's address in network order and its
    port in a 32-bit field. The audio-return stream has no place in a record.'''
    out = MxrDeviceUid(source.uid).byte_value
    for stream in (source.video, source.audio, source.anc):
        out += socket.inet_aton(stream.ip) + struct.pack('<I', stream.port)
    return out

class FrameV2IPSources(FrameBase):
    '''A device's configured OneIP sources, whole or one page of them.'''
    @staticmethod
    def construct(mxr:DeviceRegistry, sources:list[OneIPStreamSources]) -> list[FrameBase]|None:
        '''The frames carrying a whole source list to every device, in the two
        forms page describes: bare records when the list fits one frame, an
        empty list included, and numbered pages past that. None for a list
        longer than ONEIP_SOURCE_LIST_MAX. The caller has checked that every
        source names its uid.'''
        if (len(sources) > ONEIP_SOURCE_LIST_MAX):
            return None
        records = [_record(source) for source in sources]
        if (len(records) <= _RECORDS_PER_PAGE):
            payloads = [b''.join(records)]
        else:
            payloads = [struct.pack('<HH', first, len(records)) + bytes(4)
                        + b''.join(records[first:first + _RECORDS_PER_PAGE])
                        for first in range(0, len(records), _RECORDS_PER_PAGE)]
        frames:list[FrameBase] = []
        for payload in payloads:
            if ((frame := FrameBase.construct_base(mxr=mxr, opcode=0x26, payload=payload)) is None):
                return None
            frames.append(frame)
        return frames

    @cached_property
    def page(self) -> tuple[int,int]|None:
        '''Where this frame's records begin in the sender's list, and how long
        that list was when the frame was built. None when the payload is neither
        form this opcode carries.

        A list that fits one frame is sent as bare records from the first byte,
        and a unit that knows no source sends it with none. A longer one is
        split into pages, each behind a header. That header is not a whole
        record, so the remainder separates the two forms - and a
        payload that is neither is refused rather than read from byte zero,
        which would shift every record by the header's width and report a full
        set of plausible addresses belonging to no bay.

        The count is the sender's list length at the moment the page was built
        rather than a promise about the set, so it says whether this frame is
        the whole list and nothing more.
        '''
        pl = self.payload or b''
        rest = (len(pl) % _RECORD_SIZE)
        if (rest == 0):
            return (0, int(len(pl) / _RECORD_SIZE))
        if (rest != _PAGE_HEADER_SIZE):
            return None
        first = self.payload_u16(idx=0)
        total = self.payload_u16(idx=2)
        if (first is None) or (total is None):
            return None
        return (first, total)

    @cached_property
    def records_offset(self) -> int:
        '''Where the records start, which is behind the header when there is one.'''
        return 0 if ((self.payload is not None) and (len(self.payload) % _RECORD_SIZE == 0)) \
            else _PAGE_HEADER_SIZE

    @property
    def nb_sources(self) -> int:
        '''Number of source records in this frame. Not the device's source count.'''
        if (self.page is None) or (self.payload is None):
            return 0
        return int((len(self.payload) - self.records_offset) / _RECORD_SIZE)

    @cached_property
    def sources(self) -> OneIPStreamSourcesList:
        '''The OneIP stream sources carried by this frame.

        Entries are positional, since Device.oneip_source() indexes into the
        merged list, so an entry is kept rather than dropped: dropping one would
        re-map every source after it.

        Three states, not two. valid is a usable address. cleared - every stream
        zeroed - reports that the source went away, which is the only way that
        is signalled, so it must not be discarded as unusable. Anything else is
        malformed and should leave a cached address alone.
        '''
        rv = OneIPStreamSourcesList()
        if (self.page is None):
            return rv
        first = self.page[0]
        base = self.records_offset
        srcnum = 0
        while srcnum < self.nb_sources:
            pl = self.payload_idx(start=(base + (srcnum*_RECORD_SIZE)),
                                  end=(base + ((srcnum+1)*_RECORD_SIZE)))
            if (pl is None):
                break
            cfg = V2IPConfig(self, first + srcnum, pl)
            rv.append(V2IPStreamSourcesImpl(video=cfg.video, audio=cfg.audio, anc=cfg.anc, uid=cfg.uid))
            srcnum += 1
        return rv

    def process(self) -> None:
        '''Merge this frame's sources into the local device cache.'''
        if ((page := self.page) is None):
            return
        if ((dev := self.remote_device) is not None):
            dev.merge_oneip_sources(first=page[0], total=page[1], page=self.sources)

    def __str__(self) -> str:
        if (self.page is None):
            return f"{str(self.remote_device)} v2ip sources: {len(self)} bytes, neither form"
        first, total = self.page
        what = f"{len(self.sources)} v2ip sources"
        if (self.records_offset != 0):
            what += f" from {first}, of {total}"
        if len(self.sources) > 0:
            return f"{str(self.remote_device)} {what}: {self.sources[0]}"
        return f"{str(self.remote_device)} {what}"
