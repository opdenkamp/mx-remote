# Diagnostics

Network status, the mxr console app and capture replay.

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

---

[Documentation index](README.md) | [Project README](../README.md)
