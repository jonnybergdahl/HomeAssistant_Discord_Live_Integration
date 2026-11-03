"""Thin wrapper around discord.py for the Discord Live integration.

Only the REST part of discord.py is used: the client logs in with a bot token
but never opens a gateway connection, so no intents are needed. Everything the
rest of the integration sees is converted to plain dataclasses, and discord.py
exceptions are mapped to the exceptions defined here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any

import aiohttp
import discord

from .recurrence import RecurrenceRule

_LOGGER = logging.getLogger(__name__)

STATUS_SCHEDULED = "scheduled"
STATUS_ACTIVE = "active"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"


class DiscordLiveError(Exception):
    """Base error for the Discord Live client."""


class DiscordAuthError(DiscordLiveError):
    """The bot token was rejected."""


class DiscordConnectionError(DiscordLiveError):
    """Discord could not be reached or returned an unexpected error."""


class DiscordGuildUnavailable(DiscordLiveError):
    """The bot is not in the guild, or lacks access to it."""


@dataclass
class GuildInfo:
    """Basic information about a guild (server)."""

    id: int
    name: str
    icon_url: str | None = None


@dataclass
class DiscordEvent:
    """A guild scheduled event."""

    id: int
    guild_id: int
    name: str
    scheduled_start: datetime
    status: str
    url: str
    scheduled_end: datetime | None = None
    description: str | None = None
    entity_type: str | None = None
    location: str | None = None
    channel_id: int | None = None
    cover_url: str | None = None
    user_count: int | None = None
    recurrence: RecurrenceRule | None = None

    @property
    def live(self) -> bool:
        """Return whether Discord reports the event as active."""
        return self.status == STATUS_ACTIVE


def _status_name(status: discord.EventStatus) -> str:
    """Normalize an EventStatus to one of the STATUS_* constants."""
    if status == discord.EventStatus.active:
        return STATUS_ACTIVE
    if status == discord.EventStatus.completed:
        return STATUS_COMPLETED
    if status == discord.EventStatus.cancelled:
        return STATUS_CANCELLED
    return STATUS_SCHEDULED


def _entity_type_name(entity_type: discord.EntityType) -> str:
    """Return a short name for the event location type."""
    if entity_type == discord.EntityType.stage_instance:
        return "stage"
    if entity_type == discord.EntityType.voice:
        return "voice"
    return "external"


def _to_event(
    event: discord.ScheduledEvent, recurrence: RecurrenceRule | None = None
) -> DiscordEvent:
    """Convert a discord.py ScheduledEvent to a DiscordEvent."""
    return DiscordEvent(
        id=event.id,
        guild_id=event.guild_id,
        name=event.name,
        scheduled_start=event.start_time,
        scheduled_end=event.end_time,
        status=_status_name(event.status),
        url=event.url,
        description=event.description,
        entity_type=_entity_type_name(event.entity_type),
        location=event.location,
        channel_id=event.channel_id,
        cover_url=event.cover_image.url if event.cover_image else None,
        user_count=event.user_count,
        recurrence=recurrence,
    )


def _to_guild_info(guild: discord.Guild) -> GuildInfo:
    """Convert a discord.py Guild to a GuildInfo."""
    return GuildInfo(
        id=guild.id,
        name=guild.name,
        icon_url=guild.icon.url if guild.icon else None,
    )


class DiscordLiveClient:
    """REST-only Discord client used by the coordinator and config flow."""

    def __init__(self, token: str) -> None:
        """Initialize the client."""
        self._token = token
        self._client = discord.Client(intents=discord.Intents.none())
        self._logged_in = False

    async def login(self) -> str:
        """Log in with the bot token and return the bot's user name."""
        try:
            await self._client.login(self._token)
        except discord.LoginFailure as err:
            raise DiscordAuthError(str(err)) from err
        except (discord.HTTPException, aiohttp.ClientError) as err:
            raise DiscordConnectionError(str(err)) from err
        self._logged_in = True
        user = self._client.user
        return user.name if user else ""

    async def guilds(self) -> list[GuildInfo]:
        """Return the guilds the bot is a member of."""
        try:
            return [_to_guild_info(g) async for g in self._client.fetch_guilds(limit=None)]
        except discord.HTTPException as err:
            raise self._map_http_error(err) from err
        except aiohttp.ClientError as err:
            raise DiscordConnectionError(str(err)) from err

    async def guild_info(self, guild_id: int) -> GuildInfo:
        """Fetch a single guild."""
        try:
            guild = await self._client.fetch_guild(guild_id)
        except discord.HTTPException as err:
            raise self._map_http_error(err) from err
        except aiohttp.ClientError as err:
            raise DiscordConnectionError(str(err)) from err
        return _to_guild_info(guild)

    async def events(self, guild_id: int) -> list[DiscordEvent]:
        """Return the scheduled and active events of a guild."""
        # discord.py drops the recurrence rule when it builds ScheduledEvent
        # objects, so fetch the raw payloads and build the objects ourselves.
        try:
            payloads: list[dict[str, Any]] = (
                await self._client.http.get_scheduled_events(guild_id, True)
            )
        except discord.HTTPException as err:
            raise self._map_http_error(err) from err
        except aiohttp.ClientError as err:
            raise DiscordConnectionError(str(err)) from err
        state = self._client._connection  # noqa: SLF001
        return [
            _to_event(
                discord.ScheduledEvent(state=state, data=data),
                RecurrenceRule.from_payload(data.get("recurrence_rule")),
            )
            for data in payloads
        ]

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._logged_in:
            await self._client.close()
            self._logged_in = False

    @staticmethod
    def _map_http_error(err: discord.HTTPException) -> DiscordLiveError:
        """Map a discord.py HTTP error to a DiscordLiveError."""
        if err.status == 401:
            return DiscordAuthError(str(err))
        if isinstance(err, (discord.Forbidden, discord.NotFound)):
            return DiscordGuildUnavailable(str(err))
        return DiscordConnectionError(str(err))
