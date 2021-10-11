#!/usr/bin/python3

import os
import aiohttp
import asyncio
import logging
from typing import Tuple

import mx_remote.proto as proto
import mx_remote.remote as remote
from .ConnectionAsync import ConnectionAsync

from .const import DEFAULT_UDP_IP
from .const import UDP_PORT

class Remote(remote.Devices):
    ''' Main component that handles the network connections and registration of remote devices '''

    _on_device_config_changed = None
    _on_device_config_complete = None
    _on_bay_registered = None
    _on_power_changed = None
    _on_name_changed = None
    _on_device_temperature_changed = None
    _on_status_signal_detected_changed = None
    _on_status_faulty_changed = None
    _on_status_hidden_changed = None
    _on_status_poe_powered_changed = None
    _on_status_hdbt_connected_changed = None
    _on_status_signal_type_changed = None
    _on_status_hpd_detected_changed = None
    _on_status_cec_detected_changed = None
    _on_status_arc_changed = None
    _on_volume_changed = None
    _on_key_pressed = None
    _on_video_source_changed = None
    _on_audio_source_changed = None
    _on_pdu_registered = None
    _on_pdu_changed = None
    _on_bay_linked = None
    _on_bay_unlinked = None
    _on_link_status_changed = None

    def __init__(self, target_ip=None, http_session=None):
        super().__init__()
        self._target_ip = target_ip
        self.uid = os.urandom(16) # TODO currently using a random id. store this
        self.conn = ConnectionAsync(self)
        if http_session is None:
            self._close_session = True
            http_session = aiohttp.ClientSession()
        else:
            self._close_session = False
        self.http_session = http_session

    @property
    def target_ip(self):
        # target ip address. TODO auto determine broadcast address on the primary interface
        return self._target_ip if (self._target_ip is not None) else DEFAULT_UDP_IP

    def start_async(self):
        # start the server that listens for mx_remote frames from other devices
        return self.conn.start_srv()

    async def close(self):
        # close all open connections
        await super().close()
        if self.conn is not None:
            self.conn.close()
        if self._close_session:
            await self.http_session.close()

    def tx_discover(self):
        # transmit a discover frame. all remotes will send a hello frame as response
        pkt = proto.create_mxr_frame(self.uid, 1)
        logging.info("discovering devices")
        return self.conn.transmit(pkt)

    def on_connection_made(self):
        # callback called after the server got started by ConnectionAsync
        self.tx_discover()
        super().on_connection_made()

    def on_datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        # called when a udp frame was received
        frame = proto.process_mxr_frame(self, data, addr)
        if frame is not None:
           frame.process()

    def on_device_config_changed(self, dev):
        logging.debug("%s updated", str(dev))
        if self._on_device_config_changed is not None:
            self._on_device_config_changed(dev)

    def set_cb_device_config_changed(self, cb):
        self._on_device_config_changed = cb

    def on_device_config_complete(self, dev):
        # called when the configuration of a remote device was fully received
        logging.debug("%s configuration complete", str(dev))
        if self._on_device_config_complete is not None:
            self._on_device_config_complete(dev)

    def set_cb_on_device_config_complete(self, cb):
        self._on_device_config_complete = cb

    def on_bay_registered(self, bay):
        logging.debug("(%s) registered: %s", str(bay), str(bay.features))
        if self._on_bay_registered is not None:
            self._on_bay_registered(bay)

    def set_cb_on_bay_registered(self, cb):
        self._on_bay_registered = cb

    def on_device_temperature_changed(self, dev):
        logging.debug("%s temperature: %s", str(dev), str(dev.temperature))
        if self._on_device_temperature_changed is not None:
            self._on_device_temperature_changed(dev)

    def set_cb_on_device_temperature_changed(self, cb):
        self._on_device_temperature_changed = cb

    def on_power_changed(self, bay, power):
        logging.debug("(%s) power status %s", str(bay), power)
        if self._on_power_changed is not None:
            self._on_power_changed(bay, power)

    def set_cb_on_power_changed(self, cb):
        self._on_power_changed = cb

    def on_name_changed(self, bay, user_name):
        logging.debug("(%s) name changed: %s", str(bay), user_name)
        if self._on_name_changed is not None:
            self._on_name_changed(bay, user_name)

    def set_cb_on_name_changed(self, cb):
        self._on_name_changed = cb

    def on_status_signal_detected_changed(self, bay, val):
        lval = "signal detected" if val else "no signal"
        logging.debug("(%s) %s", str(bay), lval)
        if self._on_status_signal_detected_changed is not None:
            self._on_status_signal_detected_changed(bay, val)

    def set_cb_on_status_signal_detected_changed(self, cb):
        self._on_status_signal_detected_changed = cb

    def on_status_faulty_changed(self, bay, val):
        lval = "FAULT" if val else "healthy"
        logging.debug("(%s) %s", str(bay), lval)
        if self._on_status_faulty_changed is not None:
            self._on_status_faulty_changed(bay, val)

    def set_cb_on_status_faulty_changed(self, cb):
        self._on_status_faulty_changed = cb

    def on_status_hidden_changed(self, bay, val):
        lval = "hidden" if val else "visible"
        logging.debug("(%s) %s", str(bay), lval)
        if self._on_status_hidden_changed is not None:
            self._on_status_hidden_changed(bay, val)

    def set_cb_on_status_hidden_changed(self, cb):
        self._on_status_hidden_changed = cb

    def on_status_poe_powered_changed(self, bay, val):
        lval = "on" if val else "off"
        logging.debug("(%s) PoE %s", str(bay), lval)
        if self._on_status_poe_powered_changed is not None:
            self._on_status_poe_powered_changed(bay, val)

    def set_cb_on_status_poe_powered_changed(self, cb):
        self._on_status_poe_powered_changed = cb

    def on_status_hdbt_connected_changed(self, bay, val):
        lval = "up" if val else "down"
        logging.debug("(%s) HDBaseT link %s", str(bay), lval)
        if self._on_status_hdbt_connected_changed is not None:
            self._on_status_hdbt_connected_changed(bay, val)

    def set_cb_on_status_hdbt_connected_changed(self, cb):
        self._on_status_hdbt_connected_changed = cb

    def on_status_signal_type_changed(self, bay, val):
        logging.debug("(%s) signal type: %s", str(bay), val)
        if self._on_status_signal_type_changed is not None:
            self._on_status_signal_type_changed(bay, val)

    def set_cb_on_status_signal_type_changed(self, cb):
        self._on_status_signal_type_changed = cb

    def on_status_hpd_detected_changed(self, bay, val):
        lval = "detected" if val else "lost"
        logging.debug("(%s) hotplug %s", str(bay), lval)
        if self._on_status_hpd_detected_changed is not None:
            self._on_status_hpd_detected_changed(bay, val)

    def set_cb_on_status_hpd_detected_changed(self, cb):
        self._on_status_hpd_detected_changed = cb

    def on_status_cec_detected_changed(self, bay, val):
        lval = "detected" if val else "not found"
        logging.debug("(%s) HDMI-CEC device %s", str(bay), lval)
        if self._on_status_cec_detected_changed is not None:
            self._on_status_cec_detected_changed(bay, val)

    def set_cb_on_status_cec_detected_changed(self, cb):
        self._on_status_cec_detected_changed = cb

    def on_status_arc_changed(self, bay, val):
        logging.info("(%s) ARC: %s", str(bay), val)
        if self._on_status_arc_changed is not None:
            self._on_status_arc_changed(bay, val)

    def set_cb_on_status_arc_changed(self, cb):
        self._on_status_arc_changed = cb

    def on_volume_changed(self, bay, volume):
        muted_str = ""
        volume_str = ""
        if volume.muted is not None:
            muted_str = " not muted" if not volume.muted else " muted"
        if volume.volume is not None:
            volume_str = " volume {}%".format(volume.volume)
        logging.debug("(%s)%s%s", str(bay), volume_str, muted_str)
        if self._on_volume_changed is not None:
            self._on_volume_changed(bay, volume)

    def set_cb_on_volume_changed(self, cb):
        self._on_volume_changed = cb

    def on_key_pressed(self, bay, key):
        logging.debug("(%s) key pressed: %s", str(bay), str(key))
        if self._on_key_pressed is not None:
            self._on_key_pressed(bay, key)

    def set_cb_on_key_pressed(self, cb):
        self._on_key_pressed = cb

    def on_video_source_changed(self, bay, video_source):
        logging.debug("(%s) video routed to (%s)", str(bay), str(video_source))
        if self._on_video_source_changed is not None:
            self._on_video_source_changed(bay, video_source)

    def set_cb_on_video_source_changed(self, cb):
        self._on_video_source_changed = cb

    def on_audio_source_changed(self, bay, audio_source):
        logging.debug("(%s) audio routed to (%s)", str(bay), str(audio_source))
        if self._on_audio_source_changed is not None:
            self._on_audio_source_changed(bay, audio_source)

    def set_cb_on_audio_source_changed(self, cb):
        self._on_audio_source_changed = cb

    def on_pdu_registered(self, pdu):
        logging.debug("%s pdu registered: %s", str(pdu.dev), str(pdu))
        if self._on_pdu_registered is not None:
            self._on_pdu_registered(pdu)

    def set_cb_on_pdu_registered(self, cb):
        self._on_pdu_registered = cb

    def on_pdu_changed(self, pdu):
        logging.debug("%s pdu: %s", str(pdu.dev), str(pdu))
        if self._on_pdu_changed is not None:
            self._on_pdu_changed(pdu)

    def set_cb_on_pdu_changed(self, cb):
        self._on_pdu_changed = cb

    def on_bay_linked(self, link):
        if self._on_bay_linked is not None:
            self._on_bay_linked(link)

    def set_cb_on_bay_linked(self, cb):
        self._on_bay_linked = cb

    def on_bay_unlinked(self, bay, serial, bay_name):
        logging.debug("(%s) unlinked from (%s %s)", str(bay), serial, bay_name)
        if self._on_bay_unlinked is not None:
            self._on_bay_unlinked(bay, serial, bay_name)

    def set_cb_on_bay_unlinked(self, cb):
        self._on_bay_unlinked = cb

    def on_link_status_changed(self, link):
        logging.debug(str(link))
        if self._on_link_status_changed is not None:
            self._on_link_status_changed(link)

    def set_cb_on_link_status_changed(self, cb):
        self._on_link_status_changed = cb

