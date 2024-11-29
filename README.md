# MX Remote Interface

Python 3 library for interfacing with MX Remote compatible devices.

## Installation

Run `pip install .`

## Documentation

Documentation is embedded in the Python code, which is automatically used by most common IDEs.

You can also use Python to read the documentation:
```python
import mx_remote
help(mx_remote.Interface)
exit()
```

## Developers

Bare minimum application that runs `mx_remote`:
```python
import asyncio
import mx_remote

loop = asyncio.get_event_loop()
mx = mx_remote.Remote()
loop.run_until_complete(mx.start_async())
loop.run_forever()
```

## Application
The console application is started by running `mxr`.

The application also includes methods for debugging MX Remote networks:
* The console application will always dump all received frames in human readable form on the console
* To dump these frames in a file `mxr -u 1 -o /path/to/file.txt`
* Import frames captured by MatrixOS and dump the frames: `mxr -i /path/to/file.bin`

All command line options:
```
usage: mxr [-h] [-i INPUT] [-f FILTER] [-o OUTPUT] [-l LOCAL_IP] [-b BROADCAST] [-u UI]

MX Remote Manager / Debugger

options:
  -h, --help    show this help message and exit
  -i INPUT      capture file to process
  -f FILTER     ip address to process in the capture file
  -o OUTPUT     write output to a file
  -l LOCAL_IP   local ip address of the network interface to use
  -b BROADCAST  use broadcast mode instead of multicast mode
  -u UI         show the user interface
```

The user interface option and `mxr-ui` application are only available when `mx_remote_manager` is installed after installing `mx_remote`.
Plain `mx_remote` only includes the command line version of `mxr`.
