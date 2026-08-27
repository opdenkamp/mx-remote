import os, sys, logging, re, pathlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)
import mx_remote
from mx_remote.proto.FrameBase import FrameBase
from mx_remote.proto.Constants import MXR_OPCODE_VERSIONS, MXR_PROTOCOL_VERSION

mx = mx_remote.Remote(open_connection=False)
mx._uid = bytes(range(1, 17))   # normally loaded from disk on connect

# the header protocol byte lives at offset 2
def stamped(frame):
    return frame.header.data[2]

# 1. the default now follows the opcode, not the build
f = FrameBase.construct_base(mxr=mx, opcode=0x00)          # hello
assert stamped(f) == 0x01, hex(stamped(f))
f = FrameBase.construct_base(mxr=mx, opcode=0x3C)          # v2ip device cfg
assert stamped(f) == 0x11, hex(stamped(f))
f = FrameBase.construct_base(mxr=mx, opcode=0x49)          # videowall
assert stamped(f) == 0x28, hex(stamped(f))
f = FrameBase.construct_base(mxr=mx, opcode=0x7F)          # unknown: fall back
assert stamped(f) == MXR_PROTOCOL_VERSION, hex(stamped(f))
# an explicit value still wins
f = FrameBase.construct_base(mxr=mx, opcode=0x00, protocol=0x20)
assert stamped(f) == 0x20, hex(stamped(f))
print('construct_base : opcode version by default, explicit override honoured')

# 2. no frame the library actually builds may exceed the ProAmp8 / AmpOS cap of 0x22
PROAMP8_CAP = 0x22
root = pathlib.Path(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'mx_remote', 'proto'))
call = re.compile(r'construct_base\((.*?)\)', re.S)
bad, checked = [], 0
for path in sorted(root.glob('Frame*.py')):
    for args in call.findall(path.read_text(encoding='utf-8')):
        m = re.search(r'opcode\s*=\s*(0x[0-9A-Fa-f]+|\d+|_OPCODE)', args)
        if not m:
            continue
        raw = m.group(1)
        if raw == '_OPCODE':
            opcode = 0x24                       # FrameV2IPManualSourceSwitch
        else:
            opcode = int(raw, 0)
        pm = re.search(r'protocol\s*=\s*(0x[0-9A-Fa-f]+|\d+)', args)
        proto = int(pm.group(1), 0) if pm else FrameBase.opcode_protocol(opcode)
        checked += 1
        table = MXR_OPCODE_VERSIONS.get(opcode)
        note = '' if (table is None or proto == table) else f'  (explicit; table says 0x{table:02X})'
        if proto > PROAMP8_CAP:
            bad.append(f'{path.name}: opcode 0x{opcode:02X} stamps 0x{proto:02X}{note}')
        elif note:
            print(f'  over-stamp   : {path.name} opcode 0x{opcode:02X} -> 0x{proto:02X}{note}')
print(f'tx frames      : {checked} construct_base call sites checked')
if bad:
    print('\nOVER THE PROAMP8 CAP:')
    for b in bad:
        print('  ' + b)
    raise SystemExit(1)
print(f'cap            : none exceed 0x{PROAMP8_CAP:02X}')
print('\nALL OK')
