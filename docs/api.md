# API reference

Generated from the docstrings in the package. The guides cover how these fit
together; this page is the exhaustive list.

Autodoc emits reStructuredText, which the markdown parser does not read, so
every directive below sits in an `eval-rst` block. Without it the page renders
the directive source as prose and the build still succeeds.

```{eval-rst}
.. automodule:: mx_remote
```

## Client

`Remote` owns the socket, the device registry and the background probe that
keeps both in step with the mesh.

```{eval-rst}
.. automodule:: mx_remote.remote.Remote
   :members:
```

## Devices, bays and callbacks

A client works against these types rather than the classes implementing them:
they are what the registry hands out and what a callback receives.

```{eval-rst}
.. automodule:: mx_remote.Interface
   :members:
```

## Device identity

```{eval-rst}
.. automodule:: mx_remote.Uid
   :members:
```

## Remote-control keys and actions

The key and action codes a bay reports, and the target a key was aimed at.

```{eval-rst}
.. autoclass:: mx_remote.proto.Constants.RCKey
   :members:
   :undoc-members:

.. autoclass:: mx_remote.proto.Constants.RCAction
   :members:
   :undoc-members:

.. autoclass:: mx_remote.proto.Constants.RCType
   :members:
   :undoc-members:

.. autodata:: mx_remote.proto.Constants.MXR_PROTOCOL_VERSION
```

## OneIP device settings

The settings a OneIP device reports and a controller writes, each behind its own
bit, and the range of the infrared profiles.

```{eval-rst}
.. autoclass:: mx_remote.proto.Constants.OneIPDeviceSetting
   :members:
   :undoc-members:

.. autodata:: mx_remote.proto.Constants.ONEIP_DEVICE_SETTING_SWITCHES

.. autodata:: mx_remote.proto.Constants.ONEIP_IR_PROFILE_NOT_SET

.. autodata:: mx_remote.proto.Constants.ONEIP_IR_PROFILE_MAX

.. autodata:: mx_remote.proto.Constants.ONEIP_DEVICE_SETTINGS_REPORTED_ONLY

.. autodata:: mx_remote.proto.Constants.ONEIP_MINUTES_PER_DAY

.. autoclass:: mx_remote.OneIPPowerSaveSchedule
   :members:

.. autoclass:: mx_remote.OneIPVlan
   :members:

.. autoclass:: mx_remote.proto.Constants.OneIPVlanFlag
   :members:

.. autodata:: mx_remote.proto.Constants.ONEIP_VLAN_PORTS

.. autodata:: mx_remote.proto.Constants.ONEIP_VLAN_PORT_SFP

.. autodata:: mx_remote.proto.Constants.ONEIP_VLAN_ID_MAX
```

## OneIP test card

A sink's test pattern, tone and lip-sync flash, and the ranges it accepts.

```{eval-rst}
.. autoclass:: mx_remote.OneIPTestcard
   :members:

.. autoclass:: mx_remote.OneIPTestTone
   :members:

.. autoclass:: mx_remote.OneIPTestSync
   :members:

.. autoclass:: mx_remote.proto.Constants.OneIPTestPattern
   :members:

.. autoclass:: mx_remote.proto.Constants.OneIPToneMode
   :members:

.. autoclass:: mx_remote.proto.Constants.OneIPTestcardFlag
   :members:

.. autodata:: mx_remote.proto.Constants.ONEIP_TONE_FREQ_MIN

.. autodata:: mx_remote.proto.Constants.ONEIP_TONE_FREQ_MAX

.. autodata:: mx_remote.proto.Constants.ONEIP_TONE_LEVEL_MIN

.. autodata:: mx_remote.proto.Constants.ONEIP_TONE_CHANNELS_MAX

.. autodata:: mx_remote.proto.Constants.ONEIP_TONE_RATES

.. autodata:: mx_remote.proto.Constants.ONEIP_SYNC_OFFSET_MAX

.. autodata:: mx_remote.proto.Constants.ONEIP_SYNC_BEEP_MS_MIN

.. autodata:: mx_remote.proto.Constants.ONEIP_SYNC_BEEP_MS_MAX
```

## Mesh time

The time zone and clock a mesh controller announces.

```{eval-rst}
.. autoclass:: mx_remote.TimeZone
   :members:

.. autoclass:: mx_remote.DeviceClock
   :members:
```

## Names from before OneIP

Releases up to 5.11 used the firmware's internal names in the public API: V2IP
for OneIP and FPGA for the video processor. Each old name maps to the new one
by spelling alone - `V2IP` becomes `OneIP` (`ONEIP` in a constant, `oneip` in
a member), and `Fpga` or `FPGA` becomes `VideoProcessor` or `VIDEO_PROCESSOR`:
`device.v2ip_settings` is `device.oneip_settings`, `V2IPFpgaFeature` is
`OneIPVideoProcessorFeature`, `FirmwareType.FPGA` is
`FirmwareType.VIDEO_PROCESSOR`.

The old names still resolve. A module-level name or a class member raises a
`DeprecationWarning` naming its replacement; an enum member and an
`AudioFeatures` bit constant are plain aliases, since those cannot warn. The old
names are left out of `from mx_remote import *` and out of the type stubs, so a
type checker reports them, and they will be removed in a future major release.

One rename has no alias: a OneIP device's `temperatures` dict reports the video
processor's sensor under `'Video Processor'`, where it used `'FPGA'`.

