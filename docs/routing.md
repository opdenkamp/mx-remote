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

On a OneIP output the audio follows the video once the video is routed: a
separate audio route is dropped, so route the audio after the video to keep the
two apart. A unit below protocol 0x27 is told the source's audio stream
instead, since some of those route no audio for "follow the video".
`audio_source` reads the video source while the audio follows it.

---

[Documentation index](README.md) | [Project README](https://github.com/opdenkamp/mx-remote#readme)
