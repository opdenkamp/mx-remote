# Devices and bays

Naming, hiding, EDID and the device registry.

## Device Management

```python
# reboot a device
await device.reboot()

# read the device log
log = await device.get_log()

# call an HTTP API endpoint on the device
result = await device.get_api("system/status")
```

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

---

[Documentation index](README.md) | [Project README](../README.md)
