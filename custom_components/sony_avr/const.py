"""Constants for the Sony AVR integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "sony_avr"

CONF_IRCC_PORT: Final = "ircc_port"
CONF_CERS_PORT: Final = "cers_port"
CONF_DMR_PORT: Final = "dmr_port"
CONF_DEVICE_ID: Final = "device_id"
CONF_MAC: Final = "mac"
# Whether CERS pairing completed. Optional: the integration works without
# it, but the input name and media title need it.
CONF_REGISTERED: Final = "registered"

# Verified against an STR-DN840 on firmware JB3.1.1.
#
# CERS registration and status live on 50001, but everything else -- IRCC and
# the UPnP renderer (RenderingControl, AVTransport) -- is served from the
# device description port, 8080. The control paths are likewise the ones the
# description advertises, not the /upnp/control/<Service> layout used by Sony's
# TVs.
DEFAULT_CERS_PORT: Final = 50001
DEFAULT_IRCC_PORT: Final = 8080
DEFAULT_DMR_PORT: Final = 8080

IRCC_CONTROL_PATH: Final = "/upnp/control/IRCC"
RENDERING_CONTROL_PATH: Final = "/RenderingControl/ctrl"
AV_TRANSPORT_PATH: Final = "/AVTransport/ctrl"

DEFAULT_NAME: Final = "Sony AVR"

# Registration identity presented to the receiver. The receiver stores this and
# shows it in Settings > Network > Renderer Access Control.
CLIENT_NAME: Final = "Home Assistant"
CLIENT_TYPE: Final = "Home Assistant"

SCAN_INTERVAL_SECONDS: Final = 10

# The receiver drops its HTTP listeners a moment after entering standby, so a
# connection error is a normal "off" reading rather than a failure.
REQUEST_TIMEOUT: Final = 5
