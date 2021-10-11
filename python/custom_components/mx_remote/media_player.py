""" Support for Pulse-Eight Video Matrix Switches """
from .const import *
from mx_remote.proto.const import *

from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv, entity_platform, service
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.typing import (
    HomeAssistantType,
    ConfigType
)
import voluptuous as vol
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry, async_add_entities) -> bool:
    @callback
    def async_add_player(player):
        if player[0].serial == entry.unique_id:
            async_add_entities(player)

    # register services
    platform = entity_platform.current_platform.get()
    platform.async_register_entity_service(
            SERVICE_SET_ROUTE,
            {
                vol.Required('source'): cv.string,
                vol.Optional('power'): cv.boolean,
            },
            "async_select_source",
            [SUPPORT_SELECT_SOURCE]
    )
    platform.async_register_entity_service(
            SERVICE_MUTE,
            {
                vol.Required('mute'): cv.boolean,
            },
            "async_mute_volume",
            [SUPPORT_VOLUME_MUTE]
    )
    platform.async_register_entity_service(
            SERVICE_SET_VOLUME,
            {
                vol.Required('volume'): cv.small_float,
            },
            "async_set_volume_level",
            [SUPPORT_VOLUME_SET]
    )

    async_dispatcher_connect(hass, SIGNAL_MXR_REGISTER, async_add_player)
    await hass.data[DOMAIN]['devices'][entry.unique_id]['device'].mxr_register_bays()
    return True

class P8MPBayBase(MediaPlayerEntity):
    ''' base class for media bays '''
    def __init__(self, dev, mx_bay):
        self.dev = dev
        self.hass = dev.hass
        self.mx_bay = mx_bay
        async_dispatcher_connect(self.hass, SIGNAL_MXR_BAY_UPDATE, self._mxr_update)

    async def _mxr_update(self, serial, bay_name):
        if (self.entity_id is not None) and (bay_name == self.mx_bay.bay_name) and (serial == self.mx_bay.dev.serial):
            self.async_write_ha_state()

    @property
    def mx_dev(self):
        return self.dev.dev

    @property
    def available(self):
        if self.dev is not None:
            return False
        return self.mx_bay.available

    @property
    def should_poll(self):
        return False

    @property
    def name(self):
        return "{} {}".format(self.mx_bay.mode, self.mx_bay.user_name)

    @property
    def serial(self):
        return self.dev.serial

    @property
    def device_state_attributes(self):
        return {
            'serial': self.dev.serial,
            'features': self.mx_bay.features,
        }

    @property
    def device_info(self):
        info = {
            'identifiers': {
                (MEDIA_PLAYER_DOMAIN, DOMAIN, self.dev.serial, self.mx_bay.bay_name)
             },
            'name': self.name,
            'manufacturer': 'Pulse-Eight',
            'via_device': (DOMAIN, self.dev.serial),
        }
        dev = self.mx_dev
        if dev is not None:
            info['sw_version'] = dev.version
            info['model'] = dev.name
        return info

    @property
    def unique_id(self):
        return "{} {}".format(self.dev.serial, self.mx_bay.bay_name)

    @property
    def available(self):
        return self.mx_dev is not None

    @property
    def state(self):
        return self.mx_bay.power_status

    @property
    def supported_features(self):
        raise Exception("you must override this")

    async def async_set_volume_level(self, volume):
        return await self.mx_bay.volume_set(int(volume * 100))

    async def async_volume_up(self):
        return await self.mx_bay.volume_up()

    async def async_volume_down(self):
        return await self.mx_bay.volume_down()

    async def async_mute_volume(self, mute):
        return await self.mx_bay.mute_set(mute)

    @property
    def device_state_attributes(self):
        return {
            'serial': self.dev.serial,
            'bay': self.mx_bay.bay_name,
            'features': self.mx_bay.features,
        }

class P8MPVideoBayBase(P8MPBayBase):
    @property
    def name(self):
        mode = self.mx_bay.mode
        if mode == self.mx_bay.user_name[0:len(mode)]:
            return "Video {}".format(self.mx_bay.user_name)
        return "Video {} {}".format(self.mx_bay.mode, self.mx_bay.user_name)

    @property
    def device_state_attributes(self):
        data = P8MPBayBase.device_state_attributes.fget(self)
        data['signal'] = self.mx_bay.signal_detected
        data['signal_type'] = self.mx_bay.signal_type
        data['cec'] = self.mx_bay.cec_detected
        if self.mx_bay.is_hdbaset:
            data['hbaset_link'] = self.mx_bay.hdbt_connected
            data['hbaset_poe'] = self.mx_bay.poe_powered
        return data

    @property
    def state(self):
        return self.mx_bay.power_status if self.available else STATE_OFF

    async def async_turn_on(self):
        return await self.mx_bay.power_on()

    async def async_turn_off(self):
        return await self.mx_bay.power_off()

    async def async_media_play(self):
        bay = self.mx_bay
        if bay.is_output:
            bay = bay.video_source
        return await bay.send_key(RCKey.KEY_PLAY.value)

    async def async_media_pause(self):
        bay = self.mx_bay
        if bay.is_output:
            bay = bay.video_source
        return await bay.send_key(RCKey.KEY_PAUSE.value)

    async def async_media_stop(self):
        bay = self.mx_bay
        if bay.is_output:
            bay = bay.video_source
        return await bay.send_key(RCKey.KEY_STOP.value)

