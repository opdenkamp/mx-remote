######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''No payload length may take a handler down.

Remote.process_frame logs every frame it decodes before processing it and
re-raises whatever either step throws, so a handler that raises on a length it
does not expect propagates out of the datagram callback. A malformed datagram,
a capture replayed off a file, or a device whose payload grew all reach it.

A handler that does not recognise a payload declines it. Raising is what it
must not do, so this sweeps every opcode against lengths either side of every
form boundary, three byte patterns, and every distinct stamp an opcode can arrive
with, and asserts which opcodes raise - not that none does. The ones that still do are listed below with what
each raises, so fixing one fails here and prompts its removal, and a handler
that starts raising fails here rather than in the field.
'''

import contextlib
import io
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.proto.Factory import create_mxr_frame, process_mxr_frame
from mx_remote.proto.Constants import MXR_OPCODE_VERSIONS, MXR_PROTOCOL_VERSION

UID = bytes(range(1, 17))
ADDR = ('192.0.2.9', 8812)

# Zero and 0xFF are the two patterns a field's own sentinel is spelled with, and
# a value no enum names is what turns a lookup into a raise; the third is
# neither, so a field that only decodes for one of the first two still shows up.
PATTERNS = {
    'zero': lambda n: bytes(n),
    'ff':   lambda n: bytes([0xFF]) * n,
    'seq':  lambda n: bytes((((7 * i) % 251) + 1) for i in range(n)),
}

# Dense over the small lengths, where the form boundaries are, and then the
# sizes the larger payloads are built out of.
LENGTHS = list(range(0, 72)) + [100, 127, 128, 151, 152, 153, 200, 255, 300, 514]

# Opcodes that raise on some length, and what each raises. Every one predates
# this sweep. The first four decline a payload shorter than the fields they read
# by raising out of their constructor, where returning no value would say the
# same thing; the last two are not length faults at all.
KNOWN = {
    0x1F: 'V2IP_SOURCE_SWITCH   - short payload raises "invalid FrameV2IPSourceSwitch size"',
    0x24: 'V2IP_MANUAL_SRC_SW   - short payload raises "invalid FrameV2IPManualSourceSwitch size"',
    0x29: 'NET_LINK_STATUS      - IndexError and struct.error on all but an empty payload',
    0x31: 'BAY_SIGNAL_STATUS    - KeyError on a value no enum names, at any length',
    0x3C: 'V2IP_DEVICE_CFG      - short payload raises "invalid v2ip configuration"',
    0x3D: 'AMP_ZONE_SETTINGS    - AttributeError reading a member off a value that is None',
}

def sweep():
    raised = {}
    for opcode in sorted(MXR_OPCODE_VERSIONS):
        # a fresh registry per opcode: uids read out of these payloads register
        # devices, and a registry carrying every one of them makes each later
        # lookup slower without testing anything the first frame did not
        mx = mx_remote.Remote(open_connection=False)
        mx._uid = bytes(range(100, 116))
        for build in PATTERNS.values():
            for length in LENGTHS:
                for stamp in sorted({1, MXR_OPCODE_VERSIONS[opcode], MXR_PROTOCOL_VERSION}):
                    raw = bytearray(create_mxr_frame(UID, opcode, build(length)))
                    raw[2] = stamp
                    try:
                        # the factory prints a traceback of its own before
                        # re-raising, which says nothing this does not
                        with contextlib.redirect_stdout(io.StringIO()):
                            frame = process_mxr_frame(mx, time.time(), bytes(raw), ADDR)
                        if (frame is None):
                            continue
                        str(frame)
                        frame.process()
                    except Exception as e:
                        raised.setdefault(opcode, f'{type(e).__name__}: {e}')
    return raised

raised = sweep()
unexpected = {op: err for op, err in raised.items() if op not in KNOWN}
assert not unexpected, \
    'a handler raises on a payload length: %s' % {f'0x{o:02X}': e for o, e in unexpected.items()}

fixed = sorted(set(KNOWN) - set(raised))
assert not fixed, \
    'these no longer raise on any length; drop them from KNOWN: %s' % [f'0x{o:02X}' for o in fixed]

stamps = sum(len({1, MXR_OPCODE_VERSIONS[op], MXR_PROTOCOL_VERSION}) for op in MXR_OPCODE_VERSIONS)
print(f'sweep : {len(MXR_OPCODE_VERSIONS)} opcodes x {len(PATTERNS)} patterns '
      f'x {len(LENGTHS)} lengths x {stamps} opcode/stamp pairs')
for opcode in sorted(KNOWN):
    print(f'known : 0x{opcode:02X} {KNOWN[opcode]}')
print(f'clean : {len(MXR_OPCODE_VERSIONS) - len(KNOWN)} opcodes decline every length they cannot read')

print()
print('ALL OK')
