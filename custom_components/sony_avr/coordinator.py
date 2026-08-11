"""Polling coordinator for the Sony AVR integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, SCAN_INTERVAL_SECONDS
from .sony import InvalidAuth, SonyAvrClient, SonyStatus

_LOGGER = logging.getLogger(__name__)


class SonyAvrCoordinator(DataUpdateCoordinator[SonyStatus]):
    """Polls the receiver and shares one snapshot with every entity."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: SonyAvrClient
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {client.host}",
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
            config_entry=entry,
        )
        self.client = client

    async def _async_update_data(self) -> SonyStatus:
        """Fetch the receiver's state.

        The client reports an unreachable receiver as ``available=False``
        rather than raising, because standby looks exactly like a network
        failure and should not mark the entity unavailable-with-error.
        """
        try:
            return await self.client.async_get_status()
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed(str(err)) from err
