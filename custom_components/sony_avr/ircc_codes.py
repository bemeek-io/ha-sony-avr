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

# Input selection.
#
# The source names come from the receiver itself, via
# ``/cers/getSystemInformation`` -- these are exactly the strings an STR-DN840
# reports in its ``supportSource`` list, so they match what the receiver echoes
# back as the active source and can be compared directly.
INPUT_CODES: Final[dict[str, str]] = {
    "BD": "AAAAAgAAADAAAABzAw==",
    "DVD": "AAAAAgAAADAAAABxAw==",
    "GAME": "AAAAAgAAADAAAAB6Aw==",
    "SAT/CATV": "AAAAAgAAADAAAAB0Aw==",
    "VIDEO": "AAAAAgAAADAAAABsAw==",
    "TV": "AAAAAgAAADAAAAB1Aw==",
    "SA-CD/CD": "AAAAAgAAADAAAABuAw==",
    "TUNER": "AAAAAgAAADAAAABpAw==",
    "USB": "AAAAAgAAADAAAAB5Aw==",
    "AirPlay": "AAAAAgAAADAAAAB-Aw==",
    "HOME NETWORK": "AAAAAgAAADAAAAB7Aw==",
    "SEN": "AAAAAgAAADAAAAB8Aw==",
    "BLUETOOTH": "AAAAAgAAADAAAAB9Aw==",
}
