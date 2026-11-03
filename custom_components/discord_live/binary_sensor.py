"""Binary sensor platform for the Discord Live integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import CONF_GUILD_IDS
from .coordinator import DiscordLiveCoordinator
from .entity import group_device_info

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .api import DiscordEvent
    from . import DiscordLiveConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiscordLiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors for a server group."""
    coordinator = entry.runtime_data.coordinator

    guild_ids = {str(g) for g in entry.data.get(CONF_GUILD_IDS, [])}

    # Remove entities for servers that are no longer in the config
    ent_reg = er.async_get(hass)
    for entity_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if entity_entry.domain != "binary_sensor":
            continue
        # The unique_id format is f"{entry.entry_id}_{guild_id}_live"
        # and f"{entry.entry_id}_any_live"
        uid = entity_entry.unique_id
        if not uid.startswith(f"{entry.entry_id}_"):
            continue
        suffix = uid[len(entry.entry_id) + 1:]
        if suffix == "any_live":
            continue
        if suffix.endswith("_live") and suffix[:-5] not in guild_ids:
            ent_reg.async_remove(entity_entry.entity_id)

    entities: list[BinarySensorEntity] = [
        DiscordLiveGuildSensor(coordinator, entry, guild_id)
        for guild_id in coordinator.guild_ids
    ]
    entities.append(DiscordLiveGroupSensor(coordinator, entry))

    async_add_entities(entities)


class DiscordLiveGuildSensor(
    CoordinatorEntity[DiscordLiveCoordinator], BinarySensorEntity
):
    """Binary sensor indicating whether a server has a live event."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    # Friendly names are prefixed with the group (device) name.
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DiscordLiveCoordinator,
        entry: DiscordLiveConfigEntry,
        guild_id: int,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._guild_id = guild_id
        self._attr_unique_id = f"{entry.entry_id}_{guild_id}_live"
        self._attr_device_info = group_device_info(entry)
        object_id = f"discord_live_{slugify(coordinator.guild_name(guild_id))}"
        self._attr_suggested_object_id = object_id
        self.entity_id = f"binary_sensor.{object_id}"

    @property
    def name(self) -> str:
        """Friendly name for the server sensor."""
        return self.coordinator.guild_name(self._guild_id)

    @property
    def available(self) -> bool:
        """Return False when the bot has lost access to the server."""
        return (
            super().available
            and self._guild_id not in self.coordinator.unavailable_guilds
        )

    def _live_event(self) -> DiscordEvent | None:
        """Return this server's first live event."""
        live = self.coordinator.live_events(self._guild_id)
        return live[0] if live else None

    @property
    def is_on(self) -> bool | None:
        """Return true if any of this server's events is currently live."""
        if self.coordinator.data is None:
            return None
        return self._live_event() is not None

    @property
    def entity_picture(self) -> str | None:
        """Return the event cover image when live, else the server icon."""
        if (event := self._live_event()) and event.cover_url:
            return event.cover_url
        if info := self.coordinator.guilds.get(self._guild_id):
            return info.icon_url
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        event = self._live_event()
        return {
            "guild_id": str(self._guild_id),
            "guild_name": self.coordinator.guild_name(self._guild_id),
            "group": self._entry.title,
            "event_id": str(event.id) if event else None,
            "event_name": event.name if event else None,
            "url": event.url if event else None,
            "event_start": event.scheduled_start.isoformat() if event else None,
            "event_type": event.entity_type if event else None,
            "location": event.location if event else None,
            "interested_count": event.user_count if event else None,
        }


class DiscordLiveGroupSensor(
    CoordinatorEntity[DiscordLiveCoordinator], BinarySensorEntity
):
    """Binary sensor indicating whether *any* server in the group is live."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    # Friendly names are prefixed with the group (device) name.
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DiscordLiveCoordinator,
        entry: DiscordLiveConfigEntry,
    ) -> None:
        """Initialize the aggregate sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_any_live"
        self._attr_device_info = group_device_info(entry)
        object_id = f"discord_live_{slugify(entry.title)}_any_live"
        self._attr_suggested_object_id = object_id
        self.entity_id = f"binary_sensor.{object_id}"

    @property
    def name(self) -> str:
        """Friendly name for the aggregate sensor."""
        return "Live"

    @property
    def is_on(self) -> bool | None:
        """Return true if any event in the group is currently live."""
        if self.coordinator.data is None:
            return None
        return bool(self.coordinator.live_events())

    @property
    def entity_picture(self) -> str | None:
        """Return the cover image of the first live event."""
        live = self.coordinator.live_events()
        return live[0].cover_url if live else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes listing live events."""
        live = self.coordinator.live_events()
        attrs: dict[str, Any] = {
            "group": self._entry.title,
            "guild_ids": [str(g) for g in self.coordinator.guild_ids],
            "live_event_ids": [str(e.id) for e in live],
            "live_count": len(live),
        }
        if live:
            event = live[0]
            attrs.update({
                "live_guild_id": str(event.guild_id),
                "live_guild_name": self.coordinator.guild_name(event.guild_id),
                "live_event_name": event.name,
                "live_url": event.url,
            })
        return attrs
