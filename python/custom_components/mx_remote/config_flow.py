import logging
from typing import Any, Dict, Optional
from homeassistant import config_entries
from homeassistant.helpers import (
    config_entry_flow,
    discovery
)
from homeassistant.const import (
    CONF_NAME,
)
import mx_remote as mxr
from .const import DOMAIN, CONF_SERIAL

_LOGGER = logging.getLogger(__name__)

class MXRConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    def __init__(self):
        self.dev = None
        self.name = None

    async def async_step_mx_remote(self, dev: mxr.remote.Device) -> Dict[str, Any]:
        ''' device detected by mx_remote '''

        # serial is unique for production units
        await self.async_set_unique_id(dev.serial)
        self._abort_if_unique_id_configured()

        # show new device found entry
        self.dev = dev
        self.name = '{} {}'.format(dev.name, dev.serial)
        self.context.update({"title_placeholders": {'name': self.name}})
        return await self.async_step_user()

    async def async_step_user(self, user_input: Optional[Dict] = None) -> Dict[str, Any]:
        ''' new device found entry clicked '''

        if user_input is None:
            # user didn't click accept yet
            return self.async_show_form(
                step_id = "user",
                description_placeholders = {
                    'name': self.name,
                },
                errors={},
            )

        # create a new config entry
        config = {
            CONF_SERIAL: self.dev.serial,
            CONF_NAME: self.name,
        }
        return self.async_create_entry(
            title=self.name,
            data=config,
        )

    async def async_step_import(self, info):
        ''' entry imported from configuration.yaml '''

        serial = info.get("serial")
        name = info.get("name")
        await self.async_set_unique_id(serial)
        config = {
            CONF_SERIAL: serial,
            CONF_NAME: name,
        }
        self._abort_if_unique_id_configured(
            updates=config,
        )
        return self.async_create_entry(
            title="{} (import from configuration.yaml)".format(serial),
            data=config,
        )


