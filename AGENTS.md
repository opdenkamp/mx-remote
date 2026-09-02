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

### Documentation
`docs/` is both the GitHub-readable guide set and the Sphinx source for
[the published site](https://opdenkamp.github.io/mx-remote/), which
`.github/workflows/docs.yml` rebuilds on every push to master. Build it the way
the workflow does:

```sh
pip install . -r docs/requirements.txt
sphinx-build -b html -W --keep-going docs site
```

Autodoc emits reStructuredText, so a directive belongs in an ```` ```{eval-rst} ````
block. Outside one it renders as its own source and the build still reports
success — the workflow greps the output for that.

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
`Factory.py::_mxr_frame_factory`.

Get sizes and offsets from a compiler, not by adding up field widths. Two things
defeat reading:

- `mxr_uid` is `uint32_t[4]`, so it aligns to 4 and shifts every field behind it
  in a struct that is not `PACKED`.
- an `ALIGN(8)` struct is as wide as its alignment rounds it to, and its tail
  padding is part of the payload. Receivers test `len < sizeof(...)` before
  reading a field, so a frame short by its padding is dropped without a reply —
  which looks exactly like one that was accepted and ignored.

Paste the struct into a throwaway `.c` file with `__builtin_offsetof` and run it.
Note that `uint_fast16_t` is 4 bytes on the target, so model it as `uint32_t`
rather than letting the host pick.

Compile the struct's *own* component types, at the version you are decoding.
Substituting today's equivalents makes the result a reconstruction rather than a
measurement, and a reconstruction that happens to be right is indistinguishable
from one that is wrong until something else disagrees with it. Types get renamed
and moved between headers without their layout changing, so a name that no
longer exists is not evidence that the layout did change.

`PACKED` on a struct sets where its members are *placed*, not how wide they are.
A nested aggregate keeps its own internal padding, so a packed struct holding an
array of unpacked 12-byte records still spends 48 bytes on four of them — it
just starts them at an unaligned offset. Assuming the nesting flattens gives a
smaller size that looks plausible and decodes.

A protocol version outlives layout revisions. The struct at the commit that
introduced a version is not necessarily the struct any device sent under it, and
two revisions can share one version — so date a layout from the releases that
carried it, not from the commit that named it.

That needs both halves of the release history, which only the firmware side has.
The tag says what bytes a version sends; the distribution list says whether
anyone runs it. Tags alone invent field versions nobody has, and this protocol
has several — versions tagged and never uploaded are why two apparent
compatibility problems here turned out not to exist.

The protocol floor in `MXR_OPCODE_VERSIONS` is a delivery gate, not a layout
selector. A payload can widen without its floor moving, and then the stamp says
nothing about which layout arrived — dispatch on payload length instead.
`tests/wirefix.py` covers the cases where the two come apart.

## Writing down a deliberate divergence

A note recording *what the firmware does* reads as *what this library should
do*, and the gap between them is where every deliberate difference lives. So
write the divergence beside the fact, not somewhere else: "firmware ignores this
below 0x22" invites the next reader to delete the path that decodes it, where
"firmware ignores it, we decode it anyway, because those units still transmit
and nothing else answers them" does not.

This library is older than the firmware currently shipping and serves versions
that will never be upgraded, so it decodes more than any device does. That is
the intended relationship, not drift to be tidied up.

## Fixtures that cannot fail

A fixture can be too simple to reach the code under test. It can also be too
*helpful*: it reaches the code with the interesting input already removed, or it
supplies for free the precondition the code is supposed to establish. The second
kind is worse, because it occupies the slot where the real test would go and
reports green forever.

Ask what the setup does for the code, and whether a caller gets that for free.
A frame stamped at a version no device sends, a payload length chosen so that
one wrong branch still parses, a send exercised only against a device that had
already been introduced to us — each passes, and none of them can fail.

The check is mechanical: break the thing the test is for, one part at a time,
and watch that test go red for the right reason. An assertion that fires on a
sanity check placed above the subject has tested nothing. Note the proto/ and remote/ modules use tab indentation
while `Interface.py` and `const.py` use spaces — match the file you are editing.
