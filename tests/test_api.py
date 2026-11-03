"""Tests for the discord.py wrapper."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from custom_components.discord_live.api import (
    DiscordAuthError,
    DiscordConnectionError,
    DiscordGuildUnavailable,
    DiscordLiveClient,
)


def _http_error(cls: type[discord.HTTPException], status: int) -> discord.HTTPException:
    return cls(MagicMock(status=status, reason="error"), "error")


@pytest.fixture
def discord_client():
    """Patch the discord.py Client used by DiscordLiveClient."""
    client = MagicMock()
    client.login = AsyncMock()
    client.close = AsyncMock()
    client.user = SimpleNamespace(name="Test Bot")
    with patch("custom_components.discord_live.api.discord.Client", return_value=client):
        yield client


async def test_login(discord_client) -> None:
    """Login returns the bot name; close closes the client."""
    client = DiscordLiveClient("token")
    assert await client.login() == "Test Bot"
    discord_client.login.assert_awaited_with("token")
    await client.close()
    discord_client.close.assert_awaited_once()


async def test_login_failure(discord_client) -> None:
    """A rejected token raises DiscordAuthError."""
    discord_client.login.side_effect = discord.LoginFailure("bad")
    with pytest.raises(DiscordAuthError):
        await DiscordLiveClient("token").login()


def _payload(**overrides) -> dict:
    """A raw scheduled event payload, as returned by the Discord API."""
    data = {
        "id": "1",
        "guild_id": "111",
        "channel_id": "555",
        "creator_id": "9",
        "name": "Game Night",
        "description": "Fun",
        "scheduled_start_time": "2026-01-06T18:00:00+00:00",
        "scheduled_end_time": None,
        "privacy_level": 2,
        "status": 2,
        "entity_type": 1,
        "entity_id": None,
        "entity_metadata": None,
        "user_count": 3,
        "image": "abc123",
        "recurrence_rule": None,
    }
    data.update(overrides)
    return data


async def test_events_are_converted(discord_client) -> None:
    """Raw payloads are converted to DiscordEvents."""
    discord_client.http.get_scheduled_events = AsyncMock(return_value=[_payload()])

    events = await DiscordLiveClient("token").events(111)

    discord_client.http.get_scheduled_events.assert_awaited_with(111, True)
    assert len(events) == 1
    event = events[0]
    assert event.id == 1
    assert event.guild_id == 111
    assert event.live
    assert event.entity_type == "stage"
    assert event.scheduled_start == datetime(2026, 1, 6, 18, tzinfo=timezone.utc)
    assert event.scheduled_end is None
    assert event.cover_url.startswith("https://cdn.discordapp.com/guild-events/1/abc123")
    assert event.url == "https://discord.com/events/111/1"
    assert event.user_count == 3
    assert event.recurrence is None


async def test_recurrence_rule_is_kept(discord_client) -> None:
    """The recurrence rule that discord.py drops is parsed from the payload."""
    rule = {
        "start": "2026-01-06T18:00:00+00:00",
        "end": None,
        "frequency": 2,
        "interval": 1,
        "by_weekday": [1],
        "by_n_weekday": None,
        "by_month": None,
        "by_month_day": None,
        "by_year_day": None,
        "count": None,
    }
    discord_client.http.get_scheduled_events = AsyncMock(
        return_value=[_payload(status=1, recurrence_rule=rule)]
    )

    event = (await DiscordLiveClient("token").events(111))[0]

    assert not event.live
    assert event.recurrence is not None
    assert event.recurrence.frequency == 2
    assert event.recurrence.by_weekday == (1,)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_http_error(discord.Forbidden, 403), DiscordGuildUnavailable),
        (_http_error(discord.NotFound, 404), DiscordGuildUnavailable),
        (_http_error(discord.HTTPException, 401), DiscordAuthError),
        (_http_error(discord.DiscordServerError, 503), DiscordConnectionError),
    ],
)
async def test_http_errors_are_mapped(discord_client, error, expected) -> None:
    """discord.py HTTP errors map to the integration's exceptions."""
    discord_client.http.get_scheduled_events = AsyncMock(side_effect=error)
    with pytest.raises(expected):
        await DiscordLiveClient("token").events(111)
    discord_client.fetch_guild = AsyncMock(side_effect=error)
    with pytest.raises(expected):
        await DiscordLiveClient("token").guild_info(111)
