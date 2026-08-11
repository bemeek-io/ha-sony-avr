"""Media player platform for the Sony AVR integration."""

from __future__ import annotations

import logging
from typing import ClassVar

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
from .ircc_codes import INPUT_CODES, IRCC_CODES
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
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
    )
    _attr_source_list: ClassVar[list[str]] = list(INPUT_CODES)

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
        """Wake the receiver."""
        await self._async_run(self.coordinator.client.async_turn_on())

    async def async_turn_off(self) -> None:
        """Put the receiver into standby."""
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

    async def async_select_source(self, source: str) -> None:
        """Switch inputs."""
        await self._async_run(self.coordinator.client.async_select_source(source))

    async def async_media_play(self) -> None:
        """Play."""
        await self._async_run(self.coordinator.client.async_send_command("play"))

    async def async_media_pause(self) -> None:
        """Pause."""
        await self._async_run(self.coordinator.client.async_send_command("pause"))

    async def async_media_stop(self) -> None:
        """Stop."""
        await self._async_run(self.coordinator.client.async_send_command("stop"))

    async def async_media_next_track(self) -> None:
        """Skip forward."""
        await self._async_run(self.coordinator.client.async_send_command("next"))

    async def async_media_previous_track(self) -> None:
        """Skip back."""
        await self._async_run(self.coordinator.client.async_send_command("prev"))

    async def async_send_command(self, command: str) -> None:
        """Send an arbitrary IRCC command, for keys with no HA equivalent."""
        await self._async_run(self.coordinator.client.async_send_command(command))
