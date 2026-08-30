# Routing

Selecting video and audio sources for an output.

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

---

[Documentation index](README.md) | [Project README](../README.md)
