# Configuration

Opening a connection and keeping it in step with the mesh.

## Core Concepts

### Remote

`Remote` is the main entry point. It manages the UDP connection, handles device discovery, and maintains a registry of all discovered devices.

```python
# both endpoints a unit has: the group 224.8.8.8:8812 and the subnet broadcast on 8811
mx = mx_remote.Remote()

# bind to a specific network interface
mx = mx_remote.Remote(local_ip="192.168.1.100")

# tests and development only: one endpoint on a scratch address in place of both
mx = mx_remote.Remote(target_ip="239.255.77.90", port=18890)

# offline mode for processing capture files
mx = mx_remote.Remote(open_connection=False)

# separate identity, to run concurrent clients from one account
mx = mx_remote.Remote(uid_path="/var/lib/myapp/.mxr-uid")

# a mesh device that can take the controller role, under its own serial and version
mx = mx_remote.Remote(mesh_device=True, serial="P9SN66660600", version="1.2.3")
```

A client confined to one interface is invisible on every other, so a dedicated
controller speaking the protocol on its mesh link alone is not listed by the
units on its uplink LAN. `announce_interfaces` names interfaces that get each
hello, and a dedicated controller's `CONTROLLER_STATE` hello, from a send-only
socket bound to the interface's current address:

```python
mx = mx_remote.Remote(local_ip="10.8.80.30", dedicated_controller=True, announce_interfaces=["eth1"])
mx.set_announce_interfaces(["eth1", "wlan0"])   # while running, announced at once
```

The socket is rebound when that address changes and skipped while there is
none, as on a DHCP uplink; nothing arriving there is taken. The hello there
leaves out `MANAGER` (a unit takes a promotion to controller from a manager),
`MESH_MASTER` (a unit joining a mesh joins it) and `OSD_SYNC` (a source syncs
every device with it, in any mesh). `MESH_MEMBER` stays, so no unit takes the
client for one free to join.

On Linux, the interface `local_ip` selects is the only one datagrams are taken
from, so a device reachable only by another interface stays unknown, and
starting fails when no interface holds the address. Elsewhere, broadcasts on
every interface still arrive.

Each frame leaves by the endpoints a unit picks for it:

- a frame for every unit at once goes to both: a discover, reboot or factory
  reset of every unit, the monitoring pulse, bay detection and the video
  processor upgrade;
- the hello goes to both when it is the first since the sockets opened, or the
  last one there went 30 s ago or more;
- a frame meant for one device alone, such as a ping or a remote-control
  action, goes by the endpoint that device is heard by;
- every other frame goes to the group, and to the broadcast address as well
  while some peer has not been heard by multicast for two minutes or reports
  that its multicast fails.

A peer heard only by broadcast in that time has this client announce
`DeviceFeature.STATUS_MCAST_FAULT` itself, at once. A datagram arriving by both
endpoints within 100 ms is acted on once. `broadcast=` is deprecated and
ignored.

The uid at `uid_path` (default `~/.mxr-uid`) is this client's identity on the mesh:
addressing is by uid in the payload, and a frame carrying our own uid is dropped as
an echo. Two clients sharing a uid are one peer to every device and each silently
discards everything the other sends, so give concurrent clients separate paths.

### Device

A `DeviceBase` represents a physical device on the network (a Pulse-Eight neo matrix, OneIP unit, or ProAmp8 amplifier). Devices are automatically registered when they respond to discovery requests.

The registry is kept as a unit keeps its own. Every frame from a live device
keeps it alive, and only a hello brings back one gone silent. A device silent
for three times the window that takes it offline is forgotten:
`on_device_unregistered` fires, and a hello from it later registers it as a new
device. `mx.device_tree` lists every device and this client as a unit lists
them: depth first, each under the device whose topology report names it.

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
device.bays_online     # online, and its bays have arrived since it was heard,
                       # rebooted or went offline, as a unit judges it
device.multicast       # heard by multicast in the last two minutes; None on one endpoint
device.status          # DeviceStatus enum (ONLINE, OFFLINE, REBOOTING, BOOTING, INACTIVE)
device.raw_name        # name, version and serial as the bytes announced,
device.raw_version     # never substituted or decoded
device.raw_serial
device.igmp_querier    # the IGMP querier its last uplink report names, or None
device.features        # DeviceFeatures bitmask
device.config_initialised  # False if the device broadcasts config blocks built from
                           # uninitialised memory; scaling, bay 0 addresses and the
                           # rc target padding are unreliable from it
device.temperatures    # dict of temperature sensor readings

# device type checks
device.is_oneip             # Pulse-Eight OneIP HDMI-over-IP device
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
bay.status_word      # the whole BayStatusMask as last sent, or None

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
    local_ip="192.168.1.100",
    callbacks=MyCallbacks(),
    name="My Application",
)
```

---

[Documentation index](README.md) | [Project README](https://github.com/opdenkamp/mx-remote#readme)
