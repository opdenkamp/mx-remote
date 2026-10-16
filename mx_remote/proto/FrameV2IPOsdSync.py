######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frame for V2IP_OSD_SYNC (opcode 0x53): a management unit having
other units copy its overlay captions, logo choice and place, backgrounds and
logo images.

The source sends a sync naming what it copies and how many settings follow.
Each unit asks the source for the settings it lacks, takes them, and reports
taking, then done or failed, or deferred while in power save. Every frame of a
sync carries the same seq, which the source numbers on its own.
'''

from functools import cached_property
import ipaddress
import struct
import zlib
from ..compat import override
from .Constants import (OSD_SYNC_RECORDS_MAX, OSD_SYNC_SLOTS, DeviceFeature, OsdCaptionAlign,
                        OsdCaptionFormat, OsdSyncSize, OsdSyncState, OsdSyncWhat)
from .FrameBase import FrameBase
from ..Interface import (DeviceRegistry, OsdCaption, OsdLogo, OsdSync, OsdSyncEntry, OsdSyncReport,
                         OsdSyncRequest, OsdSyncSetting, OsdSyncSlot, OsdSyncValue, _wire_enum)
from ..Uid import MxrDeviceUid

# Every frame opens with a 20-byte header: the payload version, the kind, the
# sync's u16 seq and the unit it is for.
#
#   sync     what at 20, u16 HTTP port at 22, the source's IPv4 address at 24,
#            u16 records at 28, then four 12-byte logo slots from 32 (u32
#            bytes, u32 CRC-32, u8 percent): 80 bytes
#   request  what at 20, the 16-byte missing-settings bitmap at 22, then from
#            54 the sync's source, which units on an older overlay module do
#            not send: 38 or 54 bytes
#   setting  u16 index at 20, u16 records at 22, kind at 24, size at 25, u16
#            layers at 26, u16 set at 28, then the body at 30
#   report   state at 20, u16 written at 22, u16 refused at 24, a 64-byte
#            reason at 26: 90 bytes
OSD_SYNC_VERSION = 2
'''The payload version every frame opens with; a unit drops any other.'''
_HEADER_SIZE = 20

OSD_KIND_SYNC = 0
OSD_KIND_REQUEST = 1
OSD_KIND_SETTING = 2
OSD_KIND_REPORT = 3

_SYNC_SIZE = 80
_SLOTS_AT = 32
_SLOT_SIZE = 12
_REQUEST_SIZE = 38
_REQUEST_SOURCE_AT = 38
_SETTING_BODY_AT = 30
_REPORT_SIZE = 90

OSD_SETTING_CAPTION = 0
OSD_SETTING_LOGO = 1
OSD_SETTING_BACKGROUND = 2

# A caption body: a 32-byte font, then u16 size, i16 x, i16 y, i16 wrap, align,
# format, u32 colour and the u16 text length, with the text behind it.
_CAPTION_SIZE = 48
_FONT_LEN = 32
_LOGO_SIZE = 6
_BACKGROUND_SIZE = 4

def osd_crc32(data:bytes) -> int:
    '''The CRC-32 a unit checks a logo image against: the zlib one.'''
    return zlib.crc32(data) & 0xFFFFFFFF

def _header(kind:int, seq:int, target:MxrDeviceUid) -> bytes:
    return bytes([OSD_SYNC_VERSION, kind]) + struct.pack('<H', seq) + target.byte_value

def _cstr(data:bytes) -> str:
    return data.split(b'\0', 1)[0].decode('utf-8', errors='replace')

class FrameV2IPOsdSync(FrameBase):
    '''An overlay sync, a request for one or its settings, a setting, or a
    unit's report.'''
    @staticmethod
    def construct_sync(mxr:DeviceRegistry, target:MxrDeviceUid, seq:int, what:OsdSyncWhat, http_port:int,
                       records:int, slots:tuple[OsdSyncSlot, ...], to:object=None) -> FrameBase|None:
        '''A sync, with every reserved byte zero. The source address is left
        unspecified, which a unit reads as the frame's own source. The slots are
        written only when what copies them.'''
        p = (_header(OSD_KIND_SYNC, seq, target) + bytes([int(what), 0]) + struct.pack('<H', http_port)
             + bytes(4) + struct.pack('<H', records)).ljust(_SLOTS_AT, b'\0')
        if (OsdSyncWhat.LOGO_SLOTS in what):
            p += b''.join(struct.pack('<IIB3x', s.bytes, s.crc32, s.percent) for s in slots)
        return FrameBase.construct_base(mxr=mxr, opcode=0x53, payload=p.ljust(_SYNC_SIZE, b'\0'), target=to)

    @staticmethod
    def construct_setting(mxr:DeviceRegistry, target:MxrDeviceUid, seq:int, index:int, records:int,
                          entry:OsdSyncEntry, to:object=None) -> FrameBase|None:
        '''Setting index of a sync of records, for the unit target. A caption's
        font and text are written as given, so the caller keeps the font under
        32 bytes and the text to what a u16 length counts.'''
        value = entry.value
        kind = OSD_SETTING_CAPTION if isinstance(value, OsdCaption) else \
            OSD_SETTING_LOGO if isinstance(value, OsdLogo) else OSD_SETTING_BACKGROUND
        p = (_header(OSD_KIND_SETTING, seq, target) + struct.pack('<HHBBHH', index, records, kind, int(entry.size),
                                                                  entry.layers, entry.set))
        if isinstance(value, OsdCaption):
            text = value.text.encode('utf-8')
            p += (value.font.encode('utf-8').ljust(_FONT_LEN, b'\0')[:_FONT_LEN]
                  + struct.pack('<HhhhBBIH', value.size, value.x, value.y, value.wrap, int(value.align),
                                int(value.format), value.colour, len(text)) + text)
        elif isinstance(value, OsdLogo):
            p += struct.pack('<bxhh', value.logo, value.x, value.y)
        else:
            p += struct.pack('<I', value)
        return FrameBase.construct_base(mxr=mxr, opcode=0x53, payload=p, target=to)

    @cached_property
    def kind(self) -> int|None:
        '''The kind, None for a frame a unit drops: shorter than its header, or
        of a payload version other than OSD_SYNC_VERSION.'''
        p = self.payload or b''
        if (len(p) < _HEADER_SIZE) or (p[0] != OSD_SYNC_VERSION):
            return None
        return p[1]

    @cached_property
    def seq(self) -> int|None:
        return self.payload_u16(2) if (self.kind is not None) else None

    @cached_property
    def target(self) -> MxrDeviceUid|None:
        return self.payload_uuid(4) if (self.kind is not None) else None

    @cached_property
    def from_management(self) -> bool:
        '''Whether units take a sync, and its settings, from the sender: it
        announces MANAGER, or it is the controller units follow, or, while no
        unit has said whom it follows, it announces itself as one.'''
        if ((sender := self.remote_device) is None) or ((features := sender.features) is None):
            return False
        if (DeviceFeature.MANAGER in features):
            return True
        followed = [d for d in self.mxr.remotes.values()
                    if (d.mesh_master_uid is not None) and not d.mesh_master_uid.empty]
        if any(d.mesh_master_uid == self.remote_id for d in followed):
            return True
        return (not followed) and (DeviceFeature.MESH_MASTER in features)

    @cached_property
    def sync(self) -> OsdSync|None:
        '''The sync, None for any other kind or one no unit would take: from a
        sender that is not management, short of its 80 bytes, or announcing
        more than OSD_SYNC_RECORDS_MAX settings.'''
        p = self.payload or b''
        if (self.kind != OSD_KIND_SYNC) or (len(p) < _SYNC_SIZE) or not self.from_management:
            return None
        what, port, records = OsdSyncWhat(p[20]), struct.unpack_from('<H', p, 22)[0], struct.unpack_from('<H', p, 28)[0]
        if (records > OSD_SYNC_RECORDS_MAX):
            return None
        slots = None
        if (OsdSyncWhat.LOGO_SLOTS in what):
            slots = tuple(OsdSyncSlot(*struct.unpack_from('<IIB', p, _SLOTS_AT + i * _SLOT_SIZE))
                          for i in range(OSD_SYNC_SLOTS))
        return OsdSync(seq=self.seq or 0, target=self.target or MxrDeviceUid(bytes(16)), what=what, http_port=port,
                       source_ip=str(ipaddress.IPv4Address(p[24:28])), records=records, slots=slots)

    @cached_property
    def request(self) -> OsdSyncRequest|None:
        '''The request, None for any other kind or one no unit takes. A unit
        asks about itself; management may also ask for a new sync for another
        unit. A request carries the sync's source from 54 bytes; a 38-byte one,
        as units on an older module send, reads its source as empty.'''
        p = self.payload or b''
        if (self.kind != OSD_KIND_REQUEST) or (len(p) < _REQUEST_SIZE):
            return None
        target, seq = self.target, self.seq or 0
        if (target != self.remote_id) and not ((seq == 0) and self.from_management):
            return None
        source = MxrDeviceUid(p[_REQUEST_SOURCE_AT:_REQUEST_SOURCE_AT + 16].ljust(16, b'\0'))
        return OsdSyncRequest(target=target, seq=seq, what=OsdSyncWhat(p[20]), missing=bytes(p[22:38]),
                              source=source)

    @cached_property
    def setting(self) -> OsdSyncSetting|None:
        '''The setting, None for any other kind or one no unit takes: from a
        sender that is not management, past its count, of a kind no unit knows,
        or short of its body, a caption's counted text included.'''
        p = self.payload or b''
        if (self.kind != OSD_KIND_SETTING) or (len(p) < _SETTING_BODY_AT) or not self.from_management:
            return None
        index, records, kind, size, layers, given = struct.unpack_from('<HHBBHH', p, 20)
        if (index >= records):
            return None
        body = p[_SETTING_BODY_AT:]
        value:OsdSyncValue
        if (kind == OSD_SETTING_CAPTION) and (len(body) >= _CAPTION_SIZE):
            fsize, x, y, wrap, align, fmt, colour, length = struct.unpack_from('<HhhhBBIH', body, _FONT_LEN)
            text = body[_CAPTION_SIZE:]
            if (len(text) < length):
                return None
            value = OsdCaption(font=_cstr(body[:_FONT_LEN]), size=fsize, x=x, y=y, wrap=wrap,
                               align=_wire_enum(OsdCaptionAlign, align), format=_wire_enum(OsdCaptionFormat, fmt),
                               colour=colour, text=text[:length].decode('utf-8', errors='replace'))
        elif (kind == OSD_SETTING_LOGO) and (len(body) >= _LOGO_SIZE):
            logo, x, y = struct.unpack_from('<bxhh', body)
            value = OsdLogo(logo=logo, x=x, y=y)
        elif (kind == OSD_SETTING_BACKGROUND) and (len(body) >= _BACKGROUND_SIZE):
            value = struct.unpack_from('<I', body)[0]
        else:
            return None
        return OsdSyncSetting(seq=self.seq or 0, target=self.target or MxrDeviceUid(bytes(16)), index=index,
                              records=records, size=_wire_enum(OsdSyncSize, size), layers=layers, set=given,
                              value=value)

    @cached_property
    def report(self) -> OsdSyncReport|None:
        '''A unit's report on a sync, None for any other kind, one about another
        unit, or one short of its 90 bytes.'''
        p = self.payload or b''
        if (self.kind != OSD_KIND_REPORT) or (len(p) < _REPORT_SIZE) or (self.target != self.remote_id):
            return None
        written, refused = struct.unpack_from('<HH', p, 22)
        return OsdSyncReport(seq=self.seq or 0, state=_wire_enum(OsdSyncState, p[20]), written=written,
                             refused=refused, reason=_cstr(p[26:_REPORT_SIZE]))

    @override
    def process(self) -> None:
        '''Record a sync and a report against their sender, and hand a request
        and a setting to the callbacks. A request this client may answer goes
        to the registry: one asking for a new sync, or one naming this client
        as the source, or, from an older overlay module, naming none.'''
        if ((dev := self.remote_device) is None):
            return
        if ((sync := self.sync) is not None):
            dev.on_mxr_update(sync)
        elif ((report := self.report) is not None):
            dev.on_mxr_update(report)
        elif ((setting := self.setting) is not None):
            dev.callbacks.on_osd_sync_setting(dev, setting)
        elif ((request := self.request) is not None):
            dev.callbacks.on_osd_sync_requested(dev, request)
            if (request.seq == 0) or request.source.empty or (request.source == self.mxr.uid):
                self.mxr.on_mxr_update(request)

    def __str__(self) -> str:
        if (self.kind is None):
            return "overlay sync <dropped>"
        for item in (self.sync, self.request, self.setting, self.report):
            if (item is not None):
                return f"overlay sync {item}"
        return f"overlay sync kind {self.kind} seq {self.seq} not taken"
