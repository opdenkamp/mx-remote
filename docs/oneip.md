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
of a device configuration with no validity marker of its own, so a sink with
nothing to say sends zeros and the library stores them. A sender leaves it
empty whenever its own stream configuration does not resolve, which covers more
than having no route: a selected source whose record has not arrived yet, the
state after a restart at either end, missing audio bay configuration, or a
stream failing its validity check.

Expect that reading rather than guarding against it. Any scaling change rebuilds
and rebroadcasts the block, so an empty reading turns up most often during exactly
the no-signal troubleshooting that prompted the change. A device's periodic
report puts a real route back within a minute of it having one, so wait one out
rather than treat the first empty reading as an answer.

The library caches an empty reading rather than dropping it. A sink that has
genuinely lost its route sends the same zeros, and so does every report after
it, so refusing them would hold a route that nothing later could clear.

Only the device's own report sets the block. A controller writing another
device's configuration sends it zeroed, and the library ignores that copy.

## Device settings

A V2IP device reports its settings in its configuration: decoder auto-disable,
HDMI off without signal, IR modulation, the status and network LEDs, quiet fan,
CEC combo keys, and the infrared profiles. Each sits behind its own bit, so a
device reports only the settings it has, and a write changes one without
restating the rest.

```python
from mx_remote import V2IPDeviceSetting

settings = device.v2ip_settings             # None until the device has reported
print(settings.get(V2IPDeviceSetting.FAN_QUIET))   # None: the device lacks it
print(settings.ir_profile, settings.ir_profile_sink)

await device.set_v2ip_setting(V2IPDeviceSetting.STATUS_LED, False)
await device.set_v2ip_ir_profile(2)
await device.set_v2ip_sink_ir_profile(mx_remote.V2IP_IR_PROFILE_NOT_SET)  # follow the global port
```

A write returns False, without sending anything, for whatever the device would
ignore in silence: a setting it has not reported, a profile out of range, or a
device that has reported no settings at all. So a True is never a change that
does not happen, though nothing acknowledges it either: the device answers by
reporting its settings, and until then `v2ip_settings` reads back what was
written.

A write from another controller is cached only as far as the device takes it.
The list of stored infrared profiles and whether the device's clock is set are
the device's own, and are never taken from a write.

### Power save

A device powers down by itself after a number of idle minutes, and during a
daily window per weekday, kept in the device's own time zone. Times are minutes
after midnight, Monday first; a window that ends before it starts runs past
midnight, and one that ends where it starts means none that day.

```python
from mx_remote import V2IPPowerSaveSchedule

print(settings.auto_power_save)            # idle minutes, 0 for never
print(settings.power_save_schedule)        # e.g. "mon 22:00-07:00, ..."
print(settings.get(V2IPDeviceSetting.CLOCK_SET))

await device.set_v2ip_auto_power_save(30)
await device.set_v2ip_power_save_schedule(V2IPPowerSaveSchedule(
    start=(22 * 60,) * 5 + (0, 0), end=(7 * 60,) * 5 + (0, 0)))  # weeknights
```

A schedule time that is not a time of day is refused before it is sent. A write
goes out at 176 bytes: a receiver with the schedule ignores the settings of a
shorter frame, and one whose settings end at the idle minutes takes it all the
same.

### VLAN

A device that announces `DeviceFeature.VLAN` tags its uplink by a VLAN
configuration: its own VLAN id, one per external port (the SFP port, the UTP
port with PoE, then the UTP port), and the port pinned as the uplink. Ids run
0 to `V2IP_VLAN_ID_MAX`, 0 meaning untagged; ports are numbered from 1 on the
wire, 0 meaning detect the uplink.

```python
from mx_remote import V2IPVlan

vlan = device.v2ip_vlan          # None until the device reports one
print(vlan.device, vlan.port, vlan.pinned_uplink_port, vlan.active_uplink_port)
print(vlan.is_pending, vlan.revert_s)

await device.set_v2ip_vlan(V2IPVlan(device=10, port=(0, 20, 0), uplink=2))
```

