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
the device ignores the rest. Once the frame is away `audio_locked` reads the new
lock, until the device reports its endpoints again. A report whose only change
is a status, the routing or the device's own address fires the device's
callbacks.

`device.audio_endpoints.address` is the device's own address and HTTP port, as
its report gives them. `device.audio_reported` is when its last report was
taken, as `time.time()` read it.

### What a command holds

For 500 ms after an audio command to a device, its features and links reports
are ignored, so one it sent before it took the command cannot undo what the
command set. The report after that replaces it.

## Audio routes

A route can run from an endpoint on one unit to an endpoint on another, such as
an encoder's HDMI input to a decoder's HDMI output. Every unit owning an
endpoint on the way switches its own hops, and each finds the path itself from
the two units' endpoint tables. `audio_route()` finds the same path and returns
it hop by hop from the source, or `None` when there is none:

```python
hops = mx.audio_route(decoder.remote_id, 3, encoder.remote_id, 2)
for hop in hops:    # AudioHop(sink_device, sink, source_device, source)
    print(hop)

await mx.select_audio_endpoint_input(decoder.remote_id, 3, encoder.remote_id, 2)
```

`select_audio_endpoint_input()` sends the request to every unit on the path,
from the sink's end, and each unit's own hops read routed once its frame is
away. It is refused, sending nothing, when no reported path leads from the
source to the sink, and when the path reaches a unit on released firmware up to
4.4.2 from another unit, since such a unit routes only between its own
endpoints. An output bay's `select_audio_source(source, endpoint=...)` goes the
same way.

The path is searched back from the sink, within the sink's unit, depth first.
An endpoint takes the source directly when it is routed from the source's
endpoint id, or when it receives a OneIP stream and the source sends one.
Otherwise the endpoints it is routed from are tried in ascending id, a later
one kept only when its path is strictly shorter. Failing that, the source
unit's first sending endpoint feeds the sink unit's first receiving one.

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
