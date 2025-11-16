# Copilot Instructions for HA_DobissCAN

## Project Overview

This is a Home Assistant custom component that integrates Dobiss home automation systems via CAN bus communication. It provides local push control of Dobiss modules (currently lights only) using the `python-can` library at 125kbit/s.

## Architecture

### Core Components

- **`__init__.py`**: Entry point that stores config data in `hass.data[DOMAIN][entry_id]` and forwards setup to the light platform
- **`config_flow.py`**: Multi-step UI config flow (CAN settings → add multiple lights iteratively)
- **`light.py`**: Main implementation with CAN bus communication, state management, and entity creation
- **`const.py`**: Domain constants and config keys

### Critical Design Patterns

**CAN Bus Communication**

- All CAN messages use extended IDs (29-bit)
- SET command: `0x01FC0002 | (module << 8)` with 5-byte payload
- GET command: `0x01FCFF01` to query relay state
- Filters registered: `0x0002FF01` (SET replies), `0x01FDFF01` (GET replies)
- Protocol details: https://gist.github.com/dries007/436fcd0549a52f26137bca942fef771a

**Global Lock Pattern**
A critical architectural constraint exists in `light.py`: GET replies don't include module/relay identifiers, so a shared `asyncio.Lock` serializes all GET operations across entities. Only the entity holding the lock accepts GET replies via `_awaiting_update` flag. This is a known code smell but necessary given the protocol limitations.

**State Management**

- Each `DobissLight` maintains internal `_is_on` state
- SET replies are filtered by module+relay in payload bytes [0] and [1]
- GET replies rely on the lock pattern described above
- `is_on` setter calls `async_write_ha_state()` to push updates to HA

### Config Flow Behavior

Two-step process:

1. **User step**: Collect `interface` (default: "socketcan") and `channel` (default: "can0")
2. **Light step**: Loop adding lights with `name`, `module` (1-indexed), and `relay` (0-indexed) until user unchecks "add_another"

Example config data structure:

```python
{
    "interface": "socketcan",
    "channel": "can0",
    "lights": [
        {"name": "Living Room", "module": 1, "relay": 0},
        {"name": "Kitchen", "module": 1, "relay": 1}
    ]
}
```

## Development Workflows

**Local Testing**
Install dependencies from `requirements.txt`:

```bash
pip install homeassistant~=2025.1.0 python-can~=4.0.0 voluptuous~=0.12
```

**Hardware Requirements**

- Functional CAN interface configured at 125kbit/s before HA starts
- Typical setup commands (run at boot):
  ```bash
  ip link set can0 type can bitrate 125000
  ip link set can0 up
  ```
- For HA OS users, use [HA_EnableCAN addon](https://github.com/dries007/HA_EnableCAN)

**Testing Without Hardware**
Use virtual CAN interface on Linux:

```bash
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
```

Then configure integration with `interface=socketcan` and `channel=vcan0`.

## Key Conventions

**Logging**
All modules set logger level to DEBUG explicitly:

```python
_LOGGER = logging.getLogger(DOMAIN)
_LOGGER.setLevel(logging.DEBUG)
```

**Entity Naming**

- Unique ID format: `dobiss.{entry_id}.{module}.{relay}`
- Device name is the user-provided light name
- Entity has no custom name (`_attr_name = None`) to use device name

**Timing & Rate Limiting**

- CAN send timeout: 100ms (`.1` second)
- Delays between GET operations: 10ms (`asyncio.sleep(.01)`)
- GET reply timeout: 500ms (`asyncio.wait_for` with 0.5s)
- These prevent overloading the CAN module

## Common Extension Points

**Adding Device Types**
To add covers/switches/etc beyond lights:

1. Create new platform file (e.g., `switch.py`) following `light.py` pattern
2. Add platform to `async_forward_entry_setups()` in `__init__.py`
3. Reuse the global lock pattern for GET operations
4. Update config flow to collect device-specific parameters

**Dimmer Support**
Current protocol only handles on/off (byte 2 in SET payload: 0 or 1). Dimming would require protocol investigation and updating:

- SET payload format (likely byte 2 becomes 0-255)
- `LightEntity` to use brightness features
- Config flow to identify dimmable vs toggle relays

## External Dependencies

- **python-can**: Abstracts CAN hardware (SocketCAN, PCAN, etc). Docs: https://python-can.readthedocs.io/
- **Home Assistant Platform APIs**: `LightEntity`, `ConfigFlow`, platform setup patterns
- **Hardware**: Waveshare RS485 CAN HAT tested, uses SPI with MCP2515 chipset (see README for dtoverlay config)
