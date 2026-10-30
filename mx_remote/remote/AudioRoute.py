######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''The audio route between two endpoints, found as every unit finds it.

A route across units, such as an encoder's HDMI input to a decoder's HDMI
output, is switched by every unit owning an endpoint on the way, and each finds
the path itself from the two devices' endpoint tables alone. A client sending
the route has to find the same one, or the units it addresses are not the ones
that act.'''

from ..Interface import AudioEndpoint, AudioEndpoints, AudioHop, MxrDeviceUid

_ROUTE_BITS = 32
'''How many endpoint ids a routes word names.'''

def _routes(ep:AudioEndpoint) -> int:
	'''The endpoint ids ep can be routed from, as a mask; 0 when it reported
	none.'''
	return getattr(ep, 'in_routes_supported', None) or 0

def _named(routes:int, id:int) -> bool:
	return (id < _ROUTE_BITS) and ((routes & (1 << id)) != 0)

def _back_from(device:MxrDeviceUid, eps:AudioEndpoints, node:int, source:tuple[MxrDeviceUid, int],
               source_ep:AudioEndpoint, visited:set[int]) -> list[AudioHop]|None:
	'''The route into endpoint node of the sink's device from source, as
	audio_path searches it.'''
	ep = eps.get(node)
	if (ep is None):
		return None
	routes = _routes(ep)
	stream = ep.features.is_oneip_rx and source_ep.features.is_oneip_tx
	if _named(routes, source[1]) or stream:
		return [AudioHop(device, node, source[0], source[1])]
	best:list[AudioHop]|None = None
	for input in (id for id in range(_ROUTE_BITS) if _named(routes, id)):
		if (input in visited):
			continue
		visited.add(input)
		path = _back_from(device, eps, input, source, source_ep, visited)
		if (path is not None):
			path.append(AudioHop(device, node, device, input))
			if (best is None) or (len(path) < len(best)):
				best = path
	return best

def audio_path(endpoints:dict[MxrDeviceUid, AudioEndpoints], sink:tuple[MxrDeviceUid, int],
               source:tuple[MxrDeviceUid, int]) -> list[AudioHop]|None:
	'''The audio route from source to sink, each a device and an endpoint id,
	hop by hop from the source; None when there is none.

	The search walks back from the sink, depth first, within the sink's
	device. A node takes the source directly when the source's endpoint id is
	among the node's routes, whichever device the source is on, or when the
	node receives a OneIP stream and the source sends one. Otherwise its routes
	are tried in ascending endpoint id, a later candidate replacing an earlier
	one only when strictly shorter, each endpoint searched once per request.
	When that finds nothing, the route is the source device's first sending
	endpoint feeding the sink device's first receiving one, which feeds the
	sink. A route of more than one hop inside the sink's device leaves out the
	hop into the sink itself.'''
	sink_eps = endpoints.get(sink[0])
	source_eps = endpoints.get(source[0])
	if (sink_eps is None) or (source_eps is None) or (sink_eps.get(sink[1]) is None):
		return None
	if ((source_ep := source_eps.get(source[1])) is None) or (sink == source):
		return None
	hops = _back_from(sink[0], sink_eps, sink[1], source, source_ep, {sink[1]})
	if (hops is None):
		tx = next((ep.id for ep in source_eps.as_list if ep.features.is_oneip_tx), None)
		rx = next((ep.id for ep in sink_eps.as_list if ep.features.is_oneip_rx), None)
		if (tx is None) or (rx is None):
			return None
		hops = []
		if (tx != source[1]):
			hops.append(AudioHop(source[0], tx, source[0], source[1]))
		hops.append(AudioHop(sink[0], rx, source[0], tx))
		if (rx != sink[1]):
			hops.append(AudioHop(sink[0], sink[1], sink[0], rx))
	inside = sum(1 for hop in hops if (hop.sink_device == sink[0]) and (hop.source_device == sink[0]))
	if (inside > 1):
		hops = [hop for hop in hops if not ((hop.sink_device == sink[0]) and (hop.sink == sink[1]))]
	return hops
