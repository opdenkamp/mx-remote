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
# A configuration frame names its subject in the payload, so a controller's
# write for a transceiver reaches the transceiver's record - the controller's
# own stays empty, which is what the device always meant.
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

## Sink output scaling

A sink scales for two independent reasons: automatic scaling, and a configured
output mode. Each is written behind its own validity bit, so moving one leaves
the other where it is.

```python
# what the sink reports. Trust this block only from a device whose hello carries
# CONFIG_INITIALISED - firmware without it builds the block over uninitialised
# stack, where the valid bit itself is noise.
scaling = device.v2ip_details.scaling
print(scaling.auto_scaling)        # None when the sender did not say
print(scaling.configured_mode)     # (signal type, refresh), None when it has none

# a mode is given as a depth and a colour space, never as a packed signal-type
# word read back off the wire: a sink with no mode reports the word carrying the
# index for "no depth", which a receiver decodes to zero and drops in silence.
mode = mx_remote.V2IPOutputMode(svd=16, depth=12,
                                colour=mx_remote.VideoColourSpace.YUV422, refresh=60)

await device.set_v2ip_auto_scaling(False)   # turn it off before setting a mode
await device.set_v2ip_output_mode(mode)
await device.set_v2ip_auto_scaling(True)    # back on, if that is what you want

await device.clear_v2ip_output_mode()       # the only way to say "no mode"
```

**Set the mode with automatic scaling off.** A sink scaling automatically
refuses a mode whose format the attached display does not list, and refuses it
in silence. Setting the mode first and turning automatic scaling back on
afterwards is the order that survives, because the mode is checked while
automatic scaling is still off.

Nothing acknowledges any of these. `set_v2ip_output_mode` returns False for a
mode no sink would take, but a True only says the frame went out: the sink
weighs the format against the display's EDID and against what its own output
stage can produce, and refuses silently either way. Read `v2ip_details.scaling`
back on the device's next report to learn what it did.

A scaling change makes the device rebuild and rebroadcast its sink block, so
expect `device.v2ip_sink` to read empty for a moment afterwards - see
[what an empty sink block means](#what-an-empty-sink-block-means).

## What an empty sink block means

`device.v2ip_sink` addresses that read as unset mean "no route, or the sink
could not work one out", never "definitely not subscribed". This is the one part
of a device configuration with no validity marker of its own, so a sender with
nothing to say sends zeros and every receiver stores them. A sender leaves it
empty whenever its own stream configuration does not resolve, which covers more
than having no route: a selected source whose record has not arrived yet, the
state after a restart at either end, missing audio bay configuration, or a
stream failing its validity check.

Expect that reading rather than guarding against it. Any scaling change rebuilds
and rebroadcasts the block, and a write aimed at a remote bay sends it zeroed
however it was requested, so an empty reading turns up most often during exactly
the no-signal troubleshooting that prompted the change. A device's periodic
report puts a real route back within a minute of it having one, so wait one out
rather than treat the first empty reading as an answer.

The library caches an empty reading rather than dropping it. A sink that has
genuinely lost its route sends the same zeros, and so does every report after
it, so refusing them would hold a route that nothing later could clear.

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
