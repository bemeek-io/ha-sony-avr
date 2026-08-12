"""Media player platform for the Sony AVR integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SonyAvrConfigEntry
from .const import DEFAULT_NAME, DOMAIN
from .coordinator import SonyAvrCoordinator
from .ircc_codes import IRCC_CODES
from .sony import MAX_VOLUME, SonyAvrError

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND_COMMAND = "send_command"
ATTR_COMMAND = "command"

# AVTransport reports these; anything else is treated as idle.
TRANSPORT_STATE_MAP = {
    "PLAYING": MediaPlayerState.PLAYING,
    "PAUSED_PLAYBACK": MediaPlayerState.PAUSED,
    "PAUSED_RECORDING": MediaPlayerState.PAUSED,
    "TRANSITIONING": MediaPlayerState.BUFFERING,
    "STOPPED": MediaPlayerState.IDLE,
    "NO_MEDIA_PRESENT": MediaPlayerState.IDLE,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SonyAvrConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the media player from a config entry."""
    async_add_entities([SonyAvrMediaPlayer(entry.runtime_data, entry)])

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SEND_COMMAND,
        {vol.Required(ATTR_COMMAND): vol.In(sorted(IRCC_CODES))},
        "async_send_command",
    )


class SonyAvrMediaPlayer(CoordinatorEntity[SonyAvrCoordinator], MediaPlayerEntity):
    """A Sony AV receiver controlled over IRCC-IP."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    # Only what the receiver actually accepts. It rejects the IRCC codes for
    # transport control and input selection outright, so advertising those
    # would put buttons in the UI that cannot work.
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
    )

    def __init__(
        self, coordinator: SonyAvrCoordinator, entry: SonyAvrConfigEntry
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, DEFAULT_NAME),
            manufacturer="Sony",
            model="AV Receiver",
            configuration_url=f"http://{entry.data[CONF_HOST]}",
        )

    @property
    def available(self) -> bool:
        """Whether the receiver answered the last poll.

        A receiver in standby stops listening entirely, so we stay "available"
        and report state OFF instead -- otherwise the entity would flip to
        unavailable every time it is switched off, which hides the turn-on
        control in the UI.
        """
        return self.coordinator.last_update_success

    @property
    def state(self) -> MediaPlayerState:
        """Return the current state."""
        status = self.coordinator.data
        if status is None or not status.available or not status.power_on:
            return MediaPlayerState.OFF
        if status.transport_state:
            return TRANSPORT_STATE_MAP.get(status.transport_state, MediaPlayerState.ON)
        return MediaPlayerState.ON

    @property
    def volume_level(self) -> float | None:
        """Volume as a 0..1 fraction."""
        status = self.coordinator.data
        if status is None or status.volume is None:
            return None
        return status.volume / MAX_VOLUME

    @property
    def is_volume_muted(self) -> bool | None:
        """Whether the receiver is muted."""
        status = self.coordinator.data
        return None if status is None else status.muted

    @property
    def source(self) -> str | None:
        """The currently selected input."""
        status = self.coordinator.data
        return None if status is None else status.source

    @property
    def media_title(self) -> str | None:
        """Title of the currently playing media, when the receiver reports one."""
        status = self.coordinator.data
        return None if status is None else status.media_title

    async def _async_run(self, coro) -> None:
        """Run a client call, then refresh so the UI reflects the result.

        The receiver needs a beat to settle before it reports the new state,
        so this leans on the coordinator's next poll rather than reading back
        immediately.
        """
        try:
            await coro
        except SonyAvrError as err:
            _LOGGER.error("Command failed: %s", err)
            raise
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Wake the receiver.

        Only a power toggle exists on this generation, so this is a no-op when
        the receiver is already on -- sending it would switch it off.
        """
        if self.state is not MediaPlayerState.OFF:
            return
        await self._async_run(self.coordinator.client.async_turn_on())

    async def async_turn_off(self) -> None:
        """Put the receiver into standby, unless it is already off."""
        if self.state is MediaPlayerState.OFF:
            return
        await self._async_run(self.coordinator.client.async_turn_off())

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume from a 0..1 fraction."""
        await self._async_run(
            self.coordinator.client.async_set_volume(round(volume * MAX_VOLUME))
        )

    async def async_volume_up(self) -> None:
        """Step the volume up."""
        await self._async_run(self.coordinator.client.async_send_command("volume_up"))

    async def async_volume_down(self) -> None:
        """Step the volume down."""
        await self._async_run(self.coordinator.client.async_send_command("volume_down"))

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute or unmute."""
        await self._async_run(self.coordinator.client.async_set_mute(mute))

    async def async_send_command(self, command: str) -> None:
        """Send an arbitrary IRCC command, for keys with no HA equivalent."""
        await self._async_run(self.coordinator.client.async_send_command(command))
