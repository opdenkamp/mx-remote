### Pulse-Eight A/V Devices ###

from .const import *
from .media_player import *
from .sensor import *

from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, STATE_OFF, STATE_ON, STATE_UNKNOWN
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_connect, dispatcher_send
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_component import DEFAULT_SCAN_INTERVAL
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.entity_platform import EntityPlatform
from homeassistant.helpers.typing import (
    HomeAssistantType,
    ConfigType
)
import logging
import mx_remote as mxr
from datetime import datetime

from typing import Sequence, TypeVar, Union
import voluptuous as vol

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")  # pylint: disable=invalid-name

# This version of ensure_list interprets an empty dict as no value
def ensure_list(value: Union[T, Sequence[T]]) -> Sequence[T]:
    """Wrap value in list if it is not one."""
    if value is None or (isinstance(value, dict) and not value):
        return []
    return value if isinstance(value, list) else [value]

# schema for configuration.yaml entries
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.All(
            ensure_list,
            [
                vol.Schema(
                    {
                        # serial number is required, name is optional
                        vol.Required(CONF_SERIAL): cv.string,
                        vol.Optional(CONF_NAME): cv.string,
                    }
                )
            ],
        )
    },
    extra=vol.ALLOW_EXTRA,
)

async def async_setup(hass: HomeAssistantType, config: ConfigEntry) -> bool:
    ''' set up the mx_remote integration '''

    if (DOMAIN not in config) or (DOMAIN in hass.data):
        return False

    def _mx_start_listening(hass: HomeAssistantType) -> mxr.Remote:
        ''' create a new task to listen for mx_remote updates '''

        def on_device_config_changed(dev):
            ''' configuration of a device changed '''
            dispatcher_send(hass, SIGNAL_MXR_DEV_UPDATE, dev)

        def on_device_config_complete(dev):
            ''' full device configuration received '''
            dispatcher_send(hass, SIGNAL_MXR_DEV_UPDATE, dev)
            # notify the config flow, so new devices can be configured
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN, context={"source": DOMAIN}, data=dev
                )
            )

        def on_device_temperature_changed(dev):
            ''' temperature sensor(s) update '''
            dispatcher_send(hass, SIGNAL_MXR_DEV_UPDATE, dev) #TODO
            dispatcher_send(hass, SIGNAL_MXR_DEV_TEMPERATURE_UPDATE, dev)

        def on_bay_update(bay, val):
            ''' bay state of a device changed '''
            dispatcher_send(hass, SIGNAL_MXR_BAY_UPDATE, bay.dev.serial, bay.bay_name)

        def on_bay_linked(link):
            ''' bay link update '''
            for bay in link.bays:
                dispatcher_send(hass, SIGNAL_MXR_DEV_UPDATE, bay.dev)
                dispatcher_send(hass, SIGNAL_MXR_BAY_UPDATE, bay.dev.serial, bay.bay_name)

        def on_bay_unlinked(bay, serial, bay_name):
            ''' bay unlinked '''
            dispatcher_send(hass, SIGNAL_MXR_DEV_UPDATE, bay.dev)
            dispatcher_send(hass, SIGNAL_MXR_BAY_UPDATE, bay.dev.serial, bay.bay_name)
            #dispatcher_send(hass, SIGNAL_MXR_DEV_UPDATE, serial)
            dispatcher_send(hass, SIGNAL_MXR_BAY_UPDATE, serial, bay_name)
            # TODO look up and notify the other

        def on_link_status_changed(link):
            ''' link up/down '''
            for bay in link.bays:
                dispatcher_send(hass, SIGNAL_MXR_DEV_UPDATE, bay.dev)
                dispatcher_send(hass, SIGNAL_MXR_BAY_UPDATE, bay.dev.serial, bay.bay_name)

        mx = mxr.Remote()
        mx.set_cb_device_config_changed(on_device_config_changed)
        mx.set_cb_on_device_config_complete(on_device_config_complete)
        mx.set_cb_on_device_temperature_changed(on_device_temperature_changed)
        mx.set_cb_on_power_changed(on_bay_update)
        mx.set_cb_on_name_changed(on_bay_update)
        mx.set_cb_on_status_signal_detected_changed(on_bay_update)
        mx.set_cb_on_status_faulty_changed(on_bay_update)
        mx.set_cb_on_status_hidden_changed(on_bay_update)
        mx.set_cb_on_status_poe_powered_changed(on_bay_update)
        mx.set_cb_on_status_hdbt_connected_changed(on_bay_update)
        mx.set_cb_on_status_signal_type_changed(on_bay_update)
        mx.set_cb_on_status_hpd_detected_changed(on_bay_update)
        mx.set_cb_on_status_cec_detected_changed(on_bay_update)
        mx.set_cb_on_status_arc_changed(on_bay_update)
        mx.set_cb_on_volume_changed(on_bay_update)
        #mx.set_cb_on_key_pressed()
        mx.set_cb_on_video_source_changed(on_bay_update)
        mx.set_cb_on_audio_source_changed(on_bay_update)
        mx.set_cb_on_bay_linked(on_bay_linked)
        mx.set_cb_on_bay_unlinked(on_bay_unlinked)
        mx.set_cb_on_link_status_changed(on_link_status_changed)
        
        hass.async_create_task(mx.start_async())
        return mx

    hass.data[DOMAIN] = {
        'mxr': _mx_start_listening(hass),
        'devices': {},
        'config': config[DOMAIN],
    }

    if not hass.config_entries.async_entries(DOMAIN):
        # import devices that are defined in configuration.yaml
        for entry in config[DOMAIN]:
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": config_entries.SOURCE_IMPORT},
                    data={
                        "serial": entry["serial"],
                        "name": entry["name"],
                    },
                )
            )

    return True

