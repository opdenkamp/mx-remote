######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Sending an overlay sync, and answering the units that take it.

A sync announces what it copies and how many settings it has. Each unit fetches
the logo images, then asks the source for the settings it lacks, once a second
until it has them all, and takes none it did not ask for. So the settings go out
only in answer to a request, a few at a time: a unit drops one that arrives while
it is still writing earlier ones, and asks for it again.

While this client holds a sync it also announces itself as the mesh's overlay
sync manager. A unit that wakes from power save, or that is told to pull, then
asks this client for a new sync instead of the controller.
'''

from __future__ import annotations
import asyncio
from collections import deque
from dataclasses import dataclass
import logging
import struct
import time
from ..Interface import (OsdCaption, OsdLogo, OsdSyncContent, OsdSyncEntry, OsdSyncImage, OsdSyncRequest,
                         OsdSyncSlot)
from ..Uid import MxrDeviceUid
from ..proto.Constants import (OSD_SYNC_FONT_MAX, OSD_SYNC_IMAGE_HEIGHT_MAX, OSD_SYNC_IMAGE_MAX,
                               OSD_SYNC_IMAGE_WIDTH_MAX, OSD_SYNC_PERCENT_MAX, OSD_SYNC_RECORDS_MAX,
                               OSD_SYNC_SLOTS, OSD_SYNC_TEXT_MAX, OsdSyncWhat)
from ..proto.FrameV2IPOsdSync import osd_crc32

_LOGGER = logging.getLogger(__name__)

SEQS_KEPT = 64
'''How many syncs of the held content a request may still name. Each unit that
asks for a new sync is sent one of its own; a request naming one that has aged
out is answered with another.'''

SETTINGS_PER_PASS = 4
PASS_GAP = 0.014
'''How many settings go out together, and the gap after them, which a unit
keeps up with.'''

_PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
_PNG_IHDR_AT = 12

def osd_content_refusal(content:OsdSyncContent) -> str|None:
    '''Why units would refuse content, None when they would take it.'''
    copies = content.what & ~OsdSyncWhat.LOGO_SLOTS
    if (int(copies) == 0) and (content.images is None):
        return 'an overlay sync copying something'
    if (len(content.entries) > OSD_SYNC_RECORDS_MAX):
        return f'an overlay sync of at most {OSD_SYNC_RECORDS_MAX} settings'
    for entry in content.entries:
        value = entry.value
        if isinstance(value, OsdCaption) and (len(value.font.encode('utf-8')) > OSD_SYNC_FONT_MAX):
            return f'a caption font of at most {OSD_SYNC_FONT_MAX} bytes'
        if isinstance(value, OsdCaption) and (len(value.text.encode('utf-8')) > OSD_SYNC_TEXT_MAX):
            return f'a caption text of at most {OSD_SYNC_TEXT_MAX} bytes'
        if isinstance(value, OsdLogo) and not (-1 <= value.logo <= 4):
            return 'a logo of -1 to 4'
    if (content.images is not None):
        if (len(content.images) != OSD_SYNC_SLOTS):
            return f'{OSD_SYNC_SLOTS} logo slots'
        for image in content.images:
            if not (0 <= image.percent <= OSD_SYNC_PERCENT_MAX):
                return f'a logo size of 0 to {OSD_SYNC_PERCENT_MAX} percent'
            if image.png and not _fits(image.png):
                return 'a PNG of at most 512 KB and 1920 by 1080 pixels'
    return None

def _fits(png:bytes) -> bool:
    '''Whether png is a PNG a unit takes, by its size and the header's.'''
    if (len(png) > OSD_SYNC_IMAGE_MAX) or not png.startswith(_PNG_SIGNATURE) \
            or (png[_PNG_IHDR_AT:_PNG_IHDR_AT + 4] != b'IHDR') or (len(png) < _PNG_IHDR_AT + 12):
        return False
    width, height = struct.unpack_from('>II', png, _PNG_IHDR_AT + 4)
    return (1 <= width <= OSD_SYNC_IMAGE_WIDTH_MAX) and (1 <= height <= OSD_SYNC_IMAGE_HEIGHT_MAX)

@dataclass
class _Held:
    '''The sync this client holds.'''
    what:OsdSyncWhat
    entries:tuple[OsdSyncEntry, ...]
    slots:tuple[OsdSyncSlot, ...]
    http_port:int
    seqs:deque[int]

@dataclass(frozen=True)
class _Pending:
    '''A setting a unit asked for, not yet sent.'''
    unit:MxrDeviceUid
    seq:int
    index:int

