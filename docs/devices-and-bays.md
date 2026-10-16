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
addressed to it with a hello at once, from any sender.

## Bay Naming

```python
await bay.set_name("Living Room TV")
```

## Bay Visibility

Hide or show bays:

```python
await bay.set_hidden(True)   # hide
await bay.set_hidden(False)  # show
```

## EDID Profiles

Change the EDID profile on input bays:

```python
from mx_remote import EdidProfile

await bay.select_edid_profile(EdidProfile.TEMPLATE_1080P_STEREO)
await bay.select_edid_profile(EdidProfile.TEMPLATE_4K_HDR_7_1)
await bay.select_edid_profile(EdidProfile.LOWEST_COMMON_DENOMINATOR)
```

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

Mesh bays are created by the unit's bay mappings, numbered by port in the
unit's own numbering: from protocol 0x2B input n is port n and output n port
127 + n; below it the first 16 bays of each direction come first.

---

[Documentation index](README.md) | [Project README](https://github.com/opdenkamp/mx-remote#readme)
