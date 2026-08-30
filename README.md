# MX Remote - Python Client for Pulse-Eight MatrixOS devices

Python 3 library for discovering and controlling [Pulse-Eight](https://www.pulse-eight.com/)
AV distribution hardware over a local network: video/audio matrices, HDMI-over-IP
encoders/decoders, multiviewers, and audio amplifiers. Supports device discovery,
video/audio routing, volume control, remote-control key passthrough, HDMI-over-IP
streaming, multiviewer control, and more.

If you are looking to integrate Pulse-Eight **neo**, **OneIP**, or **ProAmp8** devices into
your own software or home-automation system, this is the library for it.

## What is MX Remote?

MX Remote is the network protocol these Pulse-Eight devices use to discover and control one
another over UDP (multicast or broadcast). All of them run the shared **MatrixOS** firmware,
which speaks this protocol natively. This library is a client implementation of that
protocol — its purpose is to expose the devices to third-party software.

## Supported devices

All devices below run MatrixOS and are controlled through the same protocol:

- **[Pulse-Eight neo](https://www.pulse-eight.com/)** — HDBaseT video/audio matrices
  (neo:4, neo:8, neo:X, and splitters)
- **[Pulse-Eight OneIP](https://www.pulse-eight.com/p/248/oneip-tx)** — HDMI-over-IP
  units: Transmitter (TX), Receiver (RX), Transceiver (TZ), and Multiviewer
- **[Pulse-Eight ProAmp8](https://www.pulse-eight.com/p/219/proamp-8)** — 8-zone audio amplifier with
  Dolby support

## Requirements

- Python 3.11 or later
- Network access to one or more of the Pulse-Eight devices above (multicast or broadcast)

## Installation

```bash
pip install .
```

## Quick Start

The minimum code to discover devices on the network:

```python
import asyncio
import mx_remote

async def main():
    mx = mx_remote.Remote()
    await mx.start_async()

    # wait for devices to be discovered
    await asyncio.sleep(5)

    for uid, device in mx.remotes.items():
        print(f"{device.serial} ({device.name}) - {device.model_name} - {device.status}")
        for port, bay in device.bays.items():
            print(f"  {bay.bay_label} [{bay.mode}] signal={bay.signal_detected}")

    await mx.close()

asyncio.run(main())
```

## Documentation

The full API reference lives in [docs/](docs/README.md).

| Page | Covers |
| --- | --- |
| [Configuration](configuration.md) | Opening a connection and keeping it in step with the mesh. |
| [Devices and bays](devices-and-bays.md) | Naming, hiding, EDID and the device registry. |
| [Routing](routing.md) | Selecting video and audio sources for an output. |
| [Callbacks](callbacks.md) | Reacting to state changes rather than polling for them. |
| [Audio](audio.md) | Volume, mute and remote-control passthrough. |
| [OneIP and V2IP](oneip.md) | Streaming endpoints, stream sources and statistics. |
| [Multiviewer](multiviewer.md) | Layout, sources and output configuration. |
| [Diagnostics](diagnostics.md) | Network status, the mxr console app and capture replay. |

## Other languages

The same protocol, implemented independently:

- **Go** — https://github.com/opdenkamp/mx-remote-golang
- **Rust** — https://github.com/opdenkamp/mx-remote-rust (also ships a C ABI, for C and C++)

Python is the oldest of the three and the one that still decodes what older
firmware sent: `0x06`, `0x36` and `0x47` are superseded opcodes kept because a
unit on older firmware still emits them. So it decodes a slightly wider set than
the others, and the difference is deliberate rather than drift.

## License

BSD 3-Clause License. See [LICENSE](LICENSE) for details.

