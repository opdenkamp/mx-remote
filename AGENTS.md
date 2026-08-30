# AGENTS.md

Guidance for coding agents working in this repository.

## What this is

`mx_remote` is a Python 3.11+ asyncio library for interfacing with Pulse-Eight MX Remote
compatible devices over a local network (UDP multicast/broadcast): video/audio matrices
(neo), OneIP/V2IP units (tx/rx/transceiver/multiviewer), and amplifiers (ProAmp8). These
all run the shared **MatrixOS** firmware. The library does device discovery, A/V routing,
volume, remote-control key passthrough, V2IP streaming, and multiviewer control.

See `README.md` for the full public-API usage guide (the API surface is large and stable).

## Commands

```bash
pip install .                  # install; runs the custom hatch build hook
python -m build                # build wheel + sdist into dist/
mxr                            # console app: discover devices, log frames live
mxr -l <local_ip>              # bind to a specific interface
mxr -b                         # broadcast mode instead of multicast
mxr -i <capture> [-f <ip>]     # parse a MatrixOS/Wireshark capture file offline
python tests/run.py            # run every protocol test
python tests/run.py e2e stats  # run named suites only
```

There is no lint config in this repo.

`tests/` holds standalone scripts with no test framework behind it — each builds
frames, feeds them through `Remote.process_frame`, and asserts what was decoded.
A suite prints what it decoded and ends with `ALL OK`, so it can be run on its
own as well as through `run.py`.

Two things they pin that code review does not catch:

- **Struct sizes, not just field offsets.** The V2IP stats blocks are 20 and 44
  bytes only because the firmware's `ALIGN(8)` sits where GCC ignores it. Writing
  that declaration the other way round shifts every block after the first, and a
  wrong split still totals 128.
- **Field widths.** Padding in the fixtures is filled with recognisable bytes, so
  a field read at the right offset with the wrong width returns a wrong value. A
  zero-filled fixture cannot catch that: the widened read returns the same
  answer.
- **Which handlers run at all.** `tests/handlers.py` reports how many frame
  `process()` methods the other suites execute and fails if one loses its
  coverage. A handler nothing calls is invisible to every other check here,
  since they all measure tests that run.

`tests/capture.py` holds real frames off a live mesh, with the device uids
replaced. Its expected values come from firmware behaviour rather than from this
decoder, which is the property a synthetic fixture cannot have — assert against
something external, or a fixture only proves the decoder agrees with itself.

Two things a test of a *command* must do, both of which look like coverage
when they are missing:

- **Assert both directions.** A command that returns False for an unrelated
  reason satisfies a failure-only assertion on its own, so the success case is
  what gives the failure case meaning.
- **Pick an input that can reach the send.** Every multiviewer getter reads
  `UNKNOWN` until a config frame arrives, and each setter returns True without
  transmitting when the value already matches — so a table built from the first
  enum member, which is `UNKNOWN`, never transmits at all.

`tests/txresult.py` is the worked example of both.

Validate wire changes against live hardware as well, by running `mxr` or
replaying a capture file with `mxr -i`.

A client's uid is persisted at `~/.mxr-uid`, one file per account, and
`process_frame` drops any frame carrying our own uid. Two clients run from one
account are a single identity to the mesh and each discards everything the other
sends, so a second one needs its own `uid_path`.

### Versioning
Version is single-sourced in `mx_remote/const.py` (`VERSION = '...'`); `pyproject.toml`
reads it via regex, so bump it there only. Release commits follow the convention
`bump to X.Y.Z`.

### Build hook
`hatch_build.py` generates `.pyi` type stubs via `mypy stubgen` at build time and
force-includes them in the wheel (they are gitignored). `mx_remote` ships as typed
(`py.typed`). If stubgen produces nothing the build fails by design.

## Architecture

Three layers, decoupled by abstract base classes:

1. **`mx_remote/proto/`** — the wire protocol. One `Frame*` class per opcode, all
   subclassing `FrameBase` (payload accessors: `payload_u8/u16/u32/str/uuid/bay/device`).
   `Factory.py::_mxr_frame_factory` maps each opcode → its `Frame*` class. Each frame's
   `process()` method mutates registry state and fires callbacks. Frames are built for TX
   via `FrameBase.construct_base` + per-frame `constructFrame*` helpers.

2. **`mx_remote/Interface.py`** — the public API and contracts: abstract base classes
   (`DeviceBase`, `BayBase`, `DeviceRegistry`, `Multiviewer`, `AudioEndpoint`,
   `ConnectionCallbacks`) plus all enums (`DeviceStatus`, `PowerStatus`, `RCType`, …) and
   the `MxrCallbacks` class users subclass. proto/ and remote/ both depend on this; it
   depends on neither. This is the biggest file — most "where is X defined" answers are here.

3. **`mx_remote/remote/`** — concrete implementations:
   - `Remote` (`DeviceRegistry` + `ConnectionCallbacks`) — main entry point; owns the
     connection and the `remotes` registry.
   - `Device` (`DeviceBase`), `Bay` (`BayBase`) — live device/port state.
   - `ConnectionAsync` — `asyncio.DatagramProtocol` UDP transport (multicast/broadcast).
   - `State` — dispatches events to registered `MxrCallbacks`.
   - `V2IP`, `Link` — OneIP streaming and virtual bay links.

### Receive data flow
`ConnectionAsync` datagram → `Remote.on_datagram_received` → `Remote.process_frame` →
`Factory.process_mxr_frame` (decodes `FrameHeader` + opcode into a typed `Frame*`) →
`frame.process()` mutates `Device`/`Bay` → `MxrCallbacks` fire. Frames whose
`remote_id == self.uid` (our own echoes) are skipped.

### Frame wire format
A 24-byte header, then the payload:

```
0   [0x50, 0x38, protocol, 0x00]   "P8" magic + protocol version
4   sender uid                     16 bytes, the device that sent this frame
20  opcode                         u16 LE
22  payload length                 u16 LE
24  payload
```

Built by `proto/Factory.py::create_mxr_frame`, decoded by `proto/FrameHeader.py`.

## Working on the protocol

When adding or editing a `Frame*` class, byte layouts **must match the MatrixOS firmware C
structs** — verify against the firmware source rather than inferring from samples. Adding a
new opcode requires both the `Frame*` class and a dispatch entry in
`Factory.py::_mxr_frame_factory`. Note the proto/ and remote/ modules use tab indentation
while `Interface.py` and `const.py` use spaces — match the file you are editing.
