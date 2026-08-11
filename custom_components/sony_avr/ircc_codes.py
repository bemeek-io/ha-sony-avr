"""IRCC key codes for Sony AV receivers.

These are the base64-encoded infrared command codes accepted by the
``X_SendIRCC`` SOAP action. The set below is the one the STR-DN840 and its
DN8xx/DN10xx siblings respond to; unsupported codes are accepted by the
receiver and silently ignored rather than returning an error, so an unknown
code looks like a no-op.
"""

from __future__ import annotations

from typing import Final

IRCC_CODES: Final[dict[str, str]] = {
    # Power
    "power_on": "AAAAAgAAADAAAAAuAw==",
    "power_off": "AAAAAgAAADAAAAAvAw==",
    "power_toggle": "AAAAAgAAADAAAAAVAw==",
    "sleep": "AAAAAgAAADAAAAAaAw==",
    # Volume
    "volume_up": "AAAAAgAAADAAAAASAw==",
    "volume_down": "AAAAAgAAADAAAAATAw==",
    "mute": "AAAAAgAAADAAAAAUAw==",
    # Navigation
    "up": "AAAAAgAAADAAAAA5Aw==",
    "down": "AAAAAgAAADAAAAA6Aw==",
    "left": "AAAAAgAAADAAAAA7Aw==",
    "right": "AAAAAgAAADAAAAA8Aw==",
    "confirm": "AAAAAgAAADAAAAA9Aw==",
    "home": "AAAAAgAAADAAAABTAw==",
    "options": "AAAAAgAAADAAAABUAw==",
    "return": "AAAAAgAAADAAAABYAw==",
    "display": "AAAAAgAAADAAAAA_Aw==",
    # Transport
    "play": "AAAAAgAAADAAAAAaAw==",
    "pause": "AAAAAgAAADAAAAAZAw==",
    "stop": "AAAAAgAAADAAAAAYAw==",
    "next": "AAAAAgAAADAAAAB1Aw==",
    "prev": "AAAAAgAAADAAAAB2Aw==",
    "forward": "AAAAAgAAADAAAAB3Aw==",
    "rewind": "AAAAAgAAADAAAAB4Aw==",
}

# Input selection. The STR-DN840's front-panel input names map to these codes;
# the labels are what Home Assistant shows in the source list.
INPUT_CODES: Final[dict[str, str]] = {
    "BD/DVD": "AAAAAgAAADAAAABzAw==",
    "Game": "AAAAAgAAADAAAAB6Aw==",
    "Sat/CATV": "AAAAAgAAADAAAAB0Aw==",
    "Video": "AAAAAgAAADAAAABsAw==",
    "TV": "AAAAAgAAADAAAABsAw==",
    "SA-CD/CD": "AAAAAgAAADAAAABuAw==",
    "FM Tuner": "AAAAAgAAADAAAABpAw==",
    "AM Tuner": "AAAAAgAAADAAAABqAw==",
    "USB": "AAAAAgAAADAAAAB5Aw==",
    "Home Network": "AAAAAgAAADAAAAB7Aw==",
    "Music Services": "AAAAAgAAADAAAAB8Aw==",
    "Bluetooth": "AAAAAgAAADAAAAB9Aw==",
}
