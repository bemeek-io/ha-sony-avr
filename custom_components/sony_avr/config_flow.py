"""Config flow for the Sony AVR integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PIN
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_CERS_PORT,
    CONF_DEVICE_ID,
    CONF_DMR_PORT,
    CONF_IRCC_PORT,
    DEFAULT_CERS_PORT,
    DEFAULT_DMR_PORT,
    DEFAULT_IRCC_PORT,
    DEFAULT_NAME,
    DOMAIN,
)
from .sony import (
    AuthResult,
    CannotConnect,
    PairingModeRequired,
    SonyAvrClient,
    generate_device_id,
)

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Optional(CONF_CERS_PORT, default=DEFAULT_CERS_PORT): int,
        vol.Optional(CONF_IRCC_PORT, default=DEFAULT_IRCC_PORT): int,
        vol.Optional(CONF_DMR_PORT, default=DEFAULT_DMR_PORT): int,
    }
)

PIN_SCHEMA = vol.Schema({vol.Required(CONF_PIN): str})


class SonyAvrConfigFlow(ConfigFlow, domain=DOMAIN):
    """Walk the user through pairing with the receiver."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""
        self._data: dict[str, Any] = {}
        self._client: SonyAvrClient | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the receiver's address and start registration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()

            device_id = generate_device_id()
            client = SonyAvrClient(
                user_input[CONF_HOST],
                async_get_clientsession(self.hass),
                device_id=device_id,
                cers_port=user_input[CONF_CERS_PORT],
                ircc_port=user_input[CONF_IRCC_PORT],
                dmr_port=user_input[CONF_DMR_PORT],
            )

            try:
                result = await client.async_register()
            except PairingModeRequired:
                errors["base"] = "pairing_mode_required"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                self._data = {**user_input, CONF_DEVICE_ID: device_id}
                self._client = client

                if result is AuthResult.SUCCESS:
                    # Some receivers pair without ever showing a PIN.
                    return self._create_entry()
                if result is AuthResult.PIN_NEEDED:
                    return await self.async_step_pin()
                errors["base"] = "cannot_register"

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    async def async_step_pin(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the PIN shown on the receiver and finish pairing."""
        errors: dict[str, str] = {}
        assert self._client is not None

        if user_input is not None:
            try:
                result = await self._client.async_register(user_input[CONF_PIN])
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                if result is AuthResult.SUCCESS:
                    return self._create_entry()
                errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="pin",
            data_schema=PIN_SCHEMA,
            errors=errors,
            description_placeholders={"host": self._data[CONF_HOST]},
        )

    def _create_entry(self) -> ConfigFlowResult:
        """Store the paired receiver."""
        return self.async_create_entry(
            title=self._data.get(CONF_NAME, DEFAULT_NAME), data=self._data
        )
