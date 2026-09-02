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
