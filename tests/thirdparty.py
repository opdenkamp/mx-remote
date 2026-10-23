######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Applications' own messages (0x55), sent and received.

The fixtures are composed from the layout this library defines for the opcode,
so they rule out a slip rather than a shared misreading. Payload bytes are all
distinct from their neighbours, so a payload read from the wrong offset shows.
'''

import asyncio, os, struct, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import DeviceFeature, MxrDeviceUid, ThirdPartyVendor
from mx_remote.proto.Constants import THIRD_PARTY_PAYLOAD_MAX, ThirdPartyVendorFlag
from mx_remote.proto.Factory import create_mxr_frame

ADDR = ('192.0.2.9', 8812)
OURS = bytes(range(0x20, 0x30))

class Listening(mx_remote.MxrCallbacks):
    def __init__(self):
        self.messages = []
    def on_third_party_message(self, dev, message):
        self.messages.append((dev, message))

seen = Listening()
mx = mx_remote.Remote(open_connection=False, callbacks=seen)
mx._uid = OURS
sent = []
mx.transmit = lambda data: (sent.append(bytes(data)), len(data))[1]

def uid(n):
    return bytes([n]) * 16

def nm(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def body(n):
    return bytes((0x80 + i * 7) & 0xFF for i in range(n))

def rx(sender, payload, protocol=0x01):
    '''A message stamped as a client stamps it, at the opcode's row.'''
    frame = bytearray(create_mxr_frame(sender, 0x55, payload))
    frame[2] = protocol
    mx.process_frame(0.0, bytes(frame), ADDR)

def known(n):
    '''Another client, announced.'''
    frame = bytearray(create_mxr_frame(uid(n), 0x00, struct.pack('<H', 0x30) + nm('audio-cast') + nm('P9SN00000000')
                                       + nm('1.0.0') + struct.pack('<I', int(DeviceFeature.MANAGER))))
    mx.process_frame(0.0, bytes(frame), ADDR)
    seen.messages.clear()
    return mx.get_by_uid(MxrDeviceUid(uid(n)))

def call(coro):
    return asyncio.run(coro)

# ------------------------------------------------------------------- sending
# Every device gets it at the lowest stamp, with the flag byte, the three
# identifying bytes and the payload as given. A flag bit without a name goes
# out as it was set.
odk = ThirdPartyVendor(flags=ThirdPartyVendorFlag.NOT_OUI | ThirdPartyVendorFlag(0x40), id=b'ODK')
sent.clear()
assert call(mx.send_third_party(odk, body(41))) is True
frame = sent[-1]
assert frame[20:22] == bytes([0x55, 0x00]), frame[:24].hex()
assert frame[2] == 0x01, f'stamped {frame[2]:#04x}'
assert frame[24:28] == bytes([0x41]) + b'ODK', frame[24:28].hex()
assert frame[28:] == body(41)
print('send        : stamped 0x01, the vendor id then the payload as given')

sent.clear()
assert call(mx.send_third_party(ThirdPartyVendor.oui(bytes([0, 0x1A, 0x2B])), b'')) is True
assert sent[-1][24:] == bytes([0, 0, 0x1A, 0x2B]), sent[-1][24:].hex()

sent.clear()
assert call(mx.send_third_party(odk, bytes(THIRD_PARTY_PAYLOAD_MAX))) is True, 'the largest payload was refused'
assert len(sent[-1]) + 28 == 1500, 'the largest frame does not fill the MTU'

sent.clear()
assert call(mx.send_third_party(odk, bytes(THIRD_PARTY_PAYLOAD_MAX + 1))) is False
assert not sent, 'an oversized message was sent'
print('size        : an empty payload goes, and up to', THIRD_PARTY_PAYLOAD_MAX, 'bytes, which fill the MTU')

# ------------------------------------------------------------------- receiving
# The flag byte comes first and the three identifying bytes follow, and the
# payload after them arrives byte for byte.
dev = known(0x31)
rx(uid(0x31), bytes([0x81]) + b'ODK' + body(37))
assert len(seen.messages) == 1, seen.messages
by, message = seen.messages[0]
assert by is dev, by
assert message.vendor.flags == ThirdPartyVendorFlag(0x81), message.vendor.flags
assert message.vendor.id == b'ODK'
assert message.payload == body(37)
assert message.address == ADDR[0]
assert message.vendor.same_vendor(ThirdPartyVendor.private(b'ODK'))
print('receive     :', message)

# A vendor id alone is a message with nothing after it, and anything shorter
# is not a message.
known(0x32)
rx(uid(0x32), bytes([0x00, 0x00, 0x1A, 0x2B]))
assert len(seen.messages) == 1, seen.messages
assert seen.messages[0][1].vendor == ThirdPartyVendor.oui(bytes([0x00, 0x1A, 0x2B]))
assert seen.messages[0][1].payload == b''
seen.messages.clear()
for n in range(4):
    rx(uid(0x32), body(n))
assert not seen.messages, seen.messages
print('minimum     : the vendor id is the whole minimum')

# A sender that has not announced itself is not heard.
rx(uid(0x34), bytes([1]) + b'ODK' + bytes([7]))
assert not seen.messages, seen.messages

# This client never hears itself. Its own uid is never a known device either,
# so the stranger rule drops the frame too, and only the two together being
# lost turns this red.
rx(OURS, bytes([1]) + b'ODK' + bytes([7]))
assert not seen.messages, seen.messages
print('senders     : a stranger and this client are not heard')

# ------------------------------------------------------------------- vendors
# Whether two ids name the same vendor rests on the not-an-OUI flag and the
# three bytes, not on the other flag bits.
plain = ThirdPartyVendor.private(b'ODK')
assert plain.same_vendor(ThirdPartyVendor(flags=ThirdPartyVendorFlag(0xF1), id=b'ODK'))
assert not plain.same_vendor(ThirdPartyVendor.oui(b'ODK'))
for other in (b'ODL', b'PDK', b'OEK'):
    assert not plain.same_vendor(ThirdPartyVendor.private(other)), other
for wrong in (b'', b'OD', b'ODKX'):
    try:
        ThirdPartyVendor.private(wrong)
    except ValueError:
        continue
    raise AssertionError(f'a {len(wrong)}-byte vendor id was taken')
print('vendors     : the flag and the three bytes name a vendor')

print('ALL OK')
