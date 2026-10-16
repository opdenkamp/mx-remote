######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''What the source on an input is showing (0x51), cleaned as a receiving unit
cleans it, so this library shows what a unit's own API would.'''

import os, struct, sys, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import BayContent, BayContentField as Field, BayFeaturesMask as F, DeviceFeature, MxrDeviceUid
from mx_remote.proto.Factory import create_mxr_frame

ADDR = ('192.0.2.9', 8812)

class Watching(mx_remote.MxrCallbacks):
    def __init__(self):
        self.seen = []
    def on_bay_content_changed(self, bay, content):
        self.seen.append((bay, content))

seen = Watching()
mx = mx_remote.Remote(open_connection=False, callbacks=seen)
mx._uid = bytes(range(0x20, 0x30))

def uid(n):
    return bytes([n]) * 16

def nm(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def rx(sender, opcode, payload=b'', protocol=0x2D):
    frame = bytearray(create_mxr_frame(sender, opcode, payload))
    frame[2] = protocol
    mx.process_frame(time.time(), bytes(frame), ADDR)

def content(port, *pairs):
    return struct.pack('<H', port) + b''.join(k + b'\0' + v + b'\0' for k, v in pairs)

TX = uid(0x10)
rx(TX, 0x00, struct.pack('<H', 0x2F) + nm('ONEIP') + nm('TX0001') + nm('4.8.0')
             + struct.pack('<I', int(DeviceFeature.ONEIP_SOURCE)), protocol=0x01)
rx(TX, 0x02, bytes([0, 0, 0, 0, 0]) + nm('Input 1') + nm('Sky Q') + nm('1080p')
             + struct.pack('<II', 0, int(F.HDMI_IN | F.ONEIP_SOURCE_LOCAL))
             + bytes([12, 0, 12, 0, 0]) + nm('Input 13') + nm('Spare') + nm('1080p')
             + struct.pack('<II', 0, int(F.HDMI_IN)))
bay = mx.get_by_uid(MxrDeviceUid(TX)).get_by_portnum(0)
spare = mx.get_by_uid(MxrDeviceUid(TX)).get_by_portnum(12)

rx(TX, 0x51, content(0, (b'name', b'BBC One'), (b'number', b'101')))
assert bay.content == BayContent([Field('name', 'BBC One'), Field('number', '101')]), bay.content
assert bay.content.get('number') == '101' and bay.content.get('genre') is None
assert seen.seen == [(bay, bay.content)]
rx(TX, 0x51, content(0, (b'name', b'BBC One'), (b'number', b'101')))
assert len(seen.seen) == 1, 'a repeat was reported as a change'
print('decode      :', bay.content)

# Each field is cleaned as a unit cleans it. The key keeps letters, digits, _
# and -, cut to 31 bytes; the value drops control characters, " and \\, then
# every byte not part of a valid UTF-8 character, and is cut to 255 bytes before
# a character that would not fit whole.
long_key = b'k' * 40
long_value = 'é'.encode() * 200
rx(TX, 0x51, content(0, (b'na me!', b'a"b\\c\x01d\x7fe'), (long_key, long_value), (b'bad', b'x\xffy\xc3'),
                     (b'empty', b'\x01'), (b'name', b'dup'), (b'!!', b'no key')))
got = bay.content
assert got[0] == Field('name', 'abcde'), got[0]
assert got[1].key == 'k' * 31 and got[1].value == 'é' * 127, (got[1].key, len(got[1].value.encode()))
assert got[2] == Field('bad', 'xy'), got[2]
assert len(got) == 3, 'an empty, duplicate or keyless field was kept: %s' % got
print('cleaned     : keys, values, invalid UTF-8 and the 255-byte cut, as a unit has them')

# A value no NUL terminates is no field, a report with none withdraws the
# content, and a port no unit running the module has an input on is dropped.
rx(TX, 0x51, content(0, (b'name', b'Kodi')) + b'title\0Unterminated')
assert bay.content == BayContent([Field('name', 'Kodi')]), bay.content
rx(TX, 0x51, struct.pack('<H', 12) + b'name\0Elsewhere\0')
assert bay.content.get('name') == 'Kodi' and spare.content == BayContent(), 'a report for port 12 was taken'
rx(TX, 0x51, struct.pack('<H', 0))
assert bay.content == BayContent(), 'an empty report did not withdraw the content'
print('withdrawn   : an empty report clears it; unterminated values and port 12+ are dropped')

# A mesh bay shows what the input it stands for shows.
RX = uid(0x11)
rx(RX, 0x00, struct.pack('<H', 0x2F) + nm('ONEIP') + nm('RX0001') + nm('4.8.0')
             + struct.pack('<I', int(DeviceFeature.ONEIP_SINK)), protocol=0x01)
rx(RX, 0x44, struct.pack('<HH', (1 << 1) | 1, 1) + bytes(4) + TX, protocol=0x28)
mesh = mx.get_by_uid(MxrDeviceUid(RX)).get_by_portnum(1)
seen.seen.clear()
rx(TX, 0x51, content(0, (b'name', b'Netflix')))
assert mesh.content.get('name') == 'Netflix', mesh.content
assert [b for b, _ in seen.seen] == [bay, mesh], 'the change was not reported for the mesh bay'
print('mesh        : a mesh bay shows its owner\'s content, and hears its changes')

print('ALL OK')
