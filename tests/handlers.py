######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Which frame handlers does the rest of the suite execute?

A frame's process() is where a decoded value reaches the device cache, and a
handler nothing calls is invisible to every other check here: they all measure
tests that run.

This asserts the handlers below still execute and prints the rest, so a handler
that loses its coverage fails rather than going quiet. Add to BASELINE when a
suite starts exercising a new one.
'''

import contextlib
import importlib
import io
import os
import pkgutil
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import logging
logging.disable(logging.CRITICAL)

import mx_remote                                             # noqa: E402
import mx_remote.proto as proto_pkg                          # noqa: E402
from mx_remote.proto.FrameBase import FrameBase              # noqa: E402

BASELINE = {
    'FrameAmpZoneSettings.FrameAmpZoneSettings',
    'FrameAudioClip.FrameAudioClip',
    'FrameAudioSetRoute.FrameAudioSetRoute',
    'FrameBayConfig.FrameBayConfig',
    'FrameBayStatus.FrameBayStatus',
    'FrameFirmwareVersion.FrameFirmwareVersion',
    'FrameHello.FrameHello',
    'FrameLinks.FrameLinks',
    'FrameRCAction.FrameRCAction',
    'FrameRCKey.FrameRCKey',
    'FrameRoutingChange.FrameRoutingChange',
    'FrameSignalStatusNew.FrameSignalStatusNew',
    'FrameTXRCAction.FrameTXRCAction',
    'FrameTXRCKey.FrameTXRCKey',
    'FrameV2IPDetectBays.FrameV2IPDetectBays',
    'FrameV2IPDeviceConfiguration.FrameV2IPDeviceConfiguration',
    'FrameV2IPMultiviewer.FrameV2IPMultiviewer',
    'FrameV2IPSources.FrameV2IPSources',
    'FrameV2IPStats.FrameV2IPStats',
    'FrameV2IPVideoWall.FrameV2IPVideoWall',
}

def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))

    # classes defining their own process(), keyed by the class so a name
    # imported into several modules counts once
    owners: dict[type, str] = {}
    for m in pkgutil.iter_modules(proto_pkg.__path__):
        mod = importlib.import_module(f'mx_remote.proto.{m.name}')
        for name in dir(mod):
            obj = getattr(mod, name)
            if (isinstance(obj, type) and issubclass(obj, FrameBase)
                    and obj is not FrameBase and 'process' in obj.__dict__):
                owners.setdefault(obj, f'{obj.__module__.split(".")[-1]}.{obj.__name__}')

    called: set[type] = set()
    for cls in owners:
        original = cls.__dict__['process']
        def wrap(target: type, fn):
            def process(self, *args, **kwargs):
                called.add(target)
                return fn(self, *args, **kwargs)
            return process
        cls.process = wrap(cls, original)

    skip = {'run', 'handlers'}
    suites = [f[:-3] for f in sorted(os.listdir(here))
              if f.endswith('.py') and f[:-3] not in skip]
    for name in suites:
        path = os.path.join(here, name + '.py')
        globs = {'__name__': '__main__', '__file__': path}
        try:
            with open(path, encoding='utf-8') as f:
                code = compile(f.read(), path, 'exec')
            with contextlib.redirect_stdout(io.StringIO()):
                exec(code, globs)
        except SystemExit:
            pass
        except Exception:
            print(f'{name} did not complete:')
            traceback.print_exc(limit=2)
            return 1

    hit = {owners[c] for c in called}
    print(f'{len(hit)}/{len(owners)} frame handlers executed by {len(suites)} suites')

    lost = sorted(BASELINE - hit)
    if lost:
        print('\nHANDLERS THAT LOST THEIR COVERAGE:')
        for label in lost:
            print(f'  {label}')
        return 1

    gained = sorted(hit - BASELINE)
    if gained:
        print('\nNewly covered - add to BASELINE:')
        for label in gained:
            print(f'  {label}')

    uncovered = sorted(set(owners.values()) - hit)
    print(f'\nnot executed by any suite ({len(uncovered)}):')
    for label in uncovered:
        print(f'  {label}')
    print()
    print('ALL OK')
    return 0

if __name__ == '__main__':
    sys.exit(main())
