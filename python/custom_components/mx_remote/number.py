""" Support for Pulse-Eight mx_remote volume control """
from homeassistant.helpers.entity import Entity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.number import NumberEntity
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
_LOGGER.setLevel(logging.DEBUG)

async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry, async_add_entities) -> bool:
    @callback
    def async_add_volume(volume):
        for v in volume:
            if v._bay.dev.serial == entry.unique_id:
                hass.data[DOMAIN]['devices'][entry.unique_id]['numbers'].append(v._bay.bay_name)
                async_add_entities([v])

    async_dispatcher_connect(hass, SIGNAL_MXR_REGISTER_VOLUME, async_add_volume)
    return True

class P8VolumeControl(NumberEntity):
    def __init__(self, hass, dev, bay):
        self.hass = hass
        self._dev = dev
        self._bay = bay
        self._attr_native_max_value = 100
        self._attr_native_min_value = 0
        self._attr_mode = "slider"
        self._attr_native_step = 1
        #self._attr_entity_category = "TODO"
        self._attr_unique_id = "{} {} volume".format(self._dev.serial, self._bay.bay_name)
        self._attr_native_unit_of_measurement = "%"
        self._update = False

        async_dispatcher_connect(self.hass, SIGNAL_MXR_BAY_UPDATE, self._mxr_update)

    @property
    def should_poll(self):
        return False

    @property
    def native_value(self) -> float:
        volume = self._bay.volume
        return volume if volume is not None else STATE_UNKNOWN

    async def async_set_native_value(self, value: float) -> None:
        return await self._bay.volume_set(int(value))

    async def async_added_to_hass(self) -> None:
        self._update = True

    async def _mxr_update(self, serial, bay_name):
        if self._update and (bay_name == self._bay.bay_name) and (serial == self._bay.dev.serial):
            self.async_write_ha_state()

    @property
    def available(self):
        return self._dev is not None

    @property
    def name(self):
        return "{} volume".format(self._bay.user_name)

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
