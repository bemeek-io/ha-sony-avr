"""IRCC key codes for Sony AV receivers.

These are the base64-encoded infrared command codes accepted by the
``X_SendIRCC`` SOAP action.

The set below was found by sweeping the command byte on an STR-DN840 (firmware
JB3.1.1) and keeping only the codes the receiver accepts. It rejects anything
it does not implement with UPnP error 802 ("Just can receive the X_SendIRCC
action"), so an unsupported code fails loudly rather than silently -- but that
also means most published Sony code tables, which are written for their TVs,
are largely useless here. Notably this receiver has no discrete power on/off
over IRCC; only a toggle.
"""

from __future__ import annotations

from typing import Final

# Command byte layout: 00 00 00 02 | 00 00 00 30 | 00 00 00 <cmd> | 03
IRCC_CODES: Final[dict[str, str]] = {
    # Power. The receiver rejects discrete on/off, so this is a toggle only.
    "power_toggle": "AAAAAgAAADAAAAAVAw==",
    # Volume
    "volume_up": "AAAAAgAAADAAAAASAw==",
    "volume_down": "AAAAAgAAADAAAAATAw==",
    "mute": "AAAAAgAAADAAAAAUAw==",
    # Navigation
    "home": "AAAAAgAAADAAAABTAw==",
    # Numeric keypad, used by the tuner for direct preset entry.
    "num0": "AAAAAgAAADAAAAAAAw==",
    "num1": "AAAAAgAAADAAAAABAw==",
    "num2": "AAAAAgAAADAAAAACAw==",
    "num3": "AAAAAgAAADAAAAADAw==",
    "num4": "AAAAAgAAADAAAAAEAw==",
    "num5": "AAAAAgAAADAAAAAFAw==",
    "num6": "AAAAAgAAADAAAAAGAw==",
    "num7": "AAAAAgAAADAAAAAHAw==",
    "num8": "AAAAAgAAADAAAAAIAw==",
    "num9": "AAAAAgAAADAAAAAJAw==",
    # Accepted by the receiver but not positively identified. Left in so they
    # are reachable via the send_command service.
    "unknown_0c": "AAAAAgAAADAAAAAMAw==",
    "unknown_4b": "AAAAAgAAADAAAABLAw==",
}

# Input selection.
#
# The receiver rejects every IRCC input code, so switching inputs over IRCC is
# not possible on this model. The names below come from the receiver itself,
# via ``/cers/getSystemInformation``, and are kept because they are also the
# strings it reports back as the active source.
SUPPORTED_SOURCES: Final[tuple[str, ...]] = (
    "BD",
    "DVD",
    "GAME",
    "SAT/CATV",
    "VIDEO",
    "TV",
    "SA-CD/CD",
    "TUNER",
    "USB",
    "AirPlay",
    "HOME NETWORK",
    "SEN",
    "BLUETOOTH",
)

# No working IRCC codes for input selection on this generation.
INPUT_CODES: Final[dict[str, str]] = {}
