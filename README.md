# MX Remote — Pulse-Eight device interface

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
```

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

## Callbacks

Subclass `MxrCallbacks` to receive notifications when device or bay state changes:

```python
class MyCallbacks(mx_remote.MxrCallbacks):
    def on_device_config_complete(self, dev):
        print(f"Device ready: {dev.serial} ({dev.name})")

    def on_bay_registered(self, bay):
        print(f"Bay found: {bay.bay_label}")

    def on_video_source_changed(self, bay, video_source):
        print(f"{bay.user_name} video source -> {video_source.user_name}")

    def on_audio_source_changed(self, bay, audio_source):
        print(f"{bay.user_name} audio source -> {audio_source.user_name}")

    def on_volume_changed(self, bay, volume):
        print(f"{bay.user_name} volume: {volume}")

    def on_power_changed(self, bay, power):
        print(f"{bay.user_name} power: {power}")

    def on_device_online_status_changed(self, dev, online):
        print(f"{dev.serial} {'online' if online else 'offline'}")

mx = mx_remote.Remote(callbacks=MyCallbacks())
```

Available callback methods:

| Method | Trigger |
|---|---|
| `on_device_update` | any device property changed |
| `on_bay_update` | any bay property changed |
| `on_device_config_changed` | device configuration updated |
| `on_device_config_complete` | all device configuration received |
| `on_device_online_status_changed` | device went online/offline |
| `on_device_temperature_changed` | temperature readings changed |
| `on_bay_registered` | new bay discovered |
| `on_video_source_changed` | video routing changed |
| `on_audio_source_changed` | audio routing changed |
| `on_volume_changed` | volume or mute status changed |
| `on_power_changed` | CEC power status changed |
| `on_name_changed` | user-assigned bay name changed |
| `on_status_signal_detected_changed` | signal detect status changed |
| `on_status_faulty_changed` | fault status changed |
| `on_status_hidden_changed` | hidden status changed |
| `on_status_poe_powered_changed` | PoE power status changed |
| `on_status_hdbt_connected_changed` | HDBaseT link status changed |
| `on_status_signal_type_changed` | signal type changed |
| `on_status_hpd_detected_changed` | hotplug detect changed |
| `on_status_cec_detected_changed` | CEC device detected/lost |
| `on_status_arc_changed` | audio return channel status changed |
| `on_key_pressed` | remote control key press received |
| `on_action_received` | remote control action received |
| `on_bay_linked` | virtual link created |
| `on_bay_unlinked` | virtual link removed |
| `on_mirror_status_changed` | bay mirroring changed |
| `on_filter_status_changed` | bay filtering changed |
| `on_edid_profile_changed` | EDID profile changed |
| `on_rc_type_changed` | remote control type changed |
| `on_amp_zone_settings_changed` | amplifier zone settings changed |
| `on_amp_dolby_settings_changed` | amplifier Dolby settings changed |

You can also register per-device and per-bay callbacks:

```python
def on_device_changed(device):
    print(f"{device.serial} updated")

def on_bay_changed(bay):
    print(f"{bay.bay_label} updated")

device.register_callback(on_device_changed)
bay.register_callback(on_bay_changed)

# to unregister:
device.unregister_callback(on_device_changed)
bay.unregister_callback(on_bay_changed)
```

## Video and Audio Routing

Change video and audio sources on output bays:

```python
output = device.get_by_portname("Output 1")

# switch video source by port number
await output.select_video_source(port=0)

# switch video source by user-assigned name
await output.select_video_source_by_user_name("Blu-ray")

# switch audio source
await output.select_audio_source(source=0)
```

## Volume Control

```python
bay.volume_up()
bay.volume_down()
bay.volume_set(volume=50)           # set to 50%
bay.volume_set(volume=50, muted=False)
bay.mute_set(mute=True)
```

## Remote Control

Send remote control key presses and actions:

```python
from mx_remote import RCKey, RCAction

# send a key press
await bay.send_key(RCKey.KEY_SELECT)
await bay.send_key(RCKey.KEY_UP)

# send a remote control action
await bay.tx_action(RCAction.ACTION_POWER_ON)
await bay.tx_action(RCAction.ACTION_POWER_OFF)
await bay.tx_action(RCAction.ACTION_POWER_TOGGLE)
await bay.tx_action(RCAction.ACTION_VOLUME_UP)
await bay.tx_action(RCAction.ACTION_VOLUME_DOWN)
```

## EDID Profiles

Change the EDID profile on input bays:

```python
from mx_remote import EdidProfile

