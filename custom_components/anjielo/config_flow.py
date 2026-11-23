"""Config flow: bridge host, ports and token; reauth and reconfigure (e.g. moving the bridge).

With the Anjielo Bridge add-on, the Supervisor announces the bridge
(async_step_hassio): the user only confirms.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_TOKEN, CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from .api import (
    AnjieloApi,
    AnjieloAuthError,
    AnjieloError,
    AnjieloVersionError,
    check_api_version,
)
from .const import API_VERSION, CONF_RTSP_PORT, DEFAULT_PORT, DEFAULT_RTSP_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, vol.UNDEFINED)): str,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): int,
            vol.Required(
                CONF_RTSP_PORT, default=defaults.get(CONF_RTSP_PORT, DEFAULT_RTSP_PORT)
            ): int,
            vol.Optional(
                CONF_API_TOKEN, default=defaults.get(CONF_API_TOKEN, "")
            ): str,
        }
    )


class AnjieloConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, Any] = {}

    async def _validate(
        self, data: dict[str, Any], errors: dict[str, str]
    ) -> dict[str, Any] | None:
        api = AnjieloApi(
            async_get_clientsession(self.hass),
            data[CONF_HOST].strip(),
            data[CONF_PORT],
            data.get(CONF_API_TOKEN, "").strip(),
        )
        try:
            info = await api.info()
            check_api_version(info, API_VERSION)
            return info
        except AnjieloAuthError:
            errors["base"] = "invalid_auth"
        except AnjieloVersionError as err:
            _LOGGER.warning("Anjielo: %s", err)
            errors["base"] = "incompatible_version"
        except AnjieloError:
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Anjielo: unexpected error")
            errors["base"] = "unknown"
        return None

    @staticmethod
    def _clean(data: dict[str, Any]) -> dict[str, Any]:
        return {
            **data,
            CONF_HOST: data[CONF_HOST].strip(),
            CONF_API_TOKEN: data.get(CONF_API_TOKEN, "").strip(),
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            info = await self._validate(user_input, errors)
            if info is not None:
                await self.async_set_unique_id(info["device_id"])
                self._abort_if_unique_id_configured(updates=self._clean(user_input))
                return self.async_create_entry(
                    title="Intercom", data=self._clean(user_input)
                )
        return self.async_show_form(
            step_id="user", data_schema=_schema(user_input or {}), errors=errors
        )

    async def async_step_hassio(self, discovery_info: HassioServiceInfo) -> ConfigFlowResult:
        """The Anjielo Bridge add-on announces itself (host, ports, token)."""
        conf = discovery_info.config
        self._discovered = {
            CONF_HOST: str(conf.get(CONF_HOST, "127.0.0.1")),
            CONF_PORT: int(conf.get(CONF_PORT, DEFAULT_PORT)),
            CONF_RTSP_PORT: int(conf.get(CONF_RTSP_PORT, DEFAULT_RTSP_PORT)),
            CONF_API_TOKEN: str(conf.get(CONF_API_TOKEN, "")),
        }
        # The add-on announces itself before its bridge listens: if it does
        # not answer yet, identify the intercom at confirmation time.
        info = await self._validate(self._discovered, {})
        if info is not None:
            await self.async_set_unique_id(info["device_id"])
            # Already configured (by hand, or an older add-on token): follow the add-on.
            self._abort_if_unique_id_configured(updates=self._discovered)
        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            info = await self._validate(self._discovered, errors)
            if info is not None:
                await self.async_set_unique_id(info["device_id"])
                self._abort_if_unique_id_configured(updates=self._discovered)
                return self.async_create_entry(title="Intercom", data=self._discovered)
        self._set_confirm_only()
        return self.async_show_form(step_id="hassio_confirm", errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, CONF_API_TOKEN: user_input[CONF_API_TOKEN]}
            if await self._validate(data, errors) is not None:
                return self.async_update_reload_and_abort(
                    entry, data_updates=self._clean(data)
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_TOKEN): str}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            info = await self._validate(user_input, errors)
            if info is not None:
                await self.async_set_unique_id(info["device_id"])
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry, data_updates=self._clean(user_input)
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_schema(user_input or dict(entry.data)),
            errors=errors,
        )
