##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

import argparse
import asyncio
import logging
import mx_remote
import os
from typing import Any

_LOGGER = logging.getLogger(__name__)

# import pdb_attach
# pdb_attach.listen(50000)

def proto_parser(logger:logging.Logger, file:str, filter:str|None) -> None:
    """
    protocol parser entry point

    Process a file captured by MatrixOS or Wireshark

    Args:
        logger (logging.Logger): logger to use to output processed data from the capture file
        file (str): path to the file to process
        filter (str): IP address filter (optional)
    """
    if os.path.isfile(file):
        raise Exception(f"cannot find '{file}'")

    with open(file, "r") as f:
        data = f.read().split("\n")
        remote = mx_remote.Remote(open_connection=False)
        logger.debug(f"processing data from {file}")
        for line in data:
            spl = line.split(",")
            if len(spl) == 3:
                ts = spl[0]
                source = spl[1]
                if filter is not None and source != filter:
                    continue
                frame = bytes.fromhex(spl[2])
                try:
                    logger.debug(f"[[frame {ts}]]")
                    remote.on_datagram_received(frame, (source, 8811))
                except Exception as e:
                    logger.warning(f"source: {source}    frame FAILED: {e}")

def mxr_main( extra_args_callback:callable=None,
              log_level_callback:callable=None,
              entry_callback:callable=None,
              callback_param:Any=None) -> None:
    """
    mx_remote main entry point for stand alone applications

    Args:
        extra_args_callback (callable): callback to add extra arguments into the arguments parser
        log_level_callback (callable): callback to set the default logging level
        entry_callback (callable): callback to override the main entry point of the application
        callback_param (Any): parameter passed to callbacks
    """

    # command line arguments
    argparser = argparse.ArgumentParser(description="MX Remote Manager / Debugger")
    argparser.add_argument("-i", dest='input', help='capture file to process', required=False)
    argparser.add_argument("-f", dest='filter', help='ip address to process in the capture file', required=False)
    argparser.add_argument("-o", dest='output', help='write output to a file', required=False)
    argparser.add_argument("-l", dest='local_ip', help='local ip address of the network interface to use', required=False)
    argparser.add_argument("-b", dest='broadcast', help='use broadcast mode instead of multicast mode', required=False, type=bool)
    if (extra_args_callback is not None):
        extra_args_callback(callback_param, argparser)
    args = argparser.parse_args()

    if (log_level_callback is not None):
        default_level = log_level_callback(callback_param, args)
    else:
        default_level = logging.DEBUG

    # log output
    if (args.output is None):
        # console
        logging.basicConfig(level=default_level, format='%(asctime)s [%(levelname)s] %(message)s', force=True)
    else:
        # file
        logging.basicConfig(
            level=default_level,
            format="%(asctime)s - %(message)s",
            datefmt='%d-%b-%y %H:%M:%S',
            force=True,
            handlers=[
                logging.FileHandler(args.output),
                logging.StreamHandler()
            ])

    if (args.input is not None):
        proto_parser(_LOGGER, args.input, args.filter)
    else:
        if (entry_callback is not None) and entry_callback(callback_param, args):
            # handled externally
            return

        # run the console app
        loop = asyncio.get_event_loop()
        try:
            mx = mx_remote.Remote(local_ip=args.local_ip, broadcast=(args.broadcast is not None and args.broadcast))
            loop.run_until_complete(mx.start_async())
            loop.run_forever()
        except KeyboardInterrupt:
            pass
        loop.run_until_complete(mx.close())
        loop.close()

def mxr_console() -> None:
    mxr_main()
