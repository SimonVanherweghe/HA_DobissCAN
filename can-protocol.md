# CAN Protocol

## 1 Request status of all outputs

### 1.1 Send

To each module

{ 0xAF, 0x01, moduleType, moduleAddress, 0x00, 0x00, 0x00,
0x01, 0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xAF };

#### Read output status command

moduleType:

- Relay: 0x08
- Dimmer: 0x10
- 0 - 10V: 0x18

moduleAddress: 0x01 - 0x52

### 1.2 Receive

1 line of 16 bytes

#### The status of each output (1 byte per output)

- 0 - 1 for relais
- 0 - 100 for dimmers

## 2 Send TOGGLE action to output/mood

{ 0xAF, 0x02, 0xFF, outputAddress, 0x00, 0x00, 0x08, 0x01,
0x08, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xAF }

### Toggle action command header

outputAddress: 0x01 - 0x52

{ outputAddress, outputID, 0x02, 0xFF, 0xFF, 0x64, 0xFF, 0xFF }

### Toggle action command body

outputAddress: 0x01 - 0x52
outputID:

- Relay: 0x00 - 0x0B
- Dimmer: 0x00 - 0x03
- 0 - 10V: 0x00 - 0x07

## 2.1 Body structure

1. **ADDRESS** Address of the module
2. **OUTPUT** Output on which the action applies (0x00 - 0x0B)
3. **ACTION** Action to be executed
    0x00 Off
    0x01 On
    0x02 Toggle
4. _DELAY ON_
    _0xFF (disabled)_
       The delay before executing the action ON.
5. _DELAY OFF_
    _0xFF (disabled)_
       The delay before executing the action OFF.
6. _VALUE_
    _0x64 (100%)_
       The dimmer value
7. _SOFTDIM_
    _0xFF (disabled)_
       The speed of dimming
8. _COND_
    _0xFF (disabled)_
       Not used

## 3 Send DIM action to output

### Dim action command header

{ 0xAF, 0x02, 0xFF, outputAddress, 0x00, 0x00, 0x08, 0x01, 0x08, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xAF }

### Dim action command body

{ outputAddress, outputID, 0x01, 0xFF, 0xFF, dimValue, 0xFF, 0xFF}

## 3.1 Body structure

1. **ADDRESS** Address of the module
2. **OUTPUT** Output on which the action applies (0x00 - 0x0B)
3. **ACTION** Action to be executed
    0x00 Off
    0x01 On
    0x02 Toggle
4. _DELAY ON_
    _0xFF (disabled)_
       The delay before executing the action ON.
5. _DELAY OFF_
    _0xFF (disabled)_
       The delay before executing the action OFF.
6. **VALUE** The dimmer value or audio volume
7. _SOFTDIM_
    _0xFF (disabled)_
       The speed of dimming
8. _COND_
    _0xFF (disabled)_
       Not used
