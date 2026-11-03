"""Calendar platform for the Discord Live integration."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util, slugify

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
    """Set up one calendar entity per server group."""
    async_add_entities([DiscordLiveCalendar(entry)])


class DiscordLiveCalendar(
    CoordinatorEntity[DiscordLiveCoordinator], CalendarEntity
):
    """Calendar entity listing scheduled events for a single group."""

    # Friendly names are prefixed with the group (device) name.
    _attr_has_entity_name = True

    def __init__(
        self,
        entry: DiscordLiveConfigEntry,
    ) -> None:
        """Initialize the calendar entity."""
        super().__init__(entry.runtime_data.coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_calendar"
        self._attr_device_info = group_device_info(entry)
        object_id = f"discord_live_{slugify(entry.title)}"
        self._attr_suggested_object_id = object_id
        self.entity_id = f"calendar.{object_id}"

    @property
    def name(self) -> str:
        """Return a friendly name for the calendar."""
        return "Events"

    def _to_calendar_event(self, event: DiscordEvent) -> CalendarEvent:
        """Convert a DiscordEvent to a CalendarEvent."""
        # The coordinator is the single source of truth for the end time
        # (it accounts for an event that ended early).
        end_time = self.coordinator.event_end_time(event)

        if event.live:
            # If the event is currently live, ensure the end time is in the future.
            now = dt_util.now()
            if end_time < now + timedelta(minutes=30):
                end_time = now + timedelta(minutes=30)

        description = (
            f"{event.description}\n\n{event.url}" if event.description else event.url
        )
        return CalendarEvent(
            start=event.scheduled_start,
            end=end_time,
            summary=f"{self.coordinator.guild_name(event.guild_id)} - {event.name}",
            description=description,
            location=event.location,
            # Recurring events share an ID, so include the occurrence start.
            uid=f"{event.id}_{int(event.scheduled_start.timestamp())}",
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event in this group."""
        now = dt_util.now()
        for event in sorted(
            self.coordinator.relevant_events(), key=lambda e: e.scheduled_start
        ):
            calendar_event = self._to_calendar_event(event)
            if calendar_event.end > now:
                return calendar_event
        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        events: list[CalendarEvent] = []
        for event in self.coordinator.calendar_events(end_date):
            calendar_event = self._to_calendar_event(event)
            if calendar_event.start < end_date and calendar_event.end > start_date:
                events.append(calendar_event)
        events.sort(key=lambda e: e.start)
        return events
