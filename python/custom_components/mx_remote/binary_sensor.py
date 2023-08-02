""" Support for Pulse-Eight binary sensors (link, signal detect, etc) """
from homeassistant.helpers.entity import Entity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
import logging
from typing import Optional
from .const import *
from homeassistant.helpers.typing import (
    HomeAssistantType,
    ConfigType
)

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)

async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry, async_add_entities) -> bool:
    @callback
    def async_add_sensor(dev):
        if dev.serial == entry.unique_id:
            if not hass.data[DOMAIN]['devices'][dev.serial]['binary_sensors']:
                hass.data[DOMAIN]['devices'][dev.serial]['binary_sensors'] = True
                _register_binary_sensors(hass, dev, async_add_entities)
    async_dispatcher_connect(hass, SIGNAL_MXR_DEV_UPDATE, async_add_sensor)
    return True

def _register_binary_sensors(hass, dev, async_add_entities):
    def hdbt_connected(bay):
        return "on" if bay.hdbt_connected else "off"

    def cec_detected(bay):
        return "on" if bay.cec_detected else "off"

    def signal_detected(bay):
        return "on" if bay.signal_detected else "off"

    devs = []
    if dev.is_video_matrix:
        for _, bay in dev.bays.items():
            if not bay.hidden and not bay.is_v2ip_remote and not bay.dev.is_amp:
                devs.append(P8BinarySensor(hass, dev, bay, "CEC", cec_detected, None))
                devs.append(P8BinarySensor(hass, dev, bay, "signal", signal_detected, None))
                if bay.is_hdbaset:
                    devs.append(P8BinarySensor(hass, dev, bay, "link", hdbt_connected, None))
    async_add_entities(devs)

class P8BinarySensor(Entity):
    def __init__(self, hass, dev, bay, sensor_name, sensor_value, sensor_type):
        self.hass = hass
        self._dev = dev
        self._bay = bay
        self._sensor_name = sensor_name
        self._sensor_value = sensor_value
        self._sensor_type = sensor_type
        self._update = False
        async_dispatcher_connect(hass, SIGNAL_MXR_DEV_UPDATE, self._mxr_update)

    @property
    def should_poll(self):
        return False

    @property
    def available(self):
        return self._dev is not None

    @property
    def name(self):
        return "{} {} {}".format(self._sensor_name, self._bay.mode, self._bay.user_name)

    @property
    def extra_state_attributes(self):
        data = {}
        data['controller'] = self._dev.serial
        return data

    @property
    def device_info(self):
        return {
            'identifiers': {
                (DOMAIN, self._dev.serial, self._bay.bay_name)
             },
            'name': self.name,
            'manufacturer': 'Pulse-Eight',
            'via_device': (DOMAIN, self._dev.serial),
        }

    @property
    def unique_id(self):
        return "{} {} {}".format(self._dev.serial, self._bay.bay_name, self._sensor_name)

    @property
    def state(self):
        return self._sensor_value(self._bay)

    @property
    def device_class(self) -> Optional[str]:
        """Return the device class of the sensor."""
        return self._sensor_type

    async def async_added_to_hass(self) -> None:
        self._update = True

    async def _mxr_update(self, dev):
        if self._update and (self._dev == dev):
            self.async_write_ha_state()

