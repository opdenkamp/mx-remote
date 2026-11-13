# Devices and bays

Naming, hiding, EDID and the device registry.

## Device Management

```python
# reboot a device
await device.reboot()

# ask a device to hello now; False for one below protocol 0x2A
await device.ping()

# read the device log
log = await device.get_log()

# call an HTTP API endpoint on the device
result = await device.get_api("system/status")
```

A device on protocol 0x2A pings a peer it suspects is gone and takes it
offline when nothing answers within about 1.5s. The client answers a ping
addressed to it with a hello at once, from a device it has heard, as a unit
does.

## Bay Naming

```python
await bay.set_name("Living Room TV")
await bay.set_name("")     # back to the default name the unit picks
```

An empty name asks the unit to reset the bay to its default. The unit picks
that name itself, so the bay keeps its current name until the unit reports the
new one in its next bay list.

## Bay Visibility

Hide or show bays:

```python
await bay.set_hidden(True)   # hide
await bay.set_hidden(False)  # show
```

A device that lost its settings reports its bays' default names and hidden
flags, with `BayStatusMask.SETTINGS_LOST` set. A bay keeps the name and hidden
flag it had until the bit clears; a bay first heard while it is set takes what
it is sent.

## EDID Profiles

Change the EDID profile on input bays:

```python
from mx_remote import EdidProfile

await bay.select_edid_profile(EdidProfile.TEMPLATE_1080P_STEREO)
await bay.select_edid_profile(EdidProfile.TEMPLATE_4K_HDR_7_1)
await bay.select_edid_profile(EdidProfile.LOWEST_COMMON_DENOMINATOR)
```

## Bay Content

A unit with a source driver, such as the Sky Q one, reports what the source on
an input is showing as named values, in the order they are meant to be shown:

```python
print(bay.content)                 # e.g. name='BBC One', number='101'
print(bay.content.get('name'))     # None when the source reports no such value
```

The names are open-ended: a driver for a new kind of source adds its own, so
pass on the ones you do not know. Each value is cleaned as a receiving unit
cleans it, so it reads as the unit's own API shows it. The content outlives the
signal, so check `signal_detected` before showing it. `on_bay_content_changed`
reports a change, and an empty `content` is a source showing nothing.

## Signal and Connected Device

`signal_type` is a description written for display. `video_details` holds the
parts it is written from, so a caller can name the signal its own way:

```python
d = bay.video_details
if d is not None and d.from_report:
    print(d.width, d.height, d.colour, d.bpp, d.interlaced, d.hdr)
```

A signal status report carries all of them for a valid stream, with `svd` 0 and
the measured size for a stream whose mode the CTA table lacks. The bay config
snapshot, which `video_details` falls back to, carries no size or flags, and
leaves them None.

A unit reports the Pulse-Eight device connected to a bay, such as an amplifier
on a matrix output, in the long form of its connect frame:

```python
if (p8 := bay.p8_device) is not None:
    print(p8.model, p8.serial, p8.version, p8.ip)
```

It is None after a short or a disconnecting connect frame.

## Mesh Bays

A OneIP unit lists the inputs and outputs of the other units in its mesh as
bays of its own. Such a mesh bay stands for bay 0 in the same direction on the
unit its `oneip_uid` names, and `is_local` is False for it.

A mesh bay keeps only its identity: its port, `bay_name`, bay number, features
and `oneip_uid`. Everything else - its user name, signal, status, routes and
volume - is read from the bay it stands for, since what one unit reports about
another unit's bay is a copy that is never refreshed. Until that unit has
reported the bay, the rest reads as never reported. A change to the bay is
reported for every mesh bay standing for it too, except its registration and
the key presses and actions that arrive on it.

A command about a mesh bay - a rename, hide, EDID profile, action, key,
power, volume, zone settings or route - goes to the unit it stands for, about
that unit's bay, and is refused while that unit has not reported the bay. A
route names that unit as the sink, and its source by port in the numbering of
the unit listing the mesh bay.

Mesh bays are created by the unit's bay mappings, numbered by port in the
unit's own numbering: from protocol 0x2B input n is port n and output n port
127 + n; below it the first 16 bays of each direction come first.

---

[Documentation index](README.md) | [Project README](https://github.com/opdenkamp/mx-remote#readme)