async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry) -> bool:
    ''' set up a device that has been configured by the user '''
    if entry.unique_id is None:
        raise Exception("no unique id set up: %")
        entry.unique_id = entry.data[CONF_SERIAL]

    platform = EntityPlatform(
        hass=hass,
        logger=_LOGGER,
        domain=DOMAIN,
        platform_name=DOMAIN,
        platform=None,
        scan_interval=DEFAULT_SCAN_INTERVAL,
        entity_namespace=None,
    )
    platform.config_entry = entry

    mp = P8Device(hass, hass.data[DOMAIN]['mxr'], str(entry.unique_id), platform, entry.data['name'])
    hass.data[DOMAIN]['devices'][entry.unique_id] = {
        'device': mp,
        'mp_device': None,
        'sensors': False,
        'binary_sensors': False,
        'bays': {}
    }
    await platform.async_add_entities([mp])

    hass.async_create_task(hass.config_entries.async_forward_entry_setup(entry, SENSOR_DOMAIN))
    hass.async_create_task(hass.config_entries.async_forward_entry_setup(entry, BINARY_SENSOR_DOMAIN))
    hass.async_create_task(hass.config_entries.async_forward_entry_setup(entry, MEDIA_PLAYER_DOMAIN))

    return True

class P8Device(Entity):
    ''' pulse-eight device (matrix, splitter, amp, ...) '''

    def __init__(self, hass, mx, serial, platform, name=None):
        self.hass = hass
        self.serial = serial
        self.mx = mx
        self._platform = platform
        self._dev = None # set when mx_remote detects this device
        self._bays = {}
        self._bay_link_timeouts = {}
        self._added = False
        self._mp_registered = False
        self._sw_registered = False
        self._name = name if name is not None else serial
        self._add_entities = None
        async_dispatcher_connect(hass, SIGNAL_MXR_DEV_UPDATE, self._mxr_update)

    @property
    def dev(self):
        ''' mx_remote device instance for this device '''
        if self._dev is None:
            self._dev = self.mx.get_by_serial(self.serial)
        return self._dev

    @property
    def should_poll(self):
        return False

    @property
    def available(self):
        return (self.dev is not None) and self.dev.online

    async def async_added_to_hass(self) -> None:
        self._added = True
        await self._mxr_register_bays()

    async def mxr_register_bays(self):
        self._mp_registered = True
        await self._mxr_register_bays()

    async def _mxr_register_bays(self):
        ''' register the bays of this device as new media_player devices '''
        if self.dev is None or not self._mp_registered or not self._added:
            return False

        def source_value(dev, bay, param):
            vs = bay.video_source
            if vs is not None:
                return vs.user_name
            return STATE_UNKNOWN

        if self.hass.data[DOMAIN]['devices'][self.dev.serial]['mp_device'] is None:
            # register media_player for the device
            dev = P8MPDevice(self)
            self.hass.data[DOMAIN]['devices'][self.dev.serial]['mp_device'] = dev
            dispatcher_send(self.hass, SIGNAL_MXR_REGISTER, [dev])

        for _, bay in self.dev.bays.items():
            if (not bay.hidden) and (not bay.bay_name in self._bays.keys()):
                # only register bays that we don't know and that are not hidden
                nbay = []

                # wait for the link to come up for linked bays
                if bay.link_configured and not bay.link_connected:
                    if (not bay.bay_name in self._bay_link_timeouts):
                        self._bay_link_timeouts[bay.bay_name] = datetime.now()
                        continue
                    if (datetime.now() - self._bay_link_timeouts[bay.bay_name]).total_seconds() < 60:
                        # unit should send a hello within a minute if it's online
                        continue

                if bay.bay_name in self.hass.data[DOMAIN]['devices'][self.dev.serial]['bays'].keys():
                    continue

                if self.dev.is_video_matrix:
                    if bay.is_output:
                        nbay.append(P8MPVideoBayOutput(self, bay))
                        nbay.append(P8Sensor(self.hass, bay.dev, bay, None, "Source {}".format(bay.user_name), source_value, None, None))
                    else:
                        nbay.append(P8MPVideoBayInput(self, bay))
                elif self.dev.is_amp and bay.is_output: # ignore amp inputs
                    if (bay.bay >= bay.dev.amp_dolby_channels) or (bay.bay == 0):
                        nbay.append(P8MPAudioOutput(self, bay))

                if len(nbay) > 0:
                    self._bays[bay.bay_name] = nbay
                    self.hass.data[DOMAIN]['devices'][self.dev.serial]['bays'][bay.bay_name] = nbay[0]
                    if nbay[0].unique_id:
                        dispatcher_send(self.hass, "mxr_new_player", nbay)

    async def _mxr_update(self, dev):
        if isinstance(dev, str):
            if (dev != self.serial):
                return
        elif (dev.serial == self.serial):
            self._dev = dev
        else:
            return
        if self._added:
            await self._mxr_register_bays()
            self.async_write_ha_state()

    @property
    def name(self):
        return self._name

    @property
    def device_state_attributes(self):
        data = {}
        data['serial'] = self.serial
        dev = self.dev
        if dev is not None:
            data['model'] = dev.name
            data['version'] = dev.version
            data['ip'] = dev.address
            data['features'] = dev.features
            if dev.is_amp:
                data['type'] = 'amplifier'
            elif dev.is_video_matrix:
                data['type'] = 'video matrix'
            elif dev.is_audio_matrix:
                data['type'] = 'audio matrix'
            else:
                data['type'] = 'unknown'
            temperature = dev.temperature
            data['temperature'] = temperature if temperature is not None else STATE_UNKNOWN
        return data

    @property
    def device_info(self):
        info = {
            'identifiers': {
                ("mx_remote", self.serial)
             },
            'name': self.name,
            'manufacturer': 'Pulse-Eight',
        }
        dev = self.dev
        if dev is not None:
            info['sw_version'] = dev.version
            info['model'] = dev.name
        return info

    @property
    def unique_id(self):
        return self.serial

    @property
    def state(self):
        if (self.dev is None) or (self.dev.outputs is None):
            return STATE_UNKNOWN
        for _, bay in self.dev.outputs.items():
            if bay.powered_on:
                return STATE_ON
        return STATE_OFF

    @property
    def supported_features(self):
        return ()

