# ha-sony-avr

A Home Assistant integration for older Sony AV receivers that speak **IRCC-IP** —
the network remote protocol behind Sony's old TV SideView app.

Built for the **STR-DN840**, which the modern `songpal` integration does not
support. Songpal talks to Sony's newer JSON "Audio Control" API, which arrived
with the 2015-era models; the DN840 (2013) predates it and only exposes the
older CERS/IRCC and UPnP services. This integration talks to those instead.

## Supported hardware

Anything in the DN8xx/DN10xx generation that exposes `/cers/register` should
work:

- STR-DN840, STR-DN1040
- STR-DN850, STR-DN1050
- STR-DN860, STR-DN1060
- STR-DN1030, STR-DN1020, STR-DA1800ES

Only the STR-DN840 has been tested. Reports for the others are welcome.

## What you get

A `media_player` entity supporting:

| Capability | How it works | Needs pairing |
| --- | --- | --- |
| Power on / off | IRCC power codes | no |
| Volume set | UPnP `RenderingControl` (absolute, 0–100) | no |
| Volume up / down | IRCC step codes | no |
| Mute | `RenderingControl`, falling back to the IRCC toggle | no |
| Source select | IRCC input codes | no |
| Transport (play/pause/stop/next/prev) | IRCC codes | no |
| State, volume, mute | Polled from UPnP every 10s | no |
| Current input name, media title | Polled from CERS every 10s | yes |

Plus a `sony_avr.send_command` service for any remote key without a
`media_player` equivalent (`home`, `display`, `options`, arrow keys, …).

## Installation

### HACS

Add this repository as a custom repository of type *Integration*, install, then
restart Home Assistant.

### Manual

Copy `custom_components/sony_avr` into your Home Assistant `config/custom_components/`
directory and restart.

## Setup

Before adding the integration, on the receiver set **Settings → Network →
Network Standby → On**. Without it the receiver drops off the network in
standby and Home Assistant can neither read its state nor turn it back on.

Then in Home Assistant: **Settings → Devices & Services → Add Integration →
Sony AVR (IRCC)**.

1. Enter the receiver's IP address. Give it a DHCP reservation — the pairing is
   tied to the address.
2. That's it.

**Pairing is optional.** Volume, mute, transport state and every remote command
work over UPnP and IRCC without registering, so setup completes whether or not
the receiver accepts a pairing request. Registration only adds the current
input name and media title.

If you want those, put the receiver into pairing mode before adding the
integration — on the STR-DN840 that is **Home Network → Access Settings**,
where **Auto Access** should be **On**. Receivers that use a PIN will prompt
for one during setup.

## The `send_command` service

```yaml
action: sony_avr.send_command
target:
  entity_id: media_player.sony_avr
data:
  command: home
```

Available commands are in [`ircc_codes.py`](custom_components/sony_avr/ircc_codes.py):
`power_on`, `power_off`, `power_toggle`, `sleep`, `volume_up`, `volume_down`,
`mute`, `up`, `down`, `left`, `right`, `confirm`, `home`, `options`, `return`,
`display`, `play`, `pause`, `stop`, `next`, `prev`, `forward`, `rewind`.

## Notes and limitations

**Turning the receiver on requires Network Standby.** With it off, nothing is
listening while the receiver sleeps, so `turn_on` cannot reach it. There is no
software workaround — Wake-on-LAN is not supported by this generation over the
wired interface in standby.

**Input names are guesses.** The source list is the DN840's default input
labels. If you have renamed inputs on the receiver, or a sibling model labels
them differently, the names in Home Assistant will not match and some codes may
not map to the input you expect. Edit `INPUT_CODES` in
[`ircc_codes.py`](custom_components/sony_avr/ircc_codes.py) to match your unit.

**Reported source may lag.** The receiver reports the input it *thinks* is
active via CERS, which after an IRCC input change can take a poll cycle to
catch up.

**Unknown IRCC codes fail silently.** The receiver accepts any well-formed code
and ignores ones it does not implement, returning HTTP 200 either way. A command
that does nothing is more likely a wrong code than a transport error.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install pytest pytest-asyncio pytest-aiohttp ruff
.venv/bin/pip install homeassistant pytest-homeassistant-custom-component
.venv/bin/python -m pytest tests/ -q
.venv/bin/ruff check .
```

Install the dependencies directly rather than with `pip install -e .`. An
editable install leaves a finder path hook on `sys.path` that Home Assistant's
integration loader tries to read as a directory, which breaks every test that
starts a Home Assistant instance.

The protocol client in [`sony.py`](custom_components/sony_avr/sony.py) has no
Home Assistant imports, so `tests/test_sony.py` exercises it against a stub HTTP
server without installing HA. `tests/test_integration.py` covers the config flow
and entity against a real Home Assistant instance.

## Prior art

The protocol behaviour here was derived from
[KHerron/SonyAPILib](https://github.com/KHerron/SonyAPILib) (C#) and
[alexmohr/sonyapilib](https://github.com/alexmohr/sonyapilib) (Python, last
released 2020). Neither is used as a dependency — `sonyapilib` is unmaintained
and synchronous, which does not suit Home Assistant's event loop — but both were
useful references for the CERS registration handshake and the IRCC code table.

## License

MIT
