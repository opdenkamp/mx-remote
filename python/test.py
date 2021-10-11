import mx_remote
import asyncio
import logging

logging.basicConfig(level=logging.DEBUG)

loop = asyncio.get_event_loop()
mx = mx_remote.Remote()
coro = mx.start_async()
try:
    loop.run_until_complete(coro)
    loop.run_forever()
except KeyboardInterrupt:
    pass
loop.run_until_complete(mx.close())
loop.close()

