"""The Discord Live integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .api import DiscordAuthError, DiscordConnectionError, DiscordLiveClient
from .const import CONF_BOT_TOKEN
from .coordinator import DiscordLiveCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.CALENDAR, Platform.SENSOR]


@dataclass
class DiscordLiveRuntimeData:
    """Runtime data for a Discord Live group config entry."""

    coordinator: DiscordLiveCoordinator


type DiscordLiveConfigEntry = ConfigEntry[DiscordLiveRuntimeData]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiscordLiveConfigEntry,
) -> bool:
    """Set up a Discord Live group from a config entry."""
    client = DiscordLiveClient(entry.data[CONF_BOT_TOKEN])
    try:
        await client.login()
    except DiscordAuthError as err:
        await client.close()
        raise ConfigEntryAuthFailed(str(err)) from err
    except DiscordConnectionError as err:
        await client.close()
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = DiscordLiveCoordinator(hass, entry, client)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await client.close()
        raise

    entry.runtime_data = DiscordLiveRuntimeData(
        coordinator=coordinator,
    )
    entry.async_on_unload(client.close)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: DiscordLiveConfigEntry,
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
