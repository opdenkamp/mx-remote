# Multiviewer

Layout, sources and output configuration.

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

---

[Documentation index](README.md) | [Project README](https://github.com/opdenkamp/mx-remote#readme)
