# Plan: Config.dobiss Import & Dimmer Support

This plan modernizes the integration with `config.dobiss` file import as the primary configuration method, adds CRUD-based management, and implements full dimmer support with transitions.

## Steps

1. **Implement config.dobiss XML parser** - Create new file `config_parser.py` with `parse_config_file()` function. Use `xml.etree.ElementTree` to parse Microsoft DataContract XML with proper namespace handling. Build ID map for resolving `z:Id`/`z:Ref` cross-references. Extract all outputs with: module address (from `Parent/Address`), module type (from `Parent/Type`: 8=relay, 16=dimmer, 24=0-10v), output ID (from `ID`), name (from `_displayName`), area/room (from `_group/DisplayName`). Return list of `DobissOutput` dataclass objects. Handle parsing errors gracefully with informative messages.

2. **Add config.dobiss import to config flow** - In `config_flow.py`, add new `async_step_import_method()` after CAN settings step, offering "Import from config.dobiss" (recommended) or "Manual entry". For import path: add `async_step_upload_config()` with file selector, parse uploaded XML using `config_parser`, store parsed outputs. Add `async_step_select_outputs()` showing table/multi-select of all discovered outputs with columns: name, module, output, type, area. Allow filtering by room/type. Convert selected outputs to lights config data structure with proper `module_type` field.

3. **Add options flow for CRUD operations** - Add `async_get_options_flow()` static method and `DobissOptionsFlowHandler` class to `config_flow.py`. Implement `async_step_init()` showing current lights list with actions: add single light, re-import from config.dobiss, edit existing light, delete light, export to CSV. Add `async_step_add()` for single light form entry. Add `async_step_edit()` with entity selector and update form. Add `async_step_delete()` with confirmation. Add `async_step_reimport()` to refresh from updated config.dobiss file (preserving entity IDs where module+output match).

