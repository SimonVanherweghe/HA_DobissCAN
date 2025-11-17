import logging
import os
from typing import Any, Dict, Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
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

    def _resolve_file_path(self, value: str) -> str:
        """Resolve a FileSelector value or upload ID to an absolute path.

        - Absolute path: returned as-is
        - Relative path: resolved against HA config directory
        - Upload ID (hash-like string): mapped to .storage/uploads/<id>
        """
        if not value:
            return value
        
        _LOGGER.debug(f"Resolving file path for value: {value}")
        
        # Absolute path
        if os.path.isabs(value):
            _LOGGER.debug(f"Value is absolute path: {value}")
            return value
        
        # Relative to config dir
        candidate = self.hass.config.path(value)
        if os.path.exists(candidate):
            _LOGGER.debug(f"Found as relative path: {candidate}")
            return candidate
        
        # Try as direct upload ID first
        upload_path = self.hass.config.path(".storage", "uploads", value)
        if os.path.exists(upload_path):
            _LOGGER.debug(f"Found upload at: {upload_path}")
            return upload_path
        
        # Also check /media/uploads (alternative upload location)
        media_path = self.hass.config.path("media", "uploads", value)
        if os.path.exists(media_path):
            _LOGGER.debug(f"Found in media uploads: {media_path}")
            return media_path
        
        # Log what we tried
        _LOGGER.warning(f"File not found. Tried: {upload_path}, {media_path}")
        return upload_path  # Return first attempt even if not found, for error reporting

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
                # Get the uploaded file ID
                file_id = user_input.get("config_file")
                _LOGGER.debug(f"Upload config received file ID: {file_id}")
                
                if not file_id:
                    errors["base"] = "no_file"
                else:
                    # Read file content directly using the file_upload integration
                    try:
                        from homeassistant.components.file_upload import process_uploaded_file
                        
                        # Process the uploaded file and get the content
                        with process_uploaded_file(self.hass, file_id) as file_path:
                            _LOGGER.debug(f"Processing uploaded file at: {file_path}")
                            # Parse the config file
                            self.parsed_outputs = await self.hass.async_add_executor_job(
                                parse_config_file, file_path
                            )
                            
                            if not self.parsed_outputs:
                                errors["base"] = "no_outputs"
                            else:
                                _LOGGER.info(f"Parsed {len(self.parsed_outputs)} outputs from config.dobiss")
                                return await self.async_step_select_outputs()
                    
                    except ImportError:
                        # Fallback for older HA versions - try direct path resolution
                        _LOGGER.warning("file_upload component not available, trying direct path")
                        file_path = self._resolve_file_path(file_id)
                        if os.path.exists(file_path):
                            self.parsed_outputs = await self.hass.async_add_executor_job(
                                parse_config_file, file_path
                            )
                            if not self.parsed_outputs:
                                errors["base"] = "no_outputs"
                            else:
                                _LOGGER.info(f"Parsed {len(self.parsed_outputs)} outputs from config.dobiss")
                                return await self.async_step_select_outputs()
                        else:
                            errors["base"] = "no_file"
            
            except ConfigParseError as err:
                _LOGGER.error(f"Failed to parse config.dobiss: {err}")
                errors["base"] = "parse_error"
            except Exception as err:
                _LOGGER.error(f"Unexpected error parsing config.dobiss: {err}", exc_info=True)
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


    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return DobissOptionsFlowHandler(config_entry)


class DobissOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Dobiss options flow for managing lights (CRUD)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry
        # Work on a copy so we can stage changes
        self._data: Dict[str, Any] = dict(config_entry.data)
        self._lights: list[dict[str, Any]] = list(self._data.get(CONF_LIGHTS, []))
        self._edit_index: Optional[int] = None
        self._parsed_outputs: Optional[list[DobissOutput]] = None

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            action = user_input.get("action")
            if action == "add":
                return await self.async_step_add()
            if action == "edit":
                return await self.async_step_pick_edit()
            if action == "delete":
                return await self.async_step_delete()
            if action == "reimport":
                return await self.async_step_reimport_upload()
            if action == "export":
                return await self.async_step_export()
            if action == "save":
                # Persist changes back into entry.data (not options) so setup keeps working
                new_data = dict(self._data)
                new_data[CONF_LIGHTS] = self._lights
                self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
                return self.async_create_entry(title="", data={})

        actions = {
            "add": "Add light",
            "edit": "Edit light",
            "delete": "Delete lights",
            "reimport": "Re-import from config.dobiss",
            "export": "Export CSV",
            "save": "Save & exit",
        }

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("action"): vol.In(actions)
            }),
            description_placeholders={
                "count": str(len(self._lights))
            }
        )

    async def async_step_add(self, user_input=None):
        if user_input is not None:
            self._lights.append(user_input)
            return await self.async_step_init()

        schema = vol.Schema({
            vol.Required(CONF_NAME): cv.string,
            vol.Required(CONF_MODULE, default=1): cv.positive_int,
            vol.Required(CONF_RELAY, default=0): cv.positive_int,
            vol.Optional(CONF_MODULE_TYPE, default=MODULE_TYPE_RELAY): vol.In({
                MODULE_TYPE_RELAY: "Relay",
                MODULE_TYPE_DIMMER: "Dimmer",
                MODULE_TYPE_0_10V: "0-10V",
            }),
            vol.Optional(CONF_AREA): cv.string,
        })
        return self.async_show_form(step_id="add", data_schema=schema)

    async def async_step_pick_edit(self, user_input=None):
        if user_input is not None:
            # user_input contains key identifying index
            sel = user_input.get("light")
            if sel is not None:
                try:
                    self._edit_index = int(sel.split(":", 1)[0])
                except Exception:
                    self._edit_index = None
            if self._edit_index is None or self._edit_index < 0 or self._edit_index >= len(self._lights):
                return await self.async_step_init()
            return await self.async_step_edit()

        options = {}
        for idx, l in enumerate(self._lights):
            label = f"{idx}: {l.get(CONF_NAME, 'Unnamed')} (M{l.get(CONF_MODULE)} O{l.get(CONF_RELAY)})"
            options[str(idx) + ": "+ l.get(CONF_NAME, 'Unnamed')] = label
        # Use keys and labels the same due to HA selector constraints
        options = {k: v for k, v in options.items()}
        return self.async_show_form(
            step_id="pick_edit",
            data_schema=vol.Schema({
                vol.Required("light"): vol.In(options)
            })
        )

    async def async_step_edit(self, user_input=None):
        if self._edit_index is None or self._edit_index >= len(self._lights):
            return await self.async_step_init()

        current = self._lights[self._edit_index]
        if user_input is not None:
            self._lights[self._edit_index] = user_input
            self._edit_index = None
            return await self.async_step_init()

        schema = vol.Schema({
            vol.Required(CONF_NAME, default=current.get(CONF_NAME)): cv.string,
            vol.Required(CONF_MODULE, default=current.get(CONF_MODULE, 1)): cv.positive_int,
            vol.Required(CONF_RELAY, default=current.get(CONF_RELAY, 0)): cv.positive_int,
            vol.Optional(CONF_MODULE_TYPE, default=current.get(CONF_MODULE_TYPE, MODULE_TYPE_RELAY)): vol.In({
                MODULE_TYPE_RELAY: "Relay",
                MODULE_TYPE_DIMMER: "Dimmer",
                MODULE_TYPE_0_10V: "0-10V",
            }),
            vol.Optional(CONF_AREA, default=current.get(CONF_AREA, "")): cv.string,
        })
        return self.async_show_form(step_id="edit", data_schema=schema)

    async def async_step_delete(self, user_input=None):
        if user_input is not None:
            selected = user_input.get("selected", [])
            # Build map of indices
            index_map = {}
            for idx, l in enumerate(self._lights):
                key = f"{idx}: {l.get(CONF_NAME, 'Unnamed')} (M{l.get(CONF_MODULE)} O{l.get(CONF_RELAY)})"
                index_map[key] = idx
            to_delete = sorted((index_map[k] for k in selected if k in index_map), reverse=True)
            for idx in to_delete:
                self._lights.pop(idx)
            return await self.async_step_init()

        options = {}
        for idx, l in enumerate(self._lights):
            key = f"{idx}: {l.get(CONF_NAME, 'Unnamed')} (M{l.get(CONF_MODULE)} O{l.get(CONF_RELAY)})"
            options[key] = key
        return self.async_show_form(
            step_id="delete",
            data_schema=vol.Schema({
                vol.Required("selected", default=[]): cv.multi_select(options)
            })
        )

    async def async_step_reimport_upload(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                file_id = user_input.get("config_file")
                replace_all = user_input.get("replace_all", False)
                
                if not file_id:
                    errors["base"] = "no_file"
                else:
                    try:
                        from homeassistant.components.file_upload import process_uploaded_file
                        
                        with process_uploaded_file(self.hass, file_id) as file_path:
                            self._parsed_outputs = await self.hass.async_add_executor_job(parse_config_file, file_path)
                            
                            if not self._parsed_outputs:
                                errors["base"] = "no_outputs"
                            else:
                                self._replace_all = replace_all
                                return await self.async_step_reimport_select()
                    
                    except ImportError:
                        _LOGGER.warning("file_upload component not available, trying direct path")
                        file_path = self._resolve_file_path(file_id)
                        if os.path.exists(file_path):
                            self._parsed_outputs = await self.hass.async_add_executor_job(parse_config_file, file_path)
                            if not self._parsed_outputs:
                                errors["base"] = "no_outputs"
                            else:
                                self._replace_all = replace_all
                                return await self.async_step_reimport_select()
                        else:
                            errors["base"] = "no_file"
                            
            except ConfigParseError:
                errors["base"] = "parse_error"
            except Exception as err:
                _LOGGER.error(f"Unexpected error in reimport: {err}", exc_info=True)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reimport_upload",
            data_schema=vol.Schema({
                vol.Required("config_file"): selector.FileSelector(
                    selector.FileSelectorConfig(accept=".dobiss,application/xml,text/xml")
                ),
                vol.Optional("replace_all", default=False): cv.boolean,
            }),
        )

    async def async_step_reimport_select(self, user_input=None):
        if user_input is not None:
            selected = user_input.get("selected", [])
            if getattr(self, "_replace_all", False):
                self._lights = []
            # Merge by module+relay
            existing_by_key = { (l[CONF_MODULE], l[CONF_RELAY]): i for i, l in enumerate(self._lights) }
            for out in (self._parsed_outputs or []):
                key = f"{out.module}_{out.output_id}"
                if key not in selected:
                    continue
                ldata = {
                    CONF_NAME: out.name,
                    CONF_MODULE: out.module,
                    CONF_RELAY: out.output_id,
                    CONF_MODULE_TYPE: out.module_type,
                    CONF_AREA: out.area,
                }
                tup = (out.module, out.output_id)
                if tup in existing_by_key:
                    self._lights[existing_by_key[tup]] = ldata
                else:
                    self._lights.append(ldata)
            return await self.async_step_init()

        options = {}
        for out in (self._parsed_outputs or []):
            key = f"{out.module}_{out.output_id}"
            options[key] = f"{out.name} (M{out.module} O{out.output_id} {out.output_type})"
        default = list(options.keys())
        return self.async_show_form(
            step_id="reimport_select",
            data_schema=vol.Schema({
                vol.Required("selected", default=default): cv.multi_select(options)
            })
        )

    async def async_step_export(self, user_input=None):
        # Generate CSV
        lines = ["name,module,relay,module_type,area"]
        for l in self._lights:
            lines.append(
                f"{l.get(CONF_NAME,'')},{l.get(CONF_MODULE,'')},{l.get(CONF_RELAY,'')},{l.get(CONF_MODULE_TYPE,'')},{l.get(CONF_AREA,'')}"
            )
        csv_text = "\n".join(lines)

        if user_input is not None:
            # Just go back to init
            return await self.async_step_init()

        schema = vol.Schema({
            vol.Required("csv", default=csv_text): cv.string
        })
        return self.async_show_form(
            step_id="export", data_schema=schema, description_placeholders={"count": str(len(self._lights))}
        )