Only the device knows what it runs, so `v2ip_vlan` is read only from the device
describing itself, and a write is not cached. The device applies a change at
once and reverts it after `revert_s` seconds unless the mesh controller, hearing
it report the change as pending, confirms it.

Only the ids, the uplink and the trunk bit are written. Refused before sending:
a device without the VLAN feature or that has not reported its configuration, an
id above `V2IP_VLAN_ID_MAX`, an uplink that names no port, and an SFP uplink on
a device that reports no SFP port. The write goes out as a settings write that
carries no setting plus the block, so a receiver that predates the block sees a
frame it already understood.

### Test pattern, tone and lip-sync

A sink whose video processor reports `V2IPFpgaFeature.SINK_TEST_PATTERN` draws a
test card on its output: a pattern, a test tone, and a lip-sync flash that marks
a frame and beeps a set number of sample periods after it.

```python
from mx_remote import V2IPTestPattern, V2IPTestSync, V2IPTestTone, V2IPToneMode

await sink.request_v2ip_testcard()                        # the sink reports straight back
await sink.set_v2ip_test_pattern(V2IPTestPattern.FLAT, 0x3050A0)
await sink.set_v2ip_test_tone(V2IPTestTone(mode=V2IPToneMode.CONTINUOUS,
                                           freq=1000, level=-20, channels=2, rate=48000))
await sink.set_v2ip_test_sync(V2IPTestSync(period=60, lead=0, offset=0, beep_ms=40))
await sink.set_v2ip_test_pattern(V2IPTestPattern.OFF)

print(sink.v2ip_testcard)   # None until the sink has reported
```

A pattern runs until it is turned off, and holds the output on while it does.
The sink answers every request and change with its test card, on the group, so
every client records it against the sink; a write is not cached. A sink with the
feature but without the module that draws the test card does not answer.

Each value is checked against the ranges the sink accepts, since it drops what
falls outside them in silence: see `V2IPTestTone.is_valid()` and
`V2IPTestSync.is_valid()`. A tone turned off goes out whatever else it holds,
as the sink stops it regardless. The frame needs protocol 0x2B, so a sink
announcing less is refused as well.

### Every device at once

One broadcast changes settings on every V2IP device of the mesh. Each device
applies the settings it has and ignores the rest, and none below protocol 0x2A
applies any.

```python
from mx_remote import V2IPDeviceSettings

await mx.set_all_v2ip_device_settings(V2IPDeviceSettings(
    valid=V2IPDeviceSetting.STATUS_LED | V2IPDeviceSetting.AUTO_POWER_SAVE,
    flags=V2IPDeviceSetting.STATUS_LED,      # the LED on
    auto_power_save=30))
```

Nothing is cached from it: each device that applies a change reports its
settings, and its `v2ip_settings` reads that. What every device would ignore is
refused rather than sent - no setting at all, one only a device reports about
itself, a profile out of range, or a schedule time that is not a time of day.

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

### Time zone and time

The mesh controller announces its time zone and clock with every periodic
broadcast, and each device keeps its clock and power save windows by them. Both
are recorded against the device that announced them.

```python
print(controller.time_zone)   # TimeZone(zone='Europe/Amsterdam', rule='CET-1CEST,...')
print(controller.clock)       # its clock as of now, None until it has announced one

await mx.set_mesh_time_zone('Europe/Amsterdam', 'CET-1CEST,M3.5.0,M10.5.0/3')
await mx.clear_mesh_time_zone() # no time zone: the devices keep UTC
await mx.set_mesh_time()      # now; or pass a datetime
```

A device takes either only from the controller or a management application,
which is what this client announces itself as; the controller takes them too
and announces them from then on. A device keeps its own clock where it is within
2s of the time sent. A name or rule that is empty, holds a NUL or is too long
for its field, and a time before 1970 or past 2106, are refused. A controller
without a time zone announces an empty one.

---

[Documentation index](README.md) | [Project README](https://github.com/opdenkamp/mx-remote#readme)
