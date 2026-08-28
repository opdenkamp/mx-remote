######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Run every protocol test. Exits non-zero on the first failure.

    python tests/run.py            all suites
    python tests/run.py e2e stats  named suites only

Each suite is a standalone script with no test framework behind it, so it can
also be run on its own. A suite prints what it decoded and ends with ALL OK.
'''

import os
import subprocess
import sys

SUITES = [
    'smoke',        # constants, protocol version, opcode table
    'proto_stamp',  # header protocol version stamped per opcode
    'e2e',          # hello, paged bay config and links, signal status
    'merge',        # V2IP device config field-by-field merge
    'newops',       # opcodes decoded per their firmware struct
    'offsets',      # field offsets against the C layout
    'audio_ir',     # audio source orientation, IR timing offsets
    'rcsettings',   # RC settings, including bitfield packing
    'unknowns',     # unknown enum values must not raise
    'stats',        # V2IP stats block boundaries
    'capture',      # real frames off a live mesh
    'sources',      # stream source validity
    'structs',      # alignment padding, u16 bays, packed records
    'roundtrip',    # our builders replayed through our decoders
    'entry',        # the layer the runtime enters at
    'handlers',     # which frame handlers the suites above execute
    'txresult',     # a command reports success only when its frame was sent
    'vdetails',     # Bay.video_details prefers a report over the config snapshot
    'protogate',    # a frame is not sent to a device that cannot receive it
]

def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    wanted = sys.argv[1:] or SUITES
    for name in wanted:
        if name not in SUITES:
            print(f'unknown suite: {name}')
            return 2
        r = subprocess.run([sys.executable, os.path.join(here, name + '.py')],
                           capture_output=True, text=True)
        ok = (r.returncode == 0) and ('ALL OK' in r.stdout)
        print(f'{name:<12} {"ok" if ok else "FAILED"}')
        if not ok:
            print(r.stdout, end='')
            print(r.stderr, end='', file=sys.stderr)
            return 1
    print(f'\n{len(wanted)} suites ok')
    return 0

if __name__ == '__main__':
    sys.exit(main())
