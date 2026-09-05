######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Writing a V2IP sink's scaling block, and what the cache holds afterwards.

The scaling block is the only field one of these writes carries, and what makes
that true is the length and the bytes beside it: the 120-byte form appends a sink
block a receiver copies with no validity test, and the frame is a broadcast, so
every device on the network would run that copy.

The cached value is asserted separately from the bytes, because the two differ on
purpose. Clearing a mode is sent as the valid bit over a zero mode and reported
back as the valid bit clear, so a cache predicted from the frame alone would hold
a state no device broadcasts.
'''

import asyncio, os, struct, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import DeviceFeature, MxrDeviceUid, VideoColourSpace
from mx_remote.Interface import V2IPOutputMode
from mx_remote.proto.Constants import (MXR_SCALING_FLAG_AUTO_SCALING, MXR_SCALING_FLAG_MODE_VALID,
                                       MXR_SCALING_FLAG_OPTIONS_VALID)
from mx_remote.proto.Factory import create_mxr_frame

ADDR = ('192.0.2.9', 8812)
mx = mx_remote.Remote(open_connection=False)
# A builder returns None without our own uid, which start_async() would load
# from disk. Ours must differ from every peer below: process_frame() drops any
# frame carrying it.
mx._uid = bytes(range(0x20, 0x30))

def uid(n):
    return bytes([n]) * 16

def name(s, sz=16):
    b = s.encode('ascii')[:sz]
    return b + bytes(sz - len(b))

def rx(sender, opcode, payload=b'', protocol=0x28):
    # create_mxr_frame() stamps protocol 1, which several receivers refuse; the
    # stamp is the third header byte.
    frame = bytearray(create_mxr_frame(sender, opcode, payload))
    frame[2] = protocol
    mx.process_frame(0.0, bytes(frame), ADDR)

def hello(sender, features, model='ONEIP'):
    rx(sender, 0x00, struct.pack('<H', 0x28) + name(model) + name('P8SN12345678')
                   + name('5.0.0') + struct.pack('<I', int(features)))
    return mx.get_by_uid(MxrDeviceUid(sender))

SINK = int(DeviceFeature.V2IP_SINK) | int(DeviceFeature.VIDEO_ROUTING)

# ---------------------------------------------------------------------- writing

sent = []
def wire(ok):
    '''Stand in for the socket: full write when ok, nothing written when not.'''
    def tx(data):
        sent.append(data)
        return len(data) if ok else 0
    mx.transmit = tx

def call(coro):
    return asyncio.new_event_loop().run_until_complete(coro)

def last_payload():
    return sent[-1][24:]

sink = hello(uid(0x10), SINK)
source = hello(uid(0x11), int(DeviceFeature.V2IP_SOURCE), model='TX')

# A device that is not a sink has no scaling block to move.
wire(True)
n = len(sent)
assert call(source.set_v2ip_auto_scaling(True)) is False, 'a source accepted a scaling write'
assert len(sent) == n, 'a refused command still transmitted'
print('not a sink  : refused, nothing sent')

# Automatic scaling on. The bytes beside the scaling block are the assertion:
# a source address that is multicast would repoint the encoder, a zero rate
# would ask for a rate of zero, and a stamped tiling uid would move the window.
assert call(sink.set_v2ip_auto_scaling(True)) is True
p = last_payload()
assert len(p) == 88, f'{len(p)} bytes: the 120-byte form zeroes every peer\'s sink block'
assert p[0:16] == uid(0x10), 'the write does not name its subject'
assert p[16:40] == bytes(24), 'a source address here repoints the encoder'
assert p[40] == 0xFF, 'a rate inside the valid range asks for that rate'
assert p[64:80] == bytes(16), 'a stamped tiling uid moves the sink\'s wall window'
mode, refresh, flags = struct.unpack('<HHB', p[56:61])
assert flags == (MXR_SCALING_FLAG_OPTIONS_VALID | MXR_SCALING_FLAG_AUTO_SCALING), hex(flags)
assert sink.v2ip_details.scaling.auto_scaling is True, sink.v2ip_details.scaling
assert sink.v2ip_details.scaling.configured_mode is None, 'a write carried a mode it did not set'
print('auto on     :', sink.v2ip_details.scaling)

# Setting a mode leaves automatic scaling where it was, and vice versa.
bad = V2IPOutputMode(svd=16, depth=16, colour=VideoColourSpace.RGB, refresh=60)
assert bad.validate() is not None, '16bpp is not a depth the output stage takes'
n = len(sent)
assert call(sink.set_v2ip_output_mode(bad)) is False, 'a mode no sink takes was sent'
assert len(sent) == n, 'a refused mode still transmitted'

good = V2IPOutputMode(svd=16, depth=12, colour=VideoColourSpace.YUV422, refresh=60)
assert good.validate() is None, good.validate()
assert call(sink.set_v2ip_output_mode(good)) is True
p = last_payload()
mode, refresh, flags = struct.unpack('<HHB', p[56:61])
assert (mode, refresh) == (0x6210, 60), (hex(mode), refresh)
assert flags == MXR_SCALING_FLAG_MODE_VALID, hex(flags)
cached = sink.v2ip_details.scaling
assert cached.auto_scaling is True, 'setting a mode moved automatic scaling'
assert cached.configured_mode is not None
signal, hz = cached.configured_mode
assert (signal.svd, signal.bpp, int(signal.color), hz) == (16, 12, 2, 60), cached
print('mode set    :', cached.configured_mode[0], '|', hz, 'Hz')

# Turning automatic scaling off keeps the mode, which is the other reason to scale.
assert call(sink.set_v2ip_auto_scaling(False)) is True
p = last_payload()
_, _, flags = struct.unpack('<HHB', p[56:61])
assert flags == MXR_SCALING_FLAG_OPTIONS_VALID, hex(flags)
cached = sink.v2ip_details.scaling
assert cached.auto_scaling is False, cached
assert cached.configured_mode is not None, 'turning automatic scaling off dropped the mode'
print('auto off    :', cached)

# Clearing is spelled differently on the wire and in the cache: the valid bit
# over a zero mode goes out, and the valid bit clear is what a device reports.
assert call(sink.clear_v2ip_output_mode()) is True
p = last_payload()
mode, refresh, flags = struct.unpack('<HHB', p[56:61])
assert (mode, refresh) == (0, 0), (mode, refresh)
assert flags == MXR_SCALING_FLAG_MODE_VALID, hex(flags)
cached = sink.v2ip_details.scaling
assert cached.configured_mode is None, 'the cache holds a state no device broadcasts'
assert cached.auto_scaling is False, 'clearing a mode moved automatic scaling'
print('mode clear  : sent', hex(flags), 'cached', hex(cached.flags))

# A write the socket dropped must report failure and leave the cache alone.
before = (sink.v2ip_details.scaling.mode, sink.v2ip_details.scaling.refresh,
          sink.v2ip_details.scaling.flags)
wire(False)
assert call(sink.set_v2ip_output_mode(good)) is False, 'a failed send reported success'
after = (sink.v2ip_details.scaling.mode, sink.v2ip_details.scaling.refresh,
         sink.v2ip_details.scaling.flags)
assert after == before, f'{before} -> {after}: a failed send moved the cache'
print('send failed : False, cache unmoved')

# What we build, our own decoder reads back the same way.
wire(True)
assert call(sink.set_v2ip_output_mode(good)) is True
rx(uid(0x10), 0x3C, last_payload())
signal, hz = sink.v2ip_details.scaling.configured_mode
assert (signal.value, hz) == (0x6210, 60), (hex(signal.value), hz)
print('round trip  :', signal, hz, 'Hz')

print('ALL OK')
