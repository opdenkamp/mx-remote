# Callbacks

Reacting to state changes rather than polling for them.

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

---

[Documentation index](README.md) | [Project README](../README.md)
