"""Sensor platform for the Discord Live integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util, slugify

from .const import UPCOMING_RECURRENCE_HORIZON
from .coordinator import DiscordLiveCoordinator
from .entity import group_device_info

if TYPE_CHECKING:
    from .api import DiscordEvent

    from . import DiscordLiveConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiscordLiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the upcoming events sensor."""
    async_add_entities([DiscordLiveUpcomingSensor(entry.runtime_data.coordinator, entry)])


class DiscordLiveUpcomingSensor(
    CoordinatorEntity[DiscordLiveCoordinator], SensorEntity
):
    """Sensor showing upcoming events in a flat format for ESPHome."""

    # Friendly names are prefixed with the group (device) name.
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DiscordLiveCoordinator,
        entry: DiscordLiveConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_upcoming"
        self._attr_device_info = group_device_info(entry)
        object_id = f"discord_live_{slugify(entry.title)}_upcoming"
        self.entity_id = f"sensor.{object_id}"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Upcoming"

    def _upcoming_events(self) -> list[DiscordEvent]:
        """Return the group's still-active events, sorted by start time.

        Uses the coordinator's shared event set and active check so this
        sensor stays consistent with the calendar and binary sensors. Repeats
        of recurring events are included up to UPCOMING_RECURRENCE_HORIZON
        ahead.
        """
        now = dt_util.now()
        upcoming = [
            e
            for e in self.coordinator.calendar_events(now + UPCOMING_RECURRENCE_HORIZON)
            if self.coordinator.is_event_active(e, now)
        ]
        return sorted(upcoming, key=lambda e: e.scheduled_start)

    @property
    def native_value(self) -> int:
        """Return the count of upcoming events."""
        return len(self._upcoming_events())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return flat list of upcoming events as attributes."""
        upcoming = self._upcoming_events()

        attrs: dict[str, Any] = {}
        for i in range(5):
            prefix = f"event_{i}"
            if i < len(upcoming):
                event = upcoming[i]
                title = event.name or ""
                if len(title) > 80:
                    title = title[:77] + "..."

                duration = self.coordinator.event_end_time(event) - event.scheduled_start
                attrs[f"{prefix}_title"] = title
                attrs[f"{prefix}_start"] = event.scheduled_start.isoformat()
                attrs[f"{prefix}_event_id"] = str(event.id)
                attrs[f"{prefix}_guild"] = self.coordinator.guild_name(event.guild_id)
                attrs[f"{prefix}_live"] = event.live
                attrs[f"{prefix}_duration"] = int(duration.total_seconds() // 60)
            else:
                attrs[f"{prefix}_title"] = ""
                attrs[f"{prefix}_start"] = ""
                attrs[f"{prefix}_event_id"] = ""
                attrs[f"{prefix}_guild"] = ""
                attrs[f"{prefix}_live"] = False
                # Keep a stable int type for duration across all slots.
                attrs[f"{prefix}_duration"] = 0

        return attrs
