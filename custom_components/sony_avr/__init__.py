"""The Sony AVR (IRCC) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_CERS_PORT,
    CONF_DEVICE_ID,
    CONF_DMR_PORT,
    CONF_IRCC_PORT,
    DEFAULT_CERS_PORT,
    DEFAULT_DMR_PORT,
    DEFAULT_IRCC_PORT,
)
from .coordinator import SonyAvrCoordinator
from .sony import SonyAvrClient

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER]

type SonyAvrConfigEntry = ConfigEntry[SonyAvrCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SonyAvrConfigEntry) -> bool:
    """Set up Sony AVR from a config entry."""
    client = SonyAvrClient(
        entry.data[CONF_HOST],
        async_get_clientsession(hass),
        device_id=entry.data[CONF_DEVICE_ID],
        cers_port=entry.data.get(CONF_CERS_PORT, DEFAULT_CERS_PORT),
        ircc_port=entry.data.get(CONF_IRCC_PORT, DEFAULT_IRCC_PORT),
        dmr_port=entry.data.get(CONF_DMR_PORT, DEFAULT_DMR_PORT),
    )

    coordinator = SonyAvrCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SonyAvrConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
