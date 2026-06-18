# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
```

There is **no test suite** and no lint config in this repo. Validate protocol changes by
running `mxr` against live hardware or by replaying a capture file with `mxr -i`.

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
   - `V2IP`, `Link`, `P8PDU` — OneIP streaming, virtual bay links, PDU support.

### Receive data flow
`ConnectionAsync` datagram → `Remote.on_datagram_received` → `Remote.process_frame` →
`Factory.process_mxr_frame` (decodes `FrameHeader` + opcode into a typed `Frame*`) →
`frame.process()` mutates `Device`/`Bay` → `MxrCallbacks` fire. Frames whose
`remote_id == self.uid` (our own echoes) are skipped.

### Frame wire format
`[0x50, 0x38, protocol, 0x00]` ("P8" magic + protocol version) + opcode (u16 LE) +
length (u16 LE) + payload. Built by `proto/Factory.py::create_mxr_frame`.

## Working on the protocol

When adding or editing a `Frame*` class, byte layouts **must match the MatrixOS firmware C
structs** — verify against the firmware source rather than inferring from samples. Adding a
new opcode requires both the `Frame*` class and a dispatch entry in
`Factory.py::_mxr_frame_factory`. Note the proto/ and remote/ modules use tab indentation
while `Interface.py` and `const.py` use spaces — match the file you are editing.
