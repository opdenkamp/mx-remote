# OneIP and V2IP

Streaming endpoints, stream sources and statistics.

## Pulse-Eight OneIP Devices

[Pulse-Eight OneIP](https://www.pulse-eight.com/p/248/oneip-tx) HDMI-over-IP devices expose additional streaming properties:

```python
# stream source addresses
if device.is_v2ip and device.v2ip_sources:
    for source in device.v2ip_sources:
        print(f"Video: {source.video.ip}:{source.video.port}")
        print(f"Audio: {source.audio.ip}:{source.audio.port}")

# stream details (encoder/decoder config)
if device.v2ip_details:
    details = device.v2ip_details
    print(f"Video: {details.video}")
    print(f"TX rate: {details.tx_rate}")   # None when the sender offered no rate

    # per-stream DSCP marking (None from peers that predate it)
    if details.dscp and details.dscp.complete:
        print(f"DSCP: {details.dscp}")     # video / audio / anc, 0..63

# streaming statistics
# The subscription lapses 60s after the request and there is no free-running
# mode, so call this again inside the minute to keep the 1Hz reports coming.
await device.read_stats(enable=True)   # start collecting
# ... later ...
stats = device.v2ip_stats

# what the sink's decoder recovered from the codestream it is being given.
# Three answers, and they mean different things:
if stats.decoder is None:
    pass                                  # sender predates MatrixOS 10.12.46
elif stats.decoder.reading is None:
    pass                                  # decoder has never answered
else:
    reading = stats.decoder.reading
    # Geometry is what says a picture was recovered. `format` never does: with
    # no stream it reads RGB, which is indistinguishable from a real RGB source.
    if reading.recovered:
        print(f"{reading.width}x{reading.height} {reading.format}")
    # `reason` for display, `causes` for logic. Every true cause sets its bit
    # in flags; which one keeps `reason` is a fixed priority in the video
    # processor, not the numbering. TX_BRIDGE_UNLOCKED ranks below every
    # input-side cause, so a repeating pipeline restart shows as bit 9 in
    # `causes` while `reason` names the input cause instead.
    print(f"{reading.reason}")            # None for a cause this build cannot name
    print(f"{reading.causes}")            # raw reason values, lowest first
```

### Trusting a decoder reading after a switch

The values are read off the video processor every 2s and reported every 1s,
latched between reads, so roughly every other report repeats a reading already
seen — a frame arriving says nothing about freshness. `reading.updates` counts
readings actually **stored**, so it stays still while a processor is stalled
rather than implying a refresh. It is monotonic, never reset, and wraps at
65535 (~36h).

After changing what a sink is pointed at, wait for `updates` to advance by
**two** before trusting the geometry. It ticks when the reply lands, not when
the query is sent, so a single tick can carry an answer read fractionally
before the switch.

```python
before = device.v2ip_stats.decoder.reading.updates
await sink.switch_source(...)
# ... wait until reading.updates - before >= 2 (mod 65536) ...
```

Colour depth is deliberately absent: the video processor answers depth from a
driver constant rather than from the codestream, so it was withheld rather than
shipped as a constant that looks like a measurement. Assert depth at the
encoder's input bay instead.

### What this block cannot tell you

**Whether a sink is off on purpose.** A sink someone deliberately disabled
reports `NO_PACKETS`, indefinitely — the same cause as a sink that should be
receiving and is not. There is no enablement field here, so read that from
`MXR_OP_V2IP_DEVICE_CFG` or the device's HTTP status. `IDLE` sounds like the
answer and is not: it is effectively unreachable in shipping firmware.

**Whether a single sample is representative.** `reason` during a teardown is a
sequence, not a state — a measured one passed through `SWITCH_PENDING` before
settling on `NO_PACKETS` six seconds later. Use `updates` to tell a fresh
reading from a repeat, and note it cannot see a `TX_BRIDGE_UNLOCKED` flag
carried forward across a format change: a value held over is a stored reading
like any other.

## Mesh and firmware

```python
# mesh operations
await device.mesh_promote()   # promote to mesh master
await device.mesh_remove()    # remove from mesh

# firmware versions
if device.v2ip_firmware_versions:
    for fw_type, fw in device.v2ip_firmware_versions.items():
        print(f"{fw_type}: {fw.version}")
```

---

[Documentation index](README.md) | [Project README](https://github.com/opdenkamp/mx-remote#readme)
