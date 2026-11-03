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


async def test_events_are_converted(discord_client) -> None:
    """ScheduledEvents are converted to DiscordEvents."""
    start = datetime(2026, 1, 1, 18, tzinfo=timezone.utc)
    scheduled = SimpleNamespace(
        id=1,
        guild_id=111,
        name="Game Night",
        description="Fun",
        start_time=start,
        end_time=None,
        status=discord.EventStatus.active,
        entity_type=discord.EntityType.stage_instance,
        location=None,
        channel_id=555,
        cover_image=SimpleNamespace(url="https://cdn/cover.png"),
        user_count=3,
        url="https://discord.com/events/111/1",
    )
    guild = MagicMock()
    guild.fetch_scheduled_events = AsyncMock(return_value=[scheduled])
    discord_client.fetch_guild = AsyncMock(return_value=guild)

    events = await DiscordLiveClient("token").events(111)

    assert len(events) == 1
    event = events[0]
    assert event.live
    assert event.entity_type == "stage"
    assert event.cover_url == "https://cdn/cover.png"
    assert event.scheduled_start == start
    guild.fetch_scheduled_events.assert_awaited_with(with_counts=True)


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
    discord_client.fetch_guild = AsyncMock(side_effect=error)
    with pytest.raises(expected):
        await DiscordLiveClient("token").events(111)
