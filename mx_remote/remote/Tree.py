######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''The registry as a tree, which is how a unit keeps it: who sits behind whose
switch ports, as their topology reports say, in the order a unit lists them.'''

from typing import Hashable

class _Node:
	'''Where one device sits.'''
	def __init__(self) -> None:
		self.parent:Hashable|None = None
		self.children:list[Hashable] = []

class DeviceTree:
	'''Every registered device, this client included, and where it sits.

	Keys are whatever the caller identifies a device by. None is the root, so it
	cannot be a key. Nothing is ever placed back where it was: a device added,
	moved or left behind by a forgotten parent goes to the end of the list it
	joins.'''

	def __init__(self, own:Hashable) -> None:
		'''A tree holding only this client, as a unit's registry holds the unit
		itself from the start.'''
		self._roots:list[Hashable] = []
		self._nodes:dict[Hashable, _Node] = {}
		self.add(own)

	def __contains__(self, key:Hashable) -> bool:
		return key in self._nodes

	def add(self, key:Hashable) -> None:
		'''Register key at the end of the root.'''
		if key not in self._nodes:
			self._nodes[key] = _Node()
			self._roots.append(key)

	def _list(self, parent:Hashable|None) -> list[Hashable]:
		'''The list parent's children are kept in, the root's for None.'''
		return self._roots if (parent is None) else self._nodes[parent].children

	def _place(self, key:Hashable, parent:Hashable|None) -> None:
		'''Move key to the end of parent's children, or of the root.'''
		node = self._nodes[key]
		self._list(node.parent).remove(key)
		self._list(parent).append(key)
		node.parent = parent

	def _is_below(self, key:Hashable, ancestor:Hashable) -> bool:
		'''Whether key sits anywhere below ancestor.'''
		at = self._nodes[key].parent
		# A walk longer than the tree is a cycle, which placing never makes.
		for _ in range(len(self._nodes) + 1):
			if (at is None):
				return False
			if (at == ancestor):
				return True
			at = self._nodes[at].parent
		return False

	def remove(self, key:Hashable) -> None:
		'''Forget key, moving its children to the end of its parent's.'''
		if ((node := self._nodes.pop(key, None)) is None):
			return
		self._list(node.parent).remove(key)
		for child in node.children:
			self._nodes[child].parent = node.parent
			self._list(node.parent).append(child)

	def apply_topology(self, sender:Hashable, listed:list[Hashable]) -> None:
		'''Apply a topology list sender reported, as a unit does with one that
		differs from the last.

		Each listed device is moved under the sender unless it is anywhere below
		it already. One not registered is skipped, and so is one the sender sits
		below, the sender itself included: moving it would take the sender along
		into a loop the root no longer reaches. Any direct child of the sender
		the list does not name moves to the root.'''
		if sender not in self._nodes:
			return
		for key in listed:
			if (key not in self._nodes) or (key == sender) \
					or self._is_below(key, sender) or self._is_below(sender, key):
				continue
			self._place(key, sender)
		for child in list(self._nodes[sender].children):
			if child not in listed:
				self._place(child, None)

	def walk(self) -> list[tuple[Hashable, int]]:
		'''Every device depth first, a parent before its children, with how deep
		it sits: zero at the root.'''
		out:list[tuple[Hashable, int]] = []
		stack = [(key, 0) for key in reversed(self._roots)]
		while stack:
			key, depth = stack.pop()
			out.append((key, depth))
			stack.extend((child, depth + 1) for child in reversed(self._nodes[key].children))
		return out
