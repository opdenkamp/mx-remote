# mx_remote

Python 3 library for discovering and controlling [Pulse-Eight](https://www.pulse-eight.com/)
AV distribution hardware — neo matrices, OneIP HDMI-over-IP units, multiviewers and
ProAmp8 amplifiers — over the MX Remote protocol they share.

```sh
pip install mx_remote
```

```python
import mx_remote

mx = mx_remote.Remote()
await mx.start_async()
```

The guides below cover the library task by task. The [API reference](api.md) is
generated from the package's docstrings and lists everything.

```{toctree}
:maxdepth: 2

README
configuration
devices-and-bays
routing
callbacks
audio
oneip
multiviewer
diagnostics
api
```
