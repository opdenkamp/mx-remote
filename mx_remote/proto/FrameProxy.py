######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''PROXY (0x59): a OneIP controller's driver proxy.

A controller relays its mesh to one client on its uplink, by unicast on
PROXY_PORT, so that no mx_remote multicast or broadcast reaches the uplink. On
the uplink it sends a reduced hello under an uplink uid of its own and, while
the proxy is on, ANNOUNCE under that uid every 10 s. A client joins with a
driver key, after which every frame between the two goes sealed in DATA.

The layout is the controller's (docs/driver-proxy.md in v2ip-routeros-manager),
not the firmware's: units drop the opcode unread. After the sub-op byte, every
integer is big endian, unlike the rest of mx_remote.

    ANNOUNCE   0, version
    JOIN       1, version, Nd[16]
    CHALLENGE  2, Nd[16], Nc[16]
    PROOF      3, Nd[16], Nc[16], proof[32]
    RESULT     4, status, lease u16; status 0 adds Nd[16], Nc[16], proof[32]
    LEAVE      5                              (inside DATA only)
    DATA       6, counter u64, ciphertext, tag[16]
    INFO       7, version, mesh uid[16]       (inside DATA only)
'''

from __future__ import annotations
from functools import cached_property
import struct
from .FrameBase import FrameBase
from .Constants import PROXY_OPCODE, PROXY_VERSION, MXR_OPCODE_VERSIONS, ProxySubOp, decode_enum
from ..Uid import MxrDeviceUid

NONCE_SIZE = 16
PROOF_SIZE = 32
TAG_SIZE = 16
COUNTER_SIZE = 8
HEADER_SIZE = 24

def proxy_frame(uid:bytes, payload:bytes) -> bytes:
	'''A whole PROXY datagram from uid carrying payload, its sub-op first.'''
	return bytes([0x50, 0x38, MXR_OPCODE_VERSIONS[PROXY_OPCODE], 0]) + bytes(uid) \
		+ struct.pack('<HH', PROXY_OPCODE, len(payload)) + payload

def join_payload(nd:bytes) -> bytes:
	return bytes([ProxySubOp.JOIN, PROXY_VERSION]) + nd

def proof_payload(nd:bytes, nc:bytes, proof:bytes) -> bytes:
	return bytes([ProxySubOp.PROOF]) + nd + nc + proof

def leave_payload() -> bytes:
	return bytes([ProxySubOp.LEAVE])

def info_payload(mesh_uid:bytes) -> bytes:
	return bytes([ProxySubOp.INFO, PROXY_VERSION]) + mesh_uid

def announce_payload() -> bytes:
	return bytes([ProxySubOp.ANNOUNCE, PROXY_VERSION])

class FrameProxy(FrameBase):
	'''A PROXY frame. Only ANNOUNCE is processed as a mesh frame; a client
	joined to a controller takes the others where they arrive.'''

	@cached_property
	def sub_op(self) -> ProxySubOp|None:
		return decode_enum(ProxySubOp, self.payload_u8(0))

	@cached_property
	def version(self) -> int|None:
		'''The version byte of ANNOUNCE, JOIN and INFO.'''
		if self.sub_op not in (ProxySubOp.ANNOUNCE, ProxySubOp.JOIN, ProxySubOp.INFO):
			return None
		return self.payload_u8(1)

	def _bytes(self, at:int, size:int) -> bytes|None:
		p = self.payload
		if (p is None) or (len(p) < (at + size)):
			return None
		return bytes(p[at:at + size])

	@cached_property
	def driver_nonce(self) -> bytes|None:
		'''Nd: in JOIN, CHALLENGE, PROOF and RESULT 0.'''
		op = self.sub_op
		if (op == ProxySubOp.JOIN):
			return self._bytes(2, NONCE_SIZE)
		if op in (ProxySubOp.CHALLENGE, ProxySubOp.PROOF):
			return self._bytes(1, NONCE_SIZE)
		if (op == ProxySubOp.RESULT) and (self.status == 0):
			return self._bytes(4, NONCE_SIZE)
		return None

	@cached_property
	def controller_nonce(self) -> bytes|None:
		'''Nc: in CHALLENGE, PROOF and RESULT 0.'''
		op = self.sub_op
		if op in (ProxySubOp.CHALLENGE, ProxySubOp.PROOF):
			return self._bytes(1 + NONCE_SIZE, NONCE_SIZE)
		if (op == ProxySubOp.RESULT) and (self.status == 0):
			return self._bytes(4 + NONCE_SIZE, NONCE_SIZE)
		return None

	@cached_property
	def proof(self) -> bytes|None:
		'''The HMAC in PROOF, and the controller's in RESULT 0.'''
		op = self.sub_op
		if (op == ProxySubOp.PROOF):
			return self._bytes(1 + 2 * NONCE_SIZE, PROOF_SIZE)
		if (op == ProxySubOp.RESULT) and (self.status == 0):
			return self._bytes(4 + 2 * NONCE_SIZE, PROOF_SIZE)
		return None

	@cached_property
	def status(self) -> int|None:
		'''The status byte of RESULT, as ProxyStatus numbers it.'''
		if (self.sub_op != ProxySubOp.RESULT) or ((b := self._bytes(1, 1)) is None):
			return None
		return b[0]

	@cached_property
	def lease(self) -> int|None:
		'''The lease of RESULT, in seconds.'''
		if (self.sub_op != ProxySubOp.RESULT) or ((b := self._bytes(2, 2)) is None):
			return None
		return int.from_bytes(b, 'big')

	@cached_property
	def counter(self) -> int|None:
		'''The counter of DATA.'''
		if (self.sub_op != ProxySubOp.DATA) or ((b := self._bytes(1, COUNTER_SIZE)) is None):
			return None
		return int.from_bytes(b, 'big')

	@cached_property
	def mesh_uid(self) -> MxrDeviceUid|None:
		'''The controller's mesh uid, in INFO.'''
		if (self.sub_op != ProxySubOp.INFO) or (self.version != PROXY_VERSION):
			return None
		b = self._bytes(2, 16)
		return None if (b is None) else MxrDeviceUid(b)

	@property
	def announces(self) -> bool:
		'''Whether this is an ANNOUNCE, of any version: a controller whose
		version this library does not speak is still one, and refuses a join
		with RESULT 5, which says why.'''
		return (self.sub_op == ProxySubOp.ANNOUNCE) and (self.version is not None)

	def process(self) -> None:
		'''Hand an ANNOUNCE to the registry, which marks its sender a proxy
		controller. Every other sub-op belongs to a joined client's session.'''
		if self.announces:
			self.mxr.on_mxr_update(self)

	def __str__(self) -> str:
		op = self.sub_op
		if (op is None):
			return "proxy: unknown sub-op"
		if (op == ProxySubOp.RESULT):
			return f"proxy result {self.status}, lease {self.lease}"
		if (op == ProxySubOp.DATA):
			return f"proxy data #{self.counter}"
		if (op == ProxySubOp.INFO):
			return f"proxy info, mesh uid {self.mesh_uid}"
		return f"proxy {op.name.lower()}"
