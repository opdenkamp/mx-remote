from .Bay import Bay
from .Device import Device
from mx_remote.proto.FrameHello import FrameHello
from typing import Any, NoReturn
import asyncio

class Devices:
	''' remote device registry '''
	def __init__(self):
		self.remotes = {}
		self._refresh_task = None

	def on_connection_made(self) -> None:
		pass

	async def close(self) -> None:
		# stop the api refresh task
		if self._refresh_task is not None:
			self._refresh_task.cancel()
			self._refresh_task = None

	def on_mxr_hello(self, hello_frame:FrameHello) -> Device:
		# hello frame received. register or update the local device cache
		d = None
		if hello_frame.remote_id in self.remotes.keys():
			d = self.remotes[hello_frame.remote_id]
		else:
			d = Device(self, hello_frame)
			self.remotes[hello_frame.remote_id] = d
		d.on_mxr_hello(hello_frame)
		return d

	def get(self, remote_id:str) -> Device:
		# get the local cache for a device, given it's unique id
		if remote_id in self.remotes.keys():
			return self.remotes[remote_id]
		return None

	def get_by_serial(self, serial:str) -> Device:
		# get the local cache for a device, given it's serial number
		for _, remote in self.remotes.items():
			if serial == remote.serial:
				return remote
		return None

	def get_bay_by_portnum(self, remote_id:str, portnum:int) -> Bay:
		# get the local cache for a bay, given the device's unique id and port number
		if remote_id not in self.remotes.keys():
			return None
		return self.remotes[remote_id].get_by_portnum(portnum)

