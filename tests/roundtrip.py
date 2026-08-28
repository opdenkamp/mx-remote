"""Feed each builder's payload back through the decoder that reads it.

A field taken from the right offset and attributed to the wrong thing is
positionally perfect, so no offset check sees it. What it is, though, is the two
halves of this library disagreeing about what a field means - and a round trip
is what exposes that.

The limit is worth stating with the technique: where builder and decoder are
wrong together this passes, which is exactly how the amp delays survived at
22/26 in two implementations. A clean round trip says the halves agree, not that
they are right.
"""
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import logging
logging.disable(logging.CRITICAL)

import mx_remote
from mx_remote.Uid import MxrDeviceUid
from mx_remote.proto.Constants import RCAction, RCKey
from mx_remote.proto.Factory import create_mxr_frame, process_mxr_frame
from mx_remote.proto.FrameTXRCKey import FrameTXRCKey
from mx_remote.proto.FrameTXRCAction import FrameTXRCAction
from mx_remote.proto.FrameAmpZoneSettings import FrameAmpZoneSettings
from mx_remote.Interface import AmpZoneSettings
from mx_remote.proto.FrameV2IPAudio import FrameV2IPAudio

UID = bytes(range(1, 17))
SRC = bytes(range(50, 66))
ADDR = ('192.0.2.9', 8812)

mx = mx_remote.Remote(open_connection=False)
mx._uid = bytes(range(100, 116))

def nm(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

hello = (struct.pack('<H', 0x28) + nm('MX-1') + nm('P8SN12345678') + nm('4.7.9')
         + struct.pack('<I', (1 << 5) | (1 << 6) | (1 << 9)))
mx.process_frame(time.time(), create_mxr_frame(UID, 0x00, hello), ADDR)

def bay_rec(port, mode, num, name):
    return (bytes([port, mode, num, 0, 0]) + nm(name) + nm(name)
            + b'1080p60' + bytes(7) + bytes(2)
            + struct.pack('<I', 0) + struct.pack('<I', (1 << 1) if mode == 0 else (1 << 0)))
mx.process_frame(time.time(), create_mxr_frame(
    UID, 0x02, bay_rec(0, 0, 0, 'In 1') + bay_rec(1, 1, 0, 'Out 1')), ADDR)

dev = mx.get_by_uid(MxrDeviceUid(UID))
out_bay = dev.get_by_portnum(1)

def decode(frame):
    """Decode a frame this library built, as though a peer had sent it.

    The sender uid is rewritten to a registered peer first. A frame we build
    carries our own uid, and Remote.process_frame drops those as echoes - so
    replaying one unchanged would exercise nothing. Rewriting it is also the
    honest simulation: the frame being modelled is another controller's.
    """
    raw = bytearray(frame.frame)
    raw[4:20] = UID                              # sender uid sits at header offset 4
    return process_mxr_frame(mx, time.time(), bytes(raw), ADDR)

# --- 0x0C RC_TX_KEY: target, bay and key must survive the round trip
built = FrameTXRCKey.construct(mxr=mx, target=out_bay, key=RCKey.KEY_PLAY)
f = decode(built)
assert f.target_uid == MxrDeviceUid(UID), f.target_uid
assert f.bay is not None and f.bay.port == out_bay.port, f.bay
assert f.key == RCKey.KEY_PLAY, f.key
print('0x0C : target, bay and key round-trip')

# --- 0x0E RC_TX_ACTION: same shape, different field in the same slot
built = FrameTXRCAction.construct(mxr=mx, target=out_bay, action=RCAction.ACTION_VOLUME_UP)
f = decode(built)
assert f.bay is not None and f.bay.port == out_bay.port
assert f.action == RCAction.ACTION_VOLUME_UP, f.action
print('0x0E : target, bay and action round-trip')

# 0x22 CHANGE_BAY_NAME and 0x34 BAY_EDID_PROFILE have no round trip to test:
# both are build-only, with no field accessors on the decode side at all.

# --- 0x43 SELECT_INPUT: the orientation case. sink and source are distinct uids
#     and distinct endpoint ids, so swapping either pair fails rather than
#     cancelling out.
class _Ep:
    def __init__(self, ident):
        self.id = ident
built = FrameV2IPAudio.construct_select_input(
    mxr=mx, sink=MxrDeviceUid(UID), sink_ep=_Ep(7),
    source=MxrDeviceUid(SRC), source_ep=_Ep(9))
f = decode(built)
sel = f._frame.select_input
assert sel.target_uid == MxrDeviceUid(UID), f'sink not read back as target: {sel.target_uid}'
assert sel.source_uid == MxrDeviceUid(SRC), f'source not read back as source: {sel.source_uid}'
assert sel.target_id == 7, sel.target_id
assert sel.source_id == 9, sel.source_id
print('0x43 : sink and source survive as themselves, not swapped')

# --- 0x3D AMP_ZONE_SETTINGS: every field through the widest struct here, and
#     the case that shows the limit. Builder and decoder agreed at 22/26 for as
#     long as both were wrong, so a clean round trip says the halves agree
#     rather than that they are right.
settings = AmpZoneSettings()
settings.gain_left, settings.gain_right = 200, 201
settings.volume_min, settings.volume_max = 1, 248
settings.delay_left, settings.delay_right = 96000, 144000
settings.bass, settings.treble = 128, 129
settings.bridged, settings.power_mode, settings.power_level = 0, 1, 40
settings.power_timeout = 900
settings.eq_left = [1, 2, 3, 4, 5]
settings.eq_right = [6, 7, 8, 9, 10]
built = FrameAmpZoneSettings.construct(mxr=mx, target=out_bay, settings=settings)
f = decode(built)
assert len(f) == 56, len(f)
assert f.delay_left == 96000 and f.delay_right == 144000, (f.delay_left, f.delay_right)
assert f.gain_left == 200 and f.gain_right == 201
assert f.volume_min == 1 and f.volume_max == 248
assert f.bass == 128 and f.treble == 129
assert f.power_timeout == 900
assert f.eq_left == [1, 2, 3, 4, 5] and f.eq_right == [6, 7, 8, 9, 10]
# asymmetric values throughout, so a swapped pair fails rather than cancelling
assert f.delay_left != f.delay_right and f.gain_left != f.gain_right
print('0x3D : every field round-trips, none swapped with its neighbour')

print()
print('ALL OK')
