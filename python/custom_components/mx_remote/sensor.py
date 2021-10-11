""" Support for Pulse-Eight Temperature sensors """
from homeassistant.helpers.entity import Entity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
import logging
from typing import Optional
from .const import *
from homeassistant.helpers.typing import (
    HomeAssistantType,
    ConfigType
)
from homeassistant.const import (
    STATE_UNKNOWN,
)

_LOGGER = logging.getLogger(__name__)
#_LOGGER.setLevel(logging.DEBUG)

async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry, async_add_entities) -> bool:
    @callback
    def async_add_sensor(dev):
        if dev.serial == entry.unique_id:
            if not hass.data[DOMAIN]['devices'][dev.serial]['sensors']:
                hass.data[DOMAIN]['devices'][dev.serial]['sensors'] = _register_sensors(hass, dev, async_add_entities)
    async_dispatcher_connect(hass, SIGNAL_MXR_DEV_UPDATE, async_add_sensor)
    return True

def _register_sensors(hass, dev, async_add_entities):
    if dev is None or dev.temperature is None:
        return False

    def temperature_value(dev, bay, nb):
        return dev.temperature[nb] if dev is not None else STATE_UNKNOWN

    nb = 0
    devs = []
    while nb < len(dev.temperature):
        devs.append(P8Sensor(hass, dev, None, nb, "Temperature", temperature_value, "temperature", "°C"))
        nb = nb + 1
    async_add_entities(devs)
    return True

class P8Sensor(Entity):
    def __init__(self, hass, dev, bay, cb_param, sensor_name, sensor_value, sensor_type, sensor_unit):
        self.hass = hass
        self._dev = dev
        self._bay = bay
        self._param = cb_param
        self._sensor_name = sensor_name
        self._sensor_value = sensor_value
        self._sensor_type = sensor_type
        self._sensor_unit = sensor_unit
        async_dispatcher_connect(hass, SIGNAL_MXR_DEV_UPDATE, self._mxr_update)

    @property
    def should_poll(self):
        return False

    @property
    def available(self):
        return self._dev is not None

    @property
    def name(self):
        return "{} {} {}".format(self._sensor_name, self._bay.mode, self._bay.user_name) if self._bay is not None else self.unique_id

    @property
    def device_state_attributes(self):
        data = {}
        data['controller'] = self._dev.serial
        return data

    @property
    def device_info(self):
        return {
            'identifiers': {
                (SENSOR_DOMAIN, DOMAIN, self._dev.serial, self._sensor_name, self._param)
             },
            'name': self.name,
            'manufacturer': 'Pulse-Eight',
            'via_device': (DOMAIN, self._dev.serial),
        }

    @property
    def unique_id(self):
        return "{} {} {}".format(self._dev.serial, self._sensor_name, self._param)

    @property
    def state(self):
        return self._sensor_value(self._dev, self._bay, self._param)

    @property
    def device_class(self) -> Optional[str]:
        """Return the device class of the sensor."""
        return self._sensor_type

    @property
    def unit_of_measurement(self):
        """Return the unit this state is expressed in."""
        return self._sensor_unit

    async def _mxr_update(self, dev):
        if (self.entity_id is not None) and (self._dev == dev):
            self.async_write_ha_state()

