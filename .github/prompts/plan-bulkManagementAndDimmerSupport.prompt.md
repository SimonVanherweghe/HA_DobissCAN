# Plan: Bulk Light Management & Dimmer Support

This plan modernizes the integration with CRUD-based bulk light management, proper dimmer support with transitions, and alignment with the full Dobiss CAN protocol.

## Steps

1. **Implement new protocol layer** - Create new file `protocol.py` with the complete Dobiss protocol from `can-protocol.md`. Current implementation uses simplified protocol (`0x01FC0002`, 5-byte payload) but docs show 16-byte header + 8-byte body structure. Implement `send_toggle_action()` and `send_dim_action()` with proper command headers (`0xAF` prefix, module types `0x08`/`0x10`/`0x18`) and body structure (bytes for address, output, action, delays, value, softdim). Add `request_status()` method that returns parsed output states (0-1 for relays, 0-100 for dimmers).

2. **Replace config flow with CSV bulk input** - In `config_flow.py`, replace `async_step_light()` loop with single-step form accepting multi-line CSV text (`name,module,relay,type` where type=`relay`|`dimmer`|`0-10v`). Parse CSV, validate for duplicates and valid ranges (module 1-82, relay varies by type), convert to config data structure with `module_type` field added.

3. **Add options flow for CRUD operations** - Add `async_get_options_flow()` static method and `DobissOptionsFlowHandler` class to `config_flow.py`. Implement `async_step_init()` showing current lights list with action menu (add/edit/delete/export). Add `async_step_add()`, `async_step_edit()`, `async_step_delete()` for individual operations. Include `async_step_export()` to show CSV export of current config for backup/sharing.

4. **Update light entity for brightness and transitions** - In `light.py`, add `ColorMode.BRIGHTNESS` support for dimmer types. Add `_brightness` (0-255 HA scale), `_transition` duration state. Implement `brightness` property and `supported_features` including `SUPPORT_TRANSITION`. Update `async_turn_on()` to: convert HA brightness (0-255) to Dobiss scale (0-100), handle `ATTR_TRANSITION` by setting softdim byte, call new `protocol.send_dim_action()` with value and softdim parameters. Update `on_can_message_received()` to parse 8-byte body responses (byte 5 contains dim value 0-100).

5. **Refactor initialization and status polling** - Update `async_setup_entry()` in `light.py` to use new `protocol.request_status()` for initial state. Replace hardcoded module type with config-based `module_type` (`0x08`/`0x10`/`0x18`). Update CAN filters to match new protocol message IDs. Modify `async_update()` to request status using proper 16-byte command format with module type.

6. **Update constants and translations** - Add to `const.py`: `CONF_MODULE_TYPE`, module type constants (`MODULE_TYPE_RELAY=0x08`, `MODULE_TYPE_DIMMER=0x10`, `MODULE_TYPE_0_10V=0x18`), relay count limits per type. Update `translations/en.json` with CSV format help text, CRUD operation labels, and module type descriptions.

## Further Considerations

1. **Protocol migration strategy** - Current installs use old simplified protocol. Should we auto-detect and migrate, or require reconfiguration? **Recommend:** Add version field to config entries, attempt migration on load with fallback to old protocol if new fails, log warning to reconfigure.

2. **CSV error handling** - Malformed CSV could break setup. Add validation with clear error messages (line numbers, what's wrong). **Recommend:** Show preview table before submission with "looks correct?" confirmation step.

3. **Module type auto-detection** - Could query all module types (0x08/0x10/0x18) during status request to auto-discover. Would simplify setup but add delay. **Recommend:** Keep manual selection for faster setup, add optional "auto-detect" button in options flow.

4. **Softdim timing scale** - Protocol doc shows softdim byte but no scale explanation. Need to test: is it seconds, 100ms intervals, or arbitrary units? **Recommend:** Test with hardware, start with assumption 1 unit = 100ms, document actual behavior.

5. **Entity registry migration** - Changing unique_id format (to include module_type) would create duplicate entities. **Recommend:** Keep existing unique_id format `dobiss.{entry_id}.{module}.{relay}`, store module_type separately in entity attributes only.

6. **0-10V output support** - Protocol includes 0-10V analog outputs. Should we support these as lights or separate platform (sensor/number)? **Recommend:** Treat as dimmable lights initially (same as dimmers), evaluate separate platform later based on user needs.

## Key Protocol Clarifications

From the protocol documentation:

- **Brightness scale**: 0-100 (not 0-255), needs conversion from HA's 0-255 scale
- **Softdim**: Byte 6 controls transition speed (0xFF = disabled/instant)
- **Status response**: Returns 16 bytes with 1 byte per output (relays: 0-1, dimmers: 0-100)
- **Module types**: Must specify relay (0x08), dimmer (0x10), or 0-10V (0x18) in requests
- **Output ranges**: Relay 0x00-0x0B (12 outputs), Dimmer 0x00-0x03 (4 outputs), 0-10V 0x00-0x07 (8 outputs)

## Protocol Structure

### Command Header (16 bytes)

```
{ 0xAF, 0x02, 0xFF, outputAddress, 0x00, 0x00, 0x08, 0x01,
  0x08, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xAF }
```

### Command Body (8 bytes)

```
{ outputAddress, outputID, action, delayOn, delayOff, value, softdim, cond }
```

Where:

- **action**: 0x00=Off, 0x01=On, 0x02=Toggle
- **value**: 0x64 (100%) for toggle, or 0-100 for dim
- **softdim**: 0xFF=disabled (instant), or transition speed value
- **delayOn/delayOff**: 0xFF=disabled

### Status Request (16 bytes)

```
{ 0xAF, 0x01, moduleType, moduleAddress, 0x00, 0x00, 0x00,
  0x01, 0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xAF }
```

Response: 16 bytes with 1 byte per output (0-1 for relays, 0-100 for dimmers)