class P8MPVideoBayInput(P8MPVideoBayBase):
    @property
    def supported_features(self):
        return SUPPORT_BAY_VIDEO_INPUT

class P8MPVideoBayOutput(P8MPVideoBayBase):
    def __init__(self, dev, mx_bay):
        P8MPBayBase.__init__(self, dev, mx_bay)

    @property
    def supported_features(self):
        if self.mx_bay.link_configured and self.mx_bay.link.is_audio:
            return SUPPORT_BAY_VIDEO_OUTPUT_AMP
        return SUPPORT_BAY_VIDEO_OUTPUT

    @property
    def device_state_attributes(self):
        data = P8MPVideoBayBase.device_state_attributes.fget(self)
        data['hotplug'] = self.mx_bay.hpd_detected
        if self.mx_bay.is_output:
            data['source'] = self.source
        if self.mx_dev.supports_arc:
            data['arc'] = self.mx_bay.arc
        data['muted'] = self.is_volume_muted
        data['volume'] = self.volume_level
        return data

    @property
    def source(self):
        vs = self.mx_bay.video_source
        if vs is not None:
            return vs.user_name
        return STATE_UNKNOWN

    @property
    def source_list(self):
        if not self.available:
            return []
        tmp = [bay.user_name for _, bay in self.mx_dev.inputs.items()]
        return tmp

    @property
    def volume_level(self):
        volume = self.mx_bay.volume
        return volume / 100.0 if volume is not None else STATE_UNKNOWN

    @property
    def is_volume_muted(self):
        muted = self.mx_bay.muted
        return muted if muted is not None else STATE_UNKNOWN

    async def async_select_source(self, source:str, power:bool=True):
        return await self.mx_bay.select_video_source_by_user_name(source, power)

class P8MPAudioOutput(P8MPBayBase):
    @property
    def name(self):
        return "Audio {} {}".format(self.mx_bay.mode, self.mx_bay.user_name)

    @property
    def supported_features(self):
        return SUPPORT_BAY_AUDIO_OUTPUT

    @property
    def state(self):
        if self.mx_bay.muted:
            return STATE_OFF
        return STATE_ON

    @property
    def volume_level(self):
        volume = self.mx_bay.volume
        return volume / 100.0 if volume is not None else STATE_UNKNOWN

    @property
    def is_volume_muted(self):
        muted = self.mx_bay.muted
        return muted if muted is not None else STATE_UNKNOWN

    async def async_turn_on(self):
        return await self.async_mute_volume(False)

    async def async_turn_off(self):
        return await self.async_mute_volume(True)

class P8MPDevice(MediaPlayerEntity):
    ''' pulse-eight device (matrix, splitter, amp, ...) '''

    def __init__(self, main_entity):
        self.main_entity = main_entity

    @property
    def dev(self):
        ''' mx_remote device instance for this device '''
        return self.main_entity.dev

    @property
    def should_poll(self):
        return False

    @property
    def available(self):
        return (self.dev is not None) and self.dev.online

    @property
    def name(self):
        return self.main_entity.name

    @property
    def serial(self):
        return self.main_entity.serial

    @property
    def device_state_attributes(self):
        return self.main_entity.device_state_attributes

    @property
    def device_info(self):
        info = {
            'identifiers': {
                (MEDIA_PLAYER_DOMAIN, DOMAIN, self.serial)
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
        return "{} media_player".format(self.serial)

    @property
    def state(self):
        if (self.dev is None) or (self.dev.outputs is None):
            return STATE_UNKNOWN
        for _, bay in self.dev.outputs.items():
            if bay.powered_on:
                return STATE_ON
        return STATE_OFF

    @property
    def source(self):
        for _, bay in self.dev.outputs.items():
            if bay.powered_on:
                inp = bay.video_source
                if inp is not None:
                    return inp.user_name
        return STATE_UNKNOWN

    @property
    def source_list(self):
        if not self.available:
            return []
        tmp = [bay.user_name for _, bay in self.dev.inputs.items()]
        return tmp

    async def async_turn_on(self):
        #tasks = []
        #for _, bay in self.dev.outputs.items():
        #    await output.set_power(True)
        #    append(tasks, self.async_update_ha_state())
        #await asyncio.wait(tasks)
        return True

    async def async_turn_off(self):
        #tasks = []
        #for _, bay in self.dev.outputs.items():
        #    await output.set_power(False)
        #    append(tasks, self.async_update_ha_state())
        #await asyncio.wait(tasks)
        return True

    @property
    def supported_features(self):
        return SUPPORT_P8MATRIX

