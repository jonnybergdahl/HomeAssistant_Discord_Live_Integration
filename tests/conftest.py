"""Shared fixtures for Discord Live tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.core import HomeAssistant

from custom_components.discord_live.api import (
    STATUS_ACTIVE,
    STATUS_SCHEDULED,
    DiscordEvent,
    GuildInfo,
)
from custom_components.discord_live.const import (
    CONF_BOT_TOKEN,
    CONF_GUILD_IDS,
    DOMAIN,
)

from pytest_homeassistant_custom_component.common import MockConfigEntry

GUILD_ID = 111
OTHER_GUILD_ID = 222


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations in all tests."""
    yield


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Create a mock config entry for a group with one server."""
    return MockConfigEntry(
        version=1,
        domain=DOMAIN,
        unique_id="test_group",
        data={CONF_BOT_TOKEN: "test-token", CONF_GUILD_IDS: [str(GUILD_ID)]},
        title="Test Group",
    )


def make_event(
    event_id: int = 1001,
    name: str = "Test Event",
    guild_id: int = GUILD_ID,
    scheduled_start: datetime | None = None,
    scheduled_end: datetime | None = None,
    live: bool = False,
) -> DiscordEvent:
    """Create a test DiscordEvent."""
    if scheduled_start is None:
        scheduled_start = datetime.now(timezone.utc) + timedelta(hours=1)
    return DiscordEvent(
        id=event_id,
        guild_id=guild_id,
        name=name,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        status=STATUS_ACTIVE if live else STATUS_SCHEDULED,
        url=f"https://discord.com/events/{guild_id}/{event_id}",
        entity_type="voice",
        channel_id=555,
        cover_url=f"https://cdn.discordapp.com/guild-events/{event_id}/cover.png",
        user_count=7,
    )


def make_guild(guild_id: int = GUILD_ID, name: str = "Test Server") -> GuildInfo:
    """Create a test GuildInfo."""
    return GuildInfo(
        id=guild_id,
        name=name,
        icon_url=f"https://cdn.discordapp.com/icons/{guild_id}/icon.png",
    )


@pytest.fixture
def mock_events():
    """Return a list of mock events for the default guild."""
    now = datetime.now(timezone.utc)
    return [
        make_event(event_id=1001, name="Morning Event", scheduled_start=now + timedelta(hours=2)),
        make_event(event_id=1002, name="Evening Event", scheduled_start=now + timedelta(hours=6)),
    ]


@pytest.fixture
def mock_client(mock_events):
    """Mock DiscordLiveClient everywhere the integration creates one."""
    client = MagicMock()
    client.login = AsyncMock(return_value="Test Bot")
    client.guilds = AsyncMock(
        return_value=[make_guild(), make_guild(OTHER_GUILD_ID, "Other Server")]
    )
    guilds = {GUILD_ID: make_guild(), OTHER_GUILD_ID: make_guild(OTHER_GUILD_ID, "Other Server")}
    client.guild_info = AsyncMock(side_effect=lambda gid: guilds[gid])
    client.events = AsyncMock(return_value=mock_events)
    client.close = AsyncMock()
    with (
        patch("custom_components.discord_live.DiscordLiveClient", return_value=client),
        patch("custom_components.discord_live.config_flow.DiscordLiveClient", return_value=client),
    ):
        yield client


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Add a config entry and set it up."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
