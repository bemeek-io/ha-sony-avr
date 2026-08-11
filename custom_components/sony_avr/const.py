"""Constants for the Sony AVR integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "sony_avr"

CONF_IRCC_PORT: Final = "ircc_port"
CONF_CERS_PORT: Final = "cers_port"
CONF_DMR_PORT: Final = "dmr_port"
CONF_DEVICE_ID: Final = "device_id"
CONF_MAC: Final = "mac"

# Sony's "network remote" ports. The receiver serves the CERS registration and
# status API on 50001 and the UPnP/DLNA renderer (AVTransport, RenderingControl)
# on 52323. IRCC control lives on the CERS port for the DN8xx/DN10xx era.
DEFAULT_CERS_PORT: Final = 50001
DEFAULT_IRCC_PORT: Final = 50001
DEFAULT_DMR_PORT: Final = 52323

DEFAULT_NAME: Final = "Sony AVR"

# Registration identity presented to the receiver. The receiver stores this and
# shows it in Settings > Network > Renderer Access Control.
CLIENT_NAME: Final = "Home Assistant"
CLIENT_TYPE: Final = "Home Assistant"

SCAN_INTERVAL_SECONDS: Final = 10

# The receiver drops its HTTP listeners a moment after entering standby, so a
# connection error is a normal "off" reading rather than a failure.
REQUEST_TIMEOUT: Final = 5
