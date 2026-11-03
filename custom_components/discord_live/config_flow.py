"""Config flow for the Discord Live integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .api import (
    DiscordAuthError,
    DiscordLiveClient,
    DiscordLiveError,
    GuildInfo,
)
from .const import CONF_BOT_TOKEN, CONF_GROUP_NAME, CONF_GUILD_IDS, DOMAIN

_LOGGER = logging.getLogger(__name__)


_TOKEN_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
)


def _guild_selector(
    guilds: list[GuildInfo], extra_ids: list[str] | None = None
) -> selector.SelectSelector:
    """Build a multi-select of guilds.

    ``extra_ids`` are selected guild IDs the bot is no longer a member of, kept
    as options so they can be deselected.
    """
    options = [
        selector.SelectOptionDict(value=str(g.id), label=g.name) for g in guilds
    ]
    known = {str(g.id) for g in guilds}
    options.extend(
        selector.SelectOptionDict(value=gid, label=f"{gid} (no access)")
        for gid in extra_ids or []
        if gid not in known
    )
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            multiple=True,
            mode=selector.SelectSelectorMode.LIST,
        )
    )


async def _fetch_guilds(token: str) -> tuple[list[GuildInfo], dict[str, str]]:
    """Log in with a bot token and list the guilds the bot is in.

    :returns: Tuple of ``(guilds, errors)``. On success, the error dict is
              empty.
    """
    client = DiscordLiveClient(token)
    try:
        await client.login()
        guilds = await client.guilds()
    except DiscordAuthError:
        return [], {"base": "invalid_auth"}
    except DiscordLiveError:
        _LOGGER.exception("Error connecting to Discord")
        return [], {"base": "cannot_connect"}
    except Exception:
        _LOGGER.exception("Unexpected error connecting to Discord")
        return [], {"base": "unknown"}
    finally:
        await client.close()
    return sorted(guilds, key=lambda g: g.name.lower()), {}


class DiscordLiveConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Discord Live."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._group_name = ""
        self._token = ""
        self._guilds: list[GuildInfo] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: name the group and enter the bot token."""
        errors: dict[str, str] = {}

        if user_input is not None:
            group_name = user_input[CONF_GROUP_NAME].strip()
            token = user_input[CONF_BOT_TOKEN].strip()

            if not group_name:
                errors["base"] = "no_group_name"
            else:
                await self.async_set_unique_id(slugify(group_name))
                self._abort_if_unique_id_configured()
                guilds, errors = await _fetch_guilds(token)
                if not errors and not guilds:
                    errors["base"] = "no_guilds"
                if not errors:
                    self._group_name = group_name
                    self._token = token
                    self._guilds = guilds
                    return await self.async_step_guilds()

        schema = vol.Schema(
            {
                vol.Required(CONF_GROUP_NAME): str,
                vol.Required(CONF_BOT_TOKEN): _TOKEN_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_guilds(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the servers to include in the group."""
        errors: dict[str, str] = {}

        if user_input is not None:
            guild_ids = user_input.get(CONF_GUILD_IDS, []) or []
            if not guild_ids:
                errors["base"] = "no_guilds_selected"
            else:
                return self.async_create_entry(
                    title=self._group_name,
                    data={CONF_BOT_TOKEN: self._token, CONF_GUILD_IDS: guild_ids},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_GUILD_IDS, default=[]): _guild_selector(self._guilds),
            }
        )
        return self.async_show_form(
            step_id="guilds",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle a rejected bot token."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new bot token."""
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_BOT_TOKEN].strip()
            _, errors = await _fetch_guilds(token)
            if not errors:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={CONF_BOT_TOKEN: token},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_BOT_TOKEN): _TOKEN_SELECTOR}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return DiscordLiveOptionsFlow()


class DiscordLiveOptionsFlow(OptionsFlow):
    """Options flow: edit the servers in a group."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        entry = self.config_entry
        current_ids = list(entry.data.get(CONF_GUILD_IDS, []))

        if user_input is not None:
            guild_ids = user_input.get(CONF_GUILD_IDS, []) or []
            if not guild_ids:
                errors["base"] = "no_guilds_selected"
            else:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, CONF_GUILD_IDS: guild_ids},
                )
                self.hass.config_entries.async_schedule_reload(entry.entry_id)
                return self.async_create_entry(title="", data={})
            current_ids = guild_ids

        guilds, fetch_errors = await _fetch_guilds(entry.data[CONF_BOT_TOKEN])
        if fetch_errors:
            return self.async_abort(reason=fetch_errors["base"])

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_GUILD_IDS, default=current_ids
                ): _guild_selector(guilds, current_ids),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