await bay.select_edid_profile(EdidProfile.TEMPLATE_1080P_STEREO)
await bay.select_edid_profile(EdidProfile.TEMPLATE_4K_HDR_7_1)
await bay.select_edid_profile(EdidProfile.LOWEST_COMMON_DENOMINATOR)
```

## Bay Visibility

Hide or show bays:

```python
await bay.set_hidden(True)   # hide
await bay.set_hidden(False)  # show
```

## Bay Naming

```python
await bay.set_name("Living Room TV")
```

## Device Management

```python
# reboot a device
await device.reboot()

# read the device log
log = await device.get_log()

# call an HTTP API endpoint on the device
result = await device.get_api("system/status")
```

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
    print(f"TX rate: {details.tx_rate}")

# streaming statistics
await device.read_stats(enable=True)   # start collecting
# ... later ...
stats = device.v2ip_stats

# mesh operations
await device.mesh_promote()   # promote to mesh master
await device.mesh_remove()    # remove from mesh

# firmware versions
if device.v2ip_firmware_versions:
    for fw_type, fw in device.v2ip_firmware_versions.items():
        print(f"{fw_type}: {fw.version}")
```

## Pulse-Eight OneIP Multiviewer

Control [OneIP Multiviewer](https://www.pulse-eight.com/p/248/oneip-tx)-specific settings:

```python
from mx_remote import (
    MultiviewerViewMode,
    MultiviewerSource,
    MultiviewerEDIDTemplate,
    MultiviewerPipSize,
    MultiviewerPipPosition,
    MultiviewerAspectRatio,
    MultiviewerOutputMode,
)

mv = device.multiviewer

# view mode
await mv.set_view_mode(MultiviewerViewMode.QUAD)

# video sources per screen
await mv.set_video_source(screen=0, source=MultiviewerSource.INPUT_1)

# audio
await mv.set_audio_source(source=MultiviewerSource.INPUT_1)
await mv.set_audio_volume(volume=80, muted=False)

# picture-in-picture
await mv.set_pip_size(MultiviewerPipSize.MEDIUM)
await mv.set_pip_position(MultiviewerPipPosition.BOTTOM_RIGHT)

# output settings
await mv.set_screen_aspect(MultiviewerAspectRatio.AR_16_9)
await mv.set_output_mode(MultiviewerOutputMode.MODE_1080P_60)
await mv.set_edid_template(MultiviewerEDIDTemplate.TEMPLATE_1080P)

# auto switching and HDCP
await mv.set_auto_switch(enable=True)
await mv.set_hdcp_mode(MultiviewerHDCPMode.AUTO)

# source mapping
await mv.set_connected_source(input=0, source=some_device_uid)
await mv.auto_route()
```

## Network Status

Inspect network port details on supported devices:

```python
for port_id, port_status in device.network_status.items():
    print(f"Port {port_status.name}: {port_status.link_speed} "
          f"{'full' if port_status.link_full_duplex else 'half'} duplex")
    if port_status.ip:
        print(f"  IP: {port_status.ip}")
    if port_status.mac_address:
        print(f"  MAC: {port_status.mac_address}")
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

## CLI Application

The `mxr` console application is installed with the package. It discovers devices and logs all received frames in human-readable form.

```
usage: mxr [-h] [-i INPUT] [-f FILTER] [-o OUTPUT] [-l LOCAL_IP] [-b]

MX Remote Manager / Debugger

options:
  -h, --help    show this help message and exit
  -i INPUT      capture file to process
  -f FILTER     only log frames from this ip address
  -o OUTPUT     write output to a file
  -l LOCAL_IP   local ip address of the network interface to use
  -b            use broadcast mode instead of multicast
```

### Examples

```bash
# discover devices and log frames to console
mxr

# bind to a specific network interface
mxr -l 192.168.1.100

# use broadcast mode
mxr -b

# log output to a file
mxr -o /path/to/output.txt

# process a capture file from MatrixOS
mxr -i /path/to/capture.bin

# process a capture file, filtering by IP address
mxr -i /path/to/capture.bin -f 10.8.8.1
```

## Programmatic Capture Processing

Process captured frames without a network connection:

```python
import mx_remote

mx_remote.proto_parser(
    logger=my_logger,
    file="/path/to/capture.bin",
    filter="10.8.8.1",   # optional IP filter
)
```

## API Documentation

Documentation is embedded in the Python code via docstrings. Most IDEs will display it automatically.

You can also use Python to browse the documentation:

```python
import mx_remote
help(mx_remote.Remote)
help(mx_remote.BayBase)
help(mx_remote.DeviceBase)
help(mx_remote.MxrCallbacks)
```

## License

BSD 3-Clause License. See [LICENSE](LICENSE) for details.
