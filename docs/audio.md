# Audio

Volume, mute and remote-control passthrough.

## Volume Control

```python
bay.volume_up()
bay.volume_down()
bay.volume_set(volume=50)           # set to 50%
bay.volume_set(volume=50, muted=False)
bay.mute_set(mute=True)
```

## Audio endpoints

A OneIP device reports its audio endpoints, each with its features and a status
word on the same bits: `FEATURE_MUTE` while it is muted, `FEATURE_TRIGGER`
while its trigger is active, and `FEATURE_AUDIO_LOCK` while its audio source is
locked.

```python
ep = device.audio_endpoint_by_id(1)
print(ep.features, ep.status, ep.audio_locked)

# keep the endpoint's audio source when the video route changes
await device.set_audio_endpoint_locked(1, True)
```

Only an endpoint whose features include `FEATURE_AUDIO_LOCK` is written, since
the device ignores the rest. The device answers by reporting its endpoints
again, so `audio_locked` reads the lock once that report arrives, and a report
whose only change is a status fires the device's callbacks.

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

---

[Documentation index](README.md) | [Project README](https://github.com/opdenkamp/mx-remote#readme)