class OsdSender:
    '''What this client sends and answers, kept apart from the socket.'''
    def __init__(self) -> None:
        # Numbered from the wall clock, so a restarted client does not reuse a
        # recent number: requests and reports name a sync by its number, and a
        # unit drops a sync repeating the last one's within two seconds.
        self._next_seq = max(int(time.time() * 1000) & 0xFFFF, 1)
        self._held:_Held|None = None
        self._issued:deque[int] = deque(maxlen=SEQS_KEPT)
        '''The syncs this client sent, of whatever it held, oldest first.'''
        self._queue:deque[_Pending] = deque()

    @property
    def holds(self) -> bool:
        '''Whether a sync is held, which is when this client is the manager.'''
        return (self._held is not None)

    @property
    def queued(self) -> int:
        return len(self._queue)

    def hold(self, content:OsdSyncContent, http_port:int) -> None:
        '''Hold content as the sync this client answers for.'''
        what = content.what & ~OsdSyncWhat.LOGO_SLOTS
        slots:tuple[OsdSyncSlot, ...] = tuple(OsdSyncSlot() for _ in range(OSD_SYNC_SLOTS))
        if (content.images is not None):
            what |= OsdSyncWhat.LOGO_SLOTS
            slots = tuple(OsdSyncSlot(bytes=len(i.png), crc32=osd_crc32(i.png), percent=i.percent)
                          for i in content.images)
        self._held = _Held(what=what, entries=tuple(content.entries), slots=slots, http_port=http_port,
                           seqs=deque(maxlen=SEQS_KEPT))

    def drop(self) -> bool:
        '''Stop holding the sync, True when one was held.'''
        held = self._held is not None
        self._held = None
        self._queue.clear()
        return held

    def new_sync(self, what:OsdSyncWhat|None=None) -> tuple[int, OsdSyncWhat, int, int, tuple[OsdSyncSlot, ...]]|None:
        '''Number a new sync of the held content, copying what, which is some
        of what the content copies, or all of it. Zero means "no sync", so the
        count skips it. None while nothing is held.'''
        if ((held := self._held) is None):
            return None
        seq = self._next_seq
        self._next_seq = max((seq + 1) & 0xFFFF, 1)
        self._issued.append(seq)
        held.seqs.append(seq)
        return (seq, held.what if (what is None) else what, held.http_port, len(held.entries), held.slots)

    def answer(self, request:OsdSyncRequest) -> OsdSyncWhat|None:
        '''Take a request: queue the settings it lacks of a sync of the held
        content, in place of what was still queued for its unit, and return
        None; or return what a new sync for its unit should copy, when it asks
        for one or names another sync of this client's. None as well for a
        request this client leaves alone.'''
        if ((held := self._held) is None):
            return None
        current = (request.seq != 0) and (request.seq in held.seqs)
        # A request naming no source, as an older overlay module sends, is this
        # client's to answer only for a sync it sent; any other is the
        # controller's.
        ours = current or (request.seq in self._issued)
        if (request.seq != 0) and request.source.empty and not ours:
            return None
        if current:
            self._queue = deque(p for p in self._queue if (p.unit != request.target))
            for index in range(len(held.entries)):
                if request.is_missing(index):
                    self._queue.append(_Pending(unit=request.target, seq=request.seq, index=index))
            return None
        # A new sync copies what the request asks for, of what is held; a
        # request asking for none of it gets none.
        what = request.what & held.what
        return what if (int(what) != 0) else None

    def next_pass(self) -> list[tuple[MxrDeviceUid, int, int, int, OsdSyncEntry]]:
        '''The next few settings to send, as (unit, seq, index, records, entry).

        The units take turns: a unit's other settings go behind everyone else's
        each time one of its own is taken, so one asking for many does not hold
        the rest past the time a unit allows a sync.'''
        out:list[tuple[MxrDeviceUid, int, int, int, OsdSyncEntry]] = []
        while (len(out) < SETTINGS_PER_PASS) and self._queue and ((held := self._held) is not None):
            p = self._queue.popleft()
            theirs = [q for q in self._queue if (q.unit == p.unit)]
            self._queue = deque([q for q in self._queue if (q.unit != p.unit)] + theirs)
            # A request for a sync since replaced, or aged out, is answered no
            # further: the unit asks again and gets a new sync.
            if (p.index >= len(held.entries)) or (p.seq not in held.seqs):
                continue
            out.append((p.unit, p.seq, p.index, len(held.entries), held.entries[p.index]))
        return out

class LogoServer:
    '''The HTTP server units fetch an overlay sync's logo images from.

    A unit asks for GET /osd-sync/slotN.png, N being 1 to 4, one image at a
    time. It takes only a 200 whose body is exactly the size the sync gave,
    sent plainly with a Content-Length: it reads neither chunked nor compressed
    bodies. A 404 fails the unit's sync, so an empty or unknown slot answers
    that.

    It listens on every interface rather than the one the client talks on: a
    unit fetches from the address the sync came from, which is whichever
    address the host sent it with.'''
    def __init__(self) -> None:
        self._server:asyncio.base_events.Server|None = None
        self.images:tuple[bytes, ...] = tuple(b'' for _ in range(OSD_SYNC_SLOTS))

    @property
    def port(self) -> int:
        if (self._server is None) or not self._server.sockets:
            return 0
        return int(self._server.sockets[0].getsockname()[1])

    async def start(self, port:int) -> None:
        if (self._server is None):
            self._server = await asyncio.start_server(self._serve, host='0.0.0.0', port=port)

    async def stop(self) -> None:
        if (self._server is not None):
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _serve(self, reader:asyncio.StreamReader, writer:asyncio.StreamWriter) -> None:
        try:
            head = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), timeout=2)
            png = self.image_for(head)
            if png:
                writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nContent-Length: %d\r\n'
                             b'ETag: "%08x"\r\nConnection: close\r\n\r\n' % (len(png), osd_crc32(png)) + png)
            else:
                writer.write(b'HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            await asyncio.wait_for(writer.drain(), timeout=10)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError):
            pass
        finally:
            writer.close()

    def image_for(self, head:bytes) -> bytes:
        '''The image a request head asks for, empty for none.'''
        parts = head.split(b'\r\n', 1)[0].split(b' ')
        if (len(parts) < 2) or (parts[0] != b'GET'):
            return b''
        path = parts[1].split(b'?', 1)[0]
        for n in range(1, OSD_SYNC_SLOTS + 1):
            if (path == b'/osd-sync/slot%d.png' % n):
                return self.images[n - 1]
        return b''