4. **Implement protocol layer with dimmer support** - Create new file `protocol.py` with CAN protocol functions. Implement `build_toggle_command(module, output_id, action)` returning 8-byte payload: `[module, output_id, action, 0xFF, 0xFF, 0x64, 0xFF, 0xFF]` where action is 0x00=off, 0x01=on, 0x02=toggle. Implement `build_dim_command(module, output_id, brightness, transition)` with payload: `[module, output_id, 0x01, 0xFF, 0xFF, brightness_value, softdim_value, 0xFF]` where brightness_value is 0-100 (convert from HA's 0-255), softdim_value is transition duration (0xFF=instant, or calculated from seconds). Add `parse_status_response(data)` to extract state from reply messages.

5. **Update light entity for brightness and transitions** - In `light.py`, add conditional `ColorMode.BRIGHTNESS` support based on `module_type` from config (type 16 or 24 = dimmable). Add `_brightness` state (0-255 HA scale), `_module_type` attribute. Implement `brightness` property returning `_brightness` for dimmers, `None` for relays. Add `SUPPORT_TRANSITION` to `supported_features` for dimmers. Update `async_turn_on()`: if `ATTR_BRIGHTNESS` in kwargs, convert to 0-100 scale, extract transition duration from `ATTR_TRANSITION`, call `protocol.build_dim_command()`, else call `protocol.build_toggle_command()`. Update `on_can_message_received()`: for SET replies (0x0002FF01), parse byte 5 as brightness value (0-100), convert to HA scale (0-255), update `_brightness` state.

6. **Update initialization and CAN filters** - Update `async_setup_entry()` in `light.py` to pass `module_type` to each `DobissLight` instance from config data. Keep existing CAN filters (0x0002FF01 for SET replies, 0x01FDFF01 for GET replies) as they match observed protocol. Update `__init__()` to store `module_type`, set color mode and supported features based on type. Update unique_id format to remain `dobiss.{entry_id}.{module}.{relay}` for backward compatibility.

7. **Update constants, translations, and documentation** - Add to `const.py`: `CONF_MODULE_TYPE`, `CONF_AREA`, module type constants (`MODULE_TYPE_RELAY=8`, `MODULE_TYPE_DIMMER=16`, `MODULE_TYPE_0_10V=24`). Update `translations/en.json` with: import method selection text, file upload instructions, output selection table headers, CRUD action labels, dimmer/transition help text. Update `README.md` with config.dobiss import instructions (where to find file on Windows: `C:\ProgramData\Dobiss\Ambiance\config.dobiss`). Update `.github/copilot-instructions.md` with parser details and new config flow structure.

## Further Considerations

1. **XML version compatibility** - Config.dobiss format may vary between Dobiss Ambiance software versions. **Recommend:** Add version detection in parser, log warnings for unknown versions, parse conservatively to handle missing fields gracefully. Test with multiple config file versions if available.

2. **Entity ID preservation during re-import** - When user updates Dobiss config and re-imports, want to preserve existing HA entity IDs where module+output match. **Recommend:** In options flow re-import, match by module+output, only add/remove changed entities, update names/types for existing ones. Show diff preview before applying.

3. **Partial selection workflow** - User may have 100+ outputs but only want 20 in HA. **Recommend:** Add room/type filter checkboxes above selection table, "Select All/None" buttons, search/filter box. Remember previous selections if re-importing.

4. **Softdim timing scale** - Protocol doc shows softdim byte but doesn't specify scale (seconds? 100ms units?). **Recommend:** Test with actual dimmer hardware using different values (1, 2, 5, 10, 50, 100, 255). Document observed behavior. Start with assumption: 0xFF=instant, 0=slowest, linear scale.

5. **Area/room integration** - Config.dobiss provides room groupings. Could map to HA device `suggested_area`. **Recommend:** Add `suggested_area` to device_info using parsed area name. Helps with HA area assignment, voice assistants, dashboards.

6. **Fallback to manual entry** - Parser may fail on corrupted/old config files. **Recommend:** Always offer manual entry as alternative. If parse fails, show error with "Continue with manual entry?" option. Don't block setup on parse failure.

7. **Mood/scene import** - Config.dobiss contains mood definitions (multi-output scenes). Could import as HA scenes. **Recommend:** Phase 2 feature. Parse moods, create HA scenes, associate with Dobiss buttons. Requires more complex parsing and scene entity creation.

## Key Protocol Clarifications

From candump analysis and protocol documentation:

### Message Format (Observed & Verified)
- **SET command ID**: `0x01FC0002 | (module << 8)` → Examples: `01FC0102`, `01FC0202`, `01FC0302`
- **SET reply ID**: `0x0002FF01` with 3-byte payload: `[module, output, state]`
- **GET command ID**: `0x01FCFF01` with 2-byte payload: `[module, output]`
- **GET reply ID**: `0x01FDFF01` with 1-byte payload: `[state]` (no module/output info - requires lock)

### SET Command Payload (8 bytes)
```
[module, output_id, action, delay_on, delay_off, value, softdim, cond]
```
Where:
- **action**: 0x00=Off, 0x01=On, 0x02=Toggle
- **delay_on/delay_off**: 0xFF=disabled, or delay value
- **value**: 0x64 (100) for toggle/on, or 0-100 for specific brightness
- **softdim**: 0xFF=instant, or transition speed value
- **cond**: 0xFF (not used)

### Observed Dimmer Commands
From candump log:
```
01FC0202 [8] 02 00 01 03 FF 32 FF FF  → Module 2, Output 0, ON, brightness=50 (0x32)
01FC0202 [8] 02 02 01 02 FF 4B FF FF  → Module 2, Output 2, ON, brightness=75 (0x4B)
01FC0302 [8] 03 07 01 FF FF 64 FF FF  → Module 3, Output 7, ON, brightness=100 (0x64)
```

### Config.dobiss Structure
```xml
<Output i:type="OutputRelais|OutputDim|Output0To10V">
  <ID>0-11</ID>                    <!-- Output number (0-indexed) -->
  <Parent>
    <Address>1-82</Address>        <!-- Module address (1-indexed) -->
    <Type>8|16|24</Type>          <!-- 8=Relay, 16=Dimmer, 24=0-10V -->
  </Parent>
  <_displayName>living led</_displayName>
  <_group>
    <DisplayName>Gelijkvloers</DisplayName>  <!-- Room/area -->
  </_group>
</Output>
```

### Module Specifications
- **Relay (Type 8)**: 12 outputs (0-11), on/off only
- **Dimmer (Type 16)**: 4 outputs (0-3), 0-100% brightness
- **0-10V (Type 24)**: 8 outputs (0-7), 0-100% analog control

### Brightness Scale Conversion
- **Dobiss protocol**: 0-100 (decimal)
- **Home Assistant**: 0-255 (standard)
- **Conversion**: `ha_brightness = dobiss_value * 255 / 100`
- **Reverse**: `dobiss_value = ha_brightness * 100 / 255`
