# Configuration

Opening a connection and keeping it in step with the mesh.

## Core Concepts

### Remote

`Remote` is the main entry point. It manages the UDP connection (multicast or broadcast), handles device discovery, and maintains a registry of all discovered devices.

```python
# default: multicast on 224.8.8.8:8812
mx = mx_remote.Remote()

# use broadcast instead
mx = mx_remote.Remote(broadcast=True)

# bind to a specific network interface
mx = mx_remote.Remote(local_ip="192.168.1.100")

# custom target address and port
mx = mx_remote.Remote(target_ip="10.8.8.255", port=8811)

# offline mode for processing capture files
mx = mx_remote.Remote(open_connection=False)

# separate identity, to run concurrent clients from one account
mx = mx_remote.Remote(uid_path="/var/lib/myapp/.mxr-uid")
```

The uid at `uid_path` (default `~/.mxr-uid`) is this client's identity on the mesh:
addressing is by uid in the payload, and a frame carrying our own uid is dropped as
an echo. Two clients sharing a uid are one peer to every device and each silently
discards everything the other sends, so give concurrent clients separate paths.

### Device

A `DeviceBase` represents a physical device on the network (a Pulse-Eight neo matrix, OneIP unit, or ProAmp8 amplifier). Devices are automatically registered when they respond to discovery requests.

```python
# look up a device by serial number or unique ID
device = mx.get_by_serial("AB1234")
device = mx.get_by_uid(uid)

# device properties
device.serial          # serial number
device.name            # device name
device.model_name      # model (e.g. "neo:8", "OneIP Transmitter")
device.address         # IP address
device.version         # firmware version
device.online          # True if responding
device.status          # DeviceStatus enum (ONLINE, OFFLINE, REBOOTING, BOOTING, INACTIVE)
device.features        # DeviceFeatures bitmask
device.config_initialised  # False if the device broadcasts config blocks built from
                           # uninitialised memory; scaling, bay 0 addresses and the
                           # rc target padding are unreliable from it
device.temperatures    # dict of temperature sensor readings

# device type checks
device.is_v2ip             # Pulse-Eight OneIP HDMI-over-IP device
device.is_video_matrix     # neo video matrix
device.is_audio_matrix     # audio-only matrix
device.is_amp              # ProAmp8 audio amplifier
device.is_oneip_tx         # OneIP transmitter
device.is_oneip_rx         # OneIP receiver
device.is_oneip_tz         # OneIP transceiver
device.is_oneip_multiviewer # OneIP multiviewer
device.supports_video_wall  # sink can crop its source to a video wall window
                            # (advertised ~1s after boot by the v2ipwall module,
                            #  and never withdrawn once advertised)

# iterate bays
for port, bay in device.bays.items():
    print(bay)
for name, bay in device.inputs.items():
    print(f"Input: {name}")
for name, bay in device.outputs.items():
    print(f"Output: {name}")
```

### Bay

A `BayBase` represents a single input or output on a device (e.g. "Input 1", "Output 3").

```python
bay.bay_name         # port name (e.g. "Input 1")
bay.user_name        # user-assigned name
bay.is_input         # True if source/input
bay.is_output        # True if sink/output
bay.is_hdmi          # True if HDMI
bay.is_audio         # True if audio-only
bay.is_hdbaset       # True if HDBaseT
bay.signal_detected  # video/audio signal present
bay.power_status     # PowerStatus enum (ON, OFF, UNKNOWN)
bay.faulty           # fault detected
bay.hidden           # hidden from UI
bay.online           # device is online
bay.features         # BayFeaturesMask
bay.status           # DeviceStatus enum

# video/audio routing (output bays)
bay.video_source              # currently selected video source bay
bay.audio_source              # currently selected audio source bay
bay.available_video_sources   # list of selectable video sources
bay.available_audio_sources   # list of selectable audio sources

# volume (bays with volume control)
bay.volume           # current volume percentage (or None)
bay.muted            # True if muted (or None)

# EDID and remote control (input bays)
bay.edid_profile     # EdidProfile enum
bay.rc_type          # RCType enum (IR, CEC, Sky, TiVo, etc.)
```

## Configuration Updates

Update connection settings at runtime:

```python
await mx.update_config(
    target_ip="10.8.8.255",
    port=8811,
    local_ip="192.168.1.100",
    broadcast=True,
    callbacks=MyCallbacks(),
    name="My Application",
)
```

---

[Documentation index](README.md) | [Project README](../README.md)
