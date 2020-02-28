# Home Assistant component for processing lirc signal through socket lirc exported
Simple Home Assistant component to watch lirc signals and fire event when signal received

## Setup

To setup add to your configuration.yaml:
```yaml
lirc_socket:
  host: [lirc host ip]
  port: [lirc socket port] (optinal, default=8765)
  remote: [remote name to watch] (optional, default listen to all remote)
  long_press_count: [consider as long press as number of same key pressed] (optional, default=5)
```

And copy files in `custom_components` folder using the same structure like defined here:
```
 custom_components
    └── lirc_socket
        └── __init__.py
        └── manifest.json
```

`host` the host ip of the lirc socket service

`port` the port of the lirc socket service, which can be set in `lirc_options.conf`, the default value is 8765,

`remote` the remote name configured in lircd.conf

`long_press_count` if hold one button in remote, it will send signal consistently, this argument refer to after how many same signal, the button will be identified as holding instead of pressing. Sometimes press a  sensitive button would send more than one signal, so the default value is set as 5.


## Home Assistant Event
When pressing or holding a button of a remote received by a well configured lirc service, the component would fire an event which could be further processed by other component or automation.
Two identified event would be fired:

### Pressing button Event
```yaml
event_type: ir_command_received,
data:
  button_name: [button name pressed] (refer to lircd.conf),
  button_alt: "short",
  remote: [remote name configured] (refer to lircd.conf)
```

### Holding button Event
```yaml
event_type: ir_command_received,
data:
  button_name: [button name pressed] (refer to lircd.conf)
  button_alt: "long"
  remote: [remote name configured] (refer to lircd.conf)
```

### Releasing holding button Event 
```yaml
event_type: ir_command_received
data:
  button_name: [button name pressed] (refer to lircd.conf)
  button_alt: "end"
  remote: [remote name configured] (refer to lircd.conf)
```

## Other configuration Example:


### lirc service side
On the server the lirc service deployed, more infos please refer to lircd project

*lirc_option.conf*
```Conf
[lircd]
nodaemon        = False
driver          = default
device          = auto
output          = /var/run/lirc/lircd
pidfile         = /var/run/lirc/lircd.pid
plugindir       = /usr/lib/arm-linux-gnueabihf/lirc/plugins
permission      = 666
allow-simulate  = No
repeat-max      = 600
listen          = 0.0.0.0:8765   #the ip and port

[lircmd]
uinput          = False
nodaemon        = False
```

*lircd.conf*
```Conf
begin remote

  name  my-remote    # the remote name
  bits           16
  flags SPACE_ENC|CONST_LENGTH
  eps            30
  aeps          100

  header       9022  4464
  one           594  1647
  zero          594   525
  ptrail        592
  repeat       9027  2220
  pre_data_bits   16
  pre_data       0x20D3
  gap          108366
  toggle_bit_mask 0x0

      begin codes
          KEY_POWER	               0x52AD   # the button name
          KEY_EJECTCD              0x22DD
          KEY_SWITCHVIDEOMODE      0xC837
          KEY_SETUP                0xF00F
          KEY_BLUETOOTH            0xB24D
          KEY_1                    0x827D
          KEY_2                    0xC03F
          KEY_3                    0x42BD
          KEY_4                    0xA25D
          KEY_5                    0xE01F
          KEY_6                    0x629D
          KEY_7                    0xAA55
		  ...
	  end codes
  end remote
```


### Home Assistant Event Automation Example:
```yaml
- alias: 'remote key pressed'
  initial_state: 'True'
  trigger:
    platform: event
    event_type: ir_command_received
  action:
    - service: python_script.key_sensor
      data_template:
        button_name: '{{trigger.event.data.button_name}}'
        button_alt: '{{trigger.event.data.button_alt}}'
        remote: '{{trigger.event.data.remote}}'

```


## Updates

## Requests / Bugs

## Credits 
