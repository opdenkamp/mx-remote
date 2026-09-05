######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''A V2IP configuration belongs to the device its payload names, not to its sender.

The subject in the first sixteen bytes decides whose record moves. A controller's
write for a transceiver has to reach the transceiver, and a write nothing on the
network would act on has to move nothing here - neither the subject's record nor
the sender's, since filing it against the sender is the failure this guards.

Both directions matter for each case. A gate that refuses everything satisfies
every drop assertion on its own, so the writes that must land are what give the
ones that must not their meaning.
'''

import os, struct, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote import DeviceFeature, MxrDeviceUid
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

def cfg(subject, rate=0xFF, mode=0, refresh=0, flags=0):
    '''An 88-byte v2ip_device_config_update naming subject, carrying no addresses.'''
    out = (subject + bytes(24)                                       # 0..40  uid, source
           + bytes([rate, 0, 0, 0]) + bytes(4)                       # 40..48 options
           + bytes(8)                                                # 48..56 arc
           + struct.pack('<HHB3s', mode, refresh, flags, b'\0\0\0')  # 56..64 scaling
           + bytes(24))                                              # 64..88 tiling
    assert len(out) == 88, len(out)
    return out

# ---------------------------------------------------------------- who it is about

# A device describing itself, which nearly every one of these frames is.
selfrep = uid(0x01)
dev = hello(selfrep, SINK)
rx(selfrep, 0x3C, cfg(selfrep, rate=30))
assert dev.v2ip_details is not None and dev.v2ip_details.tx_rate == 30, dev.v2ip_details
print('self-report :', dev.v2ip_details.tx_rate)

# A management write lands on the device it names, not on the sender.
managed = hello(uid(0x02), SINK)
ctrl = hello(uid(0x03), int(DeviceFeature.MANAGER), model='Ctrl')
rx(uid(0x03), 0x3C, cfg(uid(0x02), rate=40))
assert managed.v2ip_details is not None, 'the write did not reach the device it names'
assert managed.v2ip_details.tx_rate == 40, managed.v2ip_details
assert ctrl.v2ip_details is None, 'the write was filed against the sender'
print('managed     :', managed.v2ip_details.tx_rate, '| sender record:', ctrl.v2ip_details)

# A sender with no standing cannot move a third device's record - and the frame
# is not filed against the sender instead.
plain = hello(uid(0x04), SINK)
peer = hello(uid(0x05), int(DeviceFeature.V2IP_SOURCE), model='TX')
rx(uid(0x05), 0x3C, cfg(uid(0x04), rate=40))
assert plain.v2ip_details is None, 'a peer with no standing moved another device\'s record'
assert peer.v2ip_details is None, 'the write was filed against the sender'
print('ordinary peer: dropped, not misattributed')

# MESH_MASTER is the bit a controller actually sets; MANAGER alone would refuse
# every write one makes, since no device firmware sets MANAGER on itself.
mmanaged = hello(uid(0x06), SINK)
hello(uid(0x07), int(DeviceFeature.MESH_MASTER) | int(DeviceFeature.VIDEO_ROUTING), model='Ctrl')
rx(uid(0x07), 0x3C, cfg(uid(0x06), rate=60))
assert mmanaged.v2ip_details is not None, 'a mesh controller\'s write was refused'
assert mmanaged.v2ip_details.tx_rate == 60, mmanaged.v2ip_details
print('mesh master :', mmanaged.v2ip_details.tx_rate)

# A device sets MESH_MASTER only while it also has bays mapped, so one promoted
# before it has any announces neither bit. What closes that window is the
# controller uid the devices in its mesh report.
promoted = hello(uid(0x08), SINK)
hello(uid(0x09), int(DeviceFeature.VIDEO_ROUTING), model='Ctrl')
rx(uid(0x09), 0x3C, cfg(uid(0x08), rate=60))
assert promoted.v2ip_details is None, 'a sender nothing has vouched for moved another record'
# REPORT_MEMBERSHIP: the sub-opcode at 0, the controller uid at 4.
mesh = bytes([0xFF, 0, 0, 0]) + uid(0x09) + bytes(20)
rx(uid(0x08), 0x3B, mesh)
assert promoted.mesh_master_uid == MxrDeviceUid(uid(0x09)), promoted.mesh_master_uid
rx(uid(0x09), 0x3C, cfg(uid(0x08), rate=60))
assert promoted.v2ip_details is not None, 'the controller the device names was not trusted'
assert promoted.v2ip_details.tx_rate == 60, promoted.v2ip_details
print('named ctrl  : refused before the membership report, taken after')

# An unknown subject is dropped rather than invented: a record built from a
# third party's description is a device nothing has been heard from.
before = set(mx.remotes.keys())
rx(uid(0x03), 0x3C, cfg(uid(0x7E), rate=40))
assert set(mx.remotes.keys()) == before, 'an unknown subject created a device'
assert ctrl.v2ip_details is None, 'an unknown subject was filed against the sender'
print('unknown     : dropped, no device invented')

print('ALL OK')
