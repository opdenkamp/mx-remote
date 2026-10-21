######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''A device uid: its text form, and the uid and text it equals.

Callers key dicts by uid and look them up by uid or by its text, so a uid and
its text must hash alike.
'''

import os, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import MxrDeviceUid

RAW = bytes(range(0x10, 0x20))
TEXT = '13121110.17161514.1b1a1918.1f1e1d1c'

# ------------------------------------------------------------------- text
u = MxrDeviceUid(RAW)
assert u.value == TEXT and str(u) == TEXT and repr(u) == TEXT, u.value
assert MxrDeviceUid(TEXT).byte_value == RAW
assert MxrDeviceUid(None).value == MxrDeviceUid(b'').value == '00000000.00000000.00000000.00000000'
print('text        :', u)

# ------------------------------------------------------------------- equality
# Only the first 16 bytes are the uid: a uid read off a longer slice equals it.
for what, other in (('the same bytes', MxrDeviceUid(bytes(RAW))), ('a copy', MxrDeviceUid(u)),
                    ('its text', MxrDeviceUid(TEXT)), ('a longer slice', MxrDeviceUid(RAW + b'\xA5'))):
    assert (u == other) and (other == u) and (hash(u) == hash(other)), what
assert u == TEXT and hash(u) == hash(TEXT), 'the uid and its text'
for what, other in (('the last byte', RAW[:15] + b'\0'), ('the first byte', b'\0' + RAW[1:])):
    assert u != MxrDeviceUid(other), f'a uid differing in {what}'
assert u != TEXT.upper() and u != RAW and u != None, 'only a uid or its text'
print('equality    : the first 16 bytes, by uid or by text')

# ------------------------------------------------------------------- lookups
d = {u: 'found'}
assert d.get(MxrDeviceUid(RAW + b'\xA5')) == d.get(TEXT) == 'found'
mx = mx_remote.Remote(open_connection=False)
mx.remotes[u] = 'device' # pyright: ignore[reportArgumentType]
for key in (u, MxrDeviceUid(RAW), TEXT, RAW):
    assert mx.get_by_uid(key) == 'device', key
assert mx.get_by_uid(MxrDeviceUid(bytes(16))) is None and mx.get_by_uid(None) is None
print('lookups     : a registry finds a device by uid, text or bytes')

print('ALL OK')
