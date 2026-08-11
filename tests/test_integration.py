"""Tests for the Home Assistant config flow and media player entity.

These run against a real Home Assistant instance via
``pytest-homeassistant-custom-component``, with the receiver itself stubbed out
at the client boundary.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.media_player import (
    ATTR_MEDIA_VOLUME_LEVEL,
    SERVICE_VOLUME_SET,
    MediaPlayerState,
)
from homeassistant.components.media_player import (
    DOMAIN as MEDIA_PLAYER_DOMAIN,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_HOST,
    CONF_NAME,
    CONF_PIN,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sony_avr.const import (
    CONF_CERS_PORT,
    CONF_DEVICE_ID,
    CONF_DMR_PORT,
    CONF_IRCC_PORT,
    DOMAIN,
)
from custom_components.sony_avr.sony import AuthResult, CannotConnect, SonyStatus

ENTITY_ID = "media_player.test_receiver"

ENTRY_DATA = {
    CONF_HOST: "192.168.1.50",
    CONF_NAME: "Test Receiver",
    CONF_DEVICE_ID: "MediaRemote:AA:BB:CC:DD:EE:FF",
    CONF_CERS_PORT: 50001,
    CONF_IRCC_PORT: 50001,
    CONF_DMR_PORT: 52323,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from custom_components during tests."""
    return


def make_status(**kwargs) -> SonyStatus:
    """Build a status snapshot with sensible defaults for an awake receiver."""
    defaults = {
        "available": True,
        "power_on": True,
        "volume": 40,
        "muted": False,
        "transport_state": "PLAYING",
        "source": "BD/DVD",
        "media_title": "Something",
    }
    return SonyStatus(**{**defaults, **kwargs})


async def setup_entry(
    hass: HomeAssistant, status: SonyStatus
) -> tuple[MockConfigEntry, AsyncMock]:
    """Set up the integration with a stubbed client."""
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, title="Test Receiver")
    entry.add_to_hass(hass)

    client = AsyncMock()
    client.host = ENTRY_DATA[CONF_HOST]
    client.async_get_status.return_value = status

    with patch("custom_components.sony_avr.SonyAvrClient", return_value=client):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry, client


async def test_full_config_flow_with_pin(hass: HomeAssistant) -> None:
    """The happy path: address, then PIN, then an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    client = AsyncMock()
    client.async_register.return_value = AuthResult.PIN_NEEDED

    # Creating the entry triggers async_setup_entry, which would build a real
    # client and start polling, so the setup path is stubbed out too.
    with (
        patch(
            "custom_components.sony_avr.config_flow.SonyAvrClient", return_value=client
        ),
        patch("custom_components.sony_avr.SonyAvrClient", return_value=client),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.1.50",
                CONF_NAME: "Test Receiver",
                CONF_CERS_PORT: 50001,
                CONF_IRCC_PORT: 50001,
                CONF_DMR_PORT: 52323,
            },
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "pin"

        client.async_register.return_value = AuthResult.SUCCESS
        client.async_get_status.return_value = make_status()
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PIN: "1234"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test Receiver"
    assert result["data"][CONF_HOST] == "192.168.1.50"
    # A device id must be persisted, or the pairing breaks on restart.
    assert result["data"][CONF_DEVICE_ID].startswith("MediaRemote:")


async def test_config_flow_unreachable_receiver(hass: HomeAssistant) -> None:
    """An unreachable receiver shows an error instead of creating an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    client = AsyncMock()
    client.async_register.side_effect = CannotConnect("nope")

    with patch(
        "custom_components.sony_avr.config_flow.SonyAvrClient", return_value=client
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.1.50",
                CONF_NAME: "Test Receiver",
                CONF_CERS_PORT: 50001,
                CONF_IRCC_PORT: 50001,
                CONF_DMR_PORT: 52323,
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_config_flow_bad_pin(hass: HomeAssistant) -> None:
    """A rejected PIN re-prompts rather than creating a broken entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    client = AsyncMock()
    client.async_register.return_value = AuthResult.PIN_NEEDED

    with patch(
        "custom_components.sony_avr.config_flow.SonyAvrClient", return_value=client
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.1.50",
                CONF_NAME: "Test Receiver",
                CONF_CERS_PORT: 50001,
                CONF_IRCC_PORT: 50001,
                CONF_DMR_PORT: 52323,
            },
        )
        client.async_register.return_value = AuthResult.ERROR
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PIN: "0000"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_duplicate_host_aborts(hass: HomeAssistant) -> None:
    """The same receiver cannot be added twice."""
    entry = MockConfigEntry(
        domain=DOMAIN, data=ENTRY_DATA, unique_id=ENTRY_DATA[CONF_HOST]
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "192.168.1.50",
            CONF_NAME: "Test Receiver",
            CONF_CERS_PORT: 50001,
            CONF_IRCC_PORT: 50001,
            CONF_DMR_PORT: 52323,
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_entity_reports_playing_state(hass: HomeAssistant) -> None:
    """A playing receiver surfaces volume, source and title."""
    await setup_entry(hass, make_status())

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == MediaPlayerState.PLAYING
    assert state.attributes[ATTR_MEDIA_VOLUME_LEVEL] == pytest.approx(0.4)
    assert state.attributes["source"] == "BD/DVD"
    assert state.attributes["media_title"] == "Something"
    assert state.attributes["is_volume_muted"] is False


async def test_entity_off_when_receiver_asleep(hass: HomeAssistant) -> None:
    """A standby receiver reads as off, not unavailable.

    This is the behaviour that keeps the turn-on button visible in the UI.
    """
    await setup_entry(hass, SonyStatus(available=False))

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_OFF


async def test_turn_on_and_off(hass: HomeAssistant) -> None:
    """Power services reach the client."""
    _, client = await setup_entry(hass, make_status())

    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: ENTITY_ID},
        blocking=True,
    )
    client.async_turn_on.assert_awaited_once()

    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: ENTITY_ID},
        blocking=True,
    )
    client.async_turn_off.assert_awaited_once()


async def test_set_volume_scales_to_device_range(hass: HomeAssistant) -> None:
    """HA's 0..1 volume is converted to the receiver's 0..100."""
    _, client = await setup_entry(hass, make_status())

    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_VOLUME_SET,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_MEDIA_VOLUME_LEVEL: 0.65},
        blocking=True,
    )
    client.async_set_volume.assert_awaited_once_with(65)


async def test_send_command_service(hass: HomeAssistant) -> None:
    """The custom service forwards raw IRCC command names."""
    _, client = await setup_entry(hass, make_status())

    await hass.services.async_call(
        DOMAIN,
        "send_command",
        {ATTR_ENTITY_ID: ENTITY_ID, "command": "home"},
        blocking=True,
    )
    client.async_send_command.assert_awaited_with("home")


async def test_unload_entry(hass: HomeAssistant) -> None:
    """The integration unloads cleanly."""
    entry, _ = await setup_entry(hass, make_status())

    assert entry.state is ConfigEntryState.LOADED
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
