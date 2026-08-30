# OneIP and V2IP

Streaming endpoints, stream sources and statistics.

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
    print(f"TX rate: {details.tx_rate}")   # None when the sender offered no rate

    # per-stream DSCP marking (None from peers that predate it)
    if details.dscp and details.dscp.complete:
        print(f"DSCP: {details.dscp}")     # video / audio / anc, 0..63

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

---

[Documentation index](README.md) | [Project README](../README.md)
