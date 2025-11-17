import logging
from typing import Any, Dict, Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_LIGHTS, CONF_NAME
from homeassistant.helpers import selector

from .const import *
from .config_parser import parse_config_file, ConfigParseError, DobissOutput


_LOGGER = logging.getLogger(DOMAIN)
_LOGGER.setLevel(logging.DEBUG)


CAN = vol.Schema({
    vol.Optional(CONF_INTERFACE, default="socketcan"): cv.string,
    vol.Optional(CONF_CHANNEL, default="can0"): cv.string,
})

ENTRY = vol.Schema({
    vol.Required(CONF_NAME): cv.string,
    vol.Required(CONF_MODULE, default=1): cv.positive_int,
    vol.Required(CONF_RELAY, default=0): cv.positive_int,
    vol.Optional("add_another", default=True): cv.boolean,
})


class DobissCANConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """DobissCAN config flow."""

    def __init__(self) -> None:
        super().__init__()
        _LOGGER.warning("DobissCANConfigFlow 2")
        self.data: Dict[str, Any] = {}
    self.parsed_outputs: Optional[list[DobissOutput]] = None

    async def async_step_user(self, user_input=None):
        _LOGGER.warning("async_step_user %r %r", user_input, self.data)

        if user_input is not None:
            self.data.update(user_input)
            self.data[CONF_LIGHTS] = []
            return await self.async_step_import_method()

        return self.async_show_form(step_id="user", data_schema=CAN)
    async def async_step_import_method(self, user_input=None):
        """Ask user how they want to configure lights."""
        if user_input is not None:
            method = user_input.get("method")
            if method == "config_file":
                return await self.async_step_upload_config()
            else:
                # Manual entry
                return await self.async_step_light()
        
        return self.async_show_form(
            step_id="import_method",
            data_schema=vol.Schema({
                vol.Required("method", default="config_file"): vol.In({
                    "config_file": "Import from config.dobiss file (recommended)",
                    "manual": "Add lights manually"
                }),
            }),
        )
    
    async def async_step_upload_config(self, user_input=None):
        """Handle config.dobiss file upload."""
        errors = {}
        
        if user_input is not None:
            try:
                # Get the uploaded file path
                file_path = user_input.get("config_file")
                if not file_path:
                    errors["base"] = "no_file"
                else:
                    # Parse the config file
                    self.parsed_outputs = await self.hass.async_add_executor_job(
                        parse_config_file, file_path
                    )
                    
                    if not self.parsed_outputs:
                        errors["base"] = "no_outputs"
                    else:
                        _LOGGER.info(f"Parsed {len(self.parsed_outputs)} outputs from config.dobiss")
                        return await self.async_step_select_outputs()
            
            except ConfigParseError as err:
                _LOGGER.error(f"Failed to parse config.dobiss: {err}")
                errors["base"] = "parse_error"
            except Exception as err:
                _LOGGER.error(f"Unexpected error parsing config.dobiss: {err}")
                errors["base"] = "unknown"
        
        return self.async_show_form(
            step_id="upload_config",
            data_schema=vol.Schema({
                vol.Required("config_file"): selector.FileSelector(
                    selector.FileSelectorConfig(accept=".dobiss,application/xml,text/xml")
                ),
            }),
            errors=errors,
            description_placeholders={
                "location": "Windows: C:\\ProgramData\\Dobiss\\Ambiance\\config.dobiss"
            },
        )
    
    async def async_step_select_outputs(self, user_input=None):
        """Let user select which outputs to import."""
        if user_input is not None:
            selected_keys = user_input.get("selected", [])
            
            # Convert selections to light configs
            for output in self.parsed_outputs or []:
                key = f"{output.module}_{output.output_id}"
                if key in selected_keys:
                    self.data[CONF_LIGHTS].append({
                        CONF_NAME: output.name,
                        CONF_MODULE: output.module,
                        CONF_RELAY: output.output_id,
                        CONF_MODULE_TYPE: output.module_type,
                        CONF_AREA: output.area,
                    })
            
            num_lights = len(self.data[CONF_LIGHTS])
            return self.async_create_entry(
                title=f"Dobiss ({num_lights} lights)",
                data=self.data
            )
        
        # Build options for multi-select
        if not self.parsed_outputs:
            return await self.async_step_upload_config()
        
        options = {}
        for output in self.parsed_outputs:
            key = f"{output.module}_{output.output_id}"
            area_str = f" [{output.area}]" if output.area else ""
            options[key] = f"{output.name} (M{output.module} O{output.output_id} {output.output_type}){area_str}"
        
        # Pre-select all by default
        default_selected = list(options.keys())
        
        return self.async_show_form(
            step_id="select_outputs",
            data_schema=vol.Schema({
                vol.Required("selected", default=default_selected): cv.multi_select(options),
            }),
            description_placeholders={
                "count": str(len(self.parsed_outputs))
            },
        )
    

    async def async_step_light(self, user_input=None):
        _LOGGER.warning("async_step_light %r %r", user_input, self.data)

        if user_input is not None:
            cont = user_input.pop("add_another", False)

            self.data[CONF_LIGHTS].append(user_input)

            if not cont:
                # User is done adding lights, create the config entry.
                num_lights = len(self.data[CONF_LIGHTS])
                return self.async_create_entry(
                    title=f"Dobiss ({num_lights} lights)",
                    data=self.data
                )

        return self.async_show_form(step_id="light", data_schema=ENTRY)
