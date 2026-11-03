"""DataUpdateCoordinator for the Discord Live integration."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    STATUS_COMPLETED,
    DiscordAuthError,
    DiscordConnectionError,
    DiscordEvent,
    DiscordGuildUnavailable,
    DiscordLiveClient,
    GuildInfo,
)
from .const import (
    CONF_GUILD_IDS,
    DEFAULT_EVENT_DURATION_HOURS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    ENDED_EVENT_RETENTION,
    GUILD_INFO_INTERVAL,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

type EventKey = tuple[int, datetime]


def event_key(event: DiscordEvent) -> EventKey:
    """Key identifying a single occurrence of an event.

    Recurring events keep their ID across occurrences, so the start time is
    part of the key.
    """
    return (event.id, event.scheduled_start)


@dataclass
class EndedEvent:
    """An event occurrence that was observed live and has since ended."""

    # Snapshot of the event as it was last seen while live, with its status
    # set to completed.
    event: DiscordEvent
    # UTC time at which the event was first observed to no longer be live.
    ended_at: datetime


@dataclass
class DiscordLiveCoordinatorData:
    """Data maintained by the Discord Live coordinator."""

    # Scheduled and active events, as currently returned by Discord.
    events: list[DiscordEvent] = field(default_factory=list)
    # Recently ended occurrences, which Discord no longer returns.
    ended: list[EndedEvent] = field(default_factory=list)


class DiscordLiveCoordinator(DataUpdateCoordinator[DiscordLiveCoordinatorData]):
    """Coordinator that polls the scheduled events of a group of guilds."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: DiscordLiveClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{config_entry.entry_id}",
            config_entry=config_entry,
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )
        self.client = client
        self.guild_ids: list[int] = [
            int(g) for g in config_entry.data.get(CONF_GUILD_IDS, [])
        ]
        # guild ID -> name and icon
        self.guilds: dict[int, GuildInfo] = {}
        # Guilds the bot has lost access to (kicked, or guild deleted)
        self.unavailable_guilds: set[int] = set()

        self._last_guild_info_update: datetime | None = None
        # Working state, mutated across update cycles. Each cycle snapshots
        # these into a fresh DiscordLiveCoordinatorData; self.data itself is
        # never mutated in place.
        self._events_by_guild: dict[int, list[DiscordEvent]] = {}
        # event ID -> last snapshot of an event while it was live
        self._live: dict[int, DiscordEvent] = {}
        self._ended: list[EndedEvent] = []

    async def _async_update_data(self) -> DiscordLiveCoordinatorData:
        """Update data from Discord."""
        now = dt_util.utcnow()

        if (
            self._last_guild_info_update is None
            or now - self._last_guild_info_update >= GUILD_INFO_INTERVAL
        ):
            await self._update_guild_info()
            self._last_guild_info_update = now

        await self._update_events()
        self._update_live_state(now)

        return DiscordLiveCoordinatorData(
            events=[e for g in self.guild_ids for e in self._events_by_guild.get(g, [])],
            ended=list(self._ended),
        )

    async def _update_guild_info(self) -> None:
        """Refresh guild names and icons."""
        for guild_id in self.guild_ids:
            try:
                self.guilds[guild_id] = await self.client.guild_info(guild_id)
            except DiscordAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except DiscordGuildUnavailable as err:
                _LOGGER.warning("Bot has no access to guild %s: %s", guild_id, err)
                self.unavailable_guilds.add(guild_id)
            except DiscordConnectionError as err:
                _LOGGER.debug("Could not fetch guild info for %s: %s", guild_id, err)

    async def _update_events(self) -> None:
        """Fetch the scheduled events of every guild in the group."""
        failures = 0
        for guild_id in self.guild_ids:
            try:
                events = await self.client.events(guild_id)
            except DiscordAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except DiscordGuildUnavailable as err:
                if guild_id not in self.unavailable_guilds:
                    _LOGGER.warning("Bot has no access to guild %s: %s", guild_id, err)
                self.unavailable_guilds.add(guild_id)
                self._events_by_guild[guild_id] = []
                continue
            except DiscordConnectionError as err:
                # Keep the previously fetched events for this guild.
                _LOGGER.warning("Error fetching events for guild %s: %s", guild_id, err)
                failures += 1
                continue
            self.unavailable_guilds.discard(guild_id)
            self._events_by_guild[guild_id] = events

        # Only fail the update outright when nothing could be fetched and we
        # have nothing to fall back on.
        if self.guild_ids and failures == len(self.guild_ids) and self.data is None:
            raise UpdateFailed("Error fetching events from Discord")

    def _update_live_state(self, now: datetime) -> None:
        """Track which events went live, and record when they ended."""
        current = {
            e.id: e for events in self._events_by_guild.values() for e in events
        }

        # A live event ends when Discord no longer returns it (completed or
        # cancelled), or returns it as not active (a recurring event moved on
        # to its next occurrence).
        for event_id, last_seen in list(self._live.items()):
            event = current.get(event_id)
            if event is None or not event.live:
                self._ended.append(
                    EndedEvent(
                        event=replace(last_seen, status=STATUS_COMPLETED),
                        ended_at=now,
                    )
                )
                del self._live[event_id]

        for event in current.values():
            if event.live:
                self._live[event.id] = event

        cutoff = now - ENDED_EVENT_RETENTION
        self._ended = [e for e in self._ended if e.ended_at >= cutoff]

    def guild_name(self, guild_id: int) -> str:
        """Best known name for a guild."""
        if info := self.guilds.get(guild_id):
            return info.name
        return str(guild_id)

    def relevant_events(self) -> list[DiscordEvent]:
        """Return the shared set of events to surface across all platforms.

        This is the single source of truth for "which events exist": every
        scheduled or active event, plus recently ended occurrences that Discord
        no longer returns.
        """
        if not self.data:
            return []
        events = list(self.data.events)
        known = {event_key(e) for e in events}
        for ended in self.data.ended:
            if event_key(ended.event) not in known:
                events.append(ended.event)
        return events

    def events_for_guild(self, guild_id: int) -> list[DiscordEvent]:
        """Return the relevant events that belong to a specific guild."""
        return [e for e in self.relevant_events() if e.guild_id == guild_id]

    def live_events(self, guild_id: int | None = None) -> list[DiscordEvent]:
        """Return currently live events, optionally for a single guild."""
        if not self.data:
            return []
        return [
            e
            for e in self.data.events
            if e.live and (guild_id is None or e.guild_id == guild_id)
        ]

    def event_end_time(self, event: DiscordEvent) -> datetime:
        """Return the effective end time for an event.

        Uses the observed end once an event that was live has ended, then the
        end time set on the event in Discord, and finally the default event
        duration. An end is only used when it is after the start.
        """
        if self.data:
            key = event_key(event)
            for ended in self.data.ended:
                if (
                    event_key(ended.event) == key
                    and ended.ended_at > event.scheduled_start
                ):
                    return ended.ended_at
        if event.scheduled_end and event.scheduled_end > event.scheduled_start:
            return event.scheduled_end
        return event.scheduled_start + timedelta(hours=DEFAULT_EVENT_DURATION_HOURS)

    def is_event_active(
        self, event: DiscordEvent, now: datetime | None = None
    ) -> bool:
        """Return whether an event is live or has not yet finished."""
        if event.live:
            return True
        if now is None:
            now = dt_util.now()
        return self.event_end_time(event) > now
