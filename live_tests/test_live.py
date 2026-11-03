"""Live integration tests that make real calls to Discord.

Run with:  DISCORD_BOT_TOKEN=... pytest live_tests/ -v
These tests are NOT part of the normal test suite (they live outside tests/).
They make real network requests to Discord, and are skipped without a token.
"""

from __future__ import annotations

import os

import pytest

from custom_components.discord_live.api import DiscordLiveClient

TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

pytestmark = pytest.mark.skipif(not TOKEN, reason="DISCORD_BOT_TOKEN is not set")


async def test_login_guilds_and_events():
    """The bot can log in, list its servers, and fetch their events."""
    client = DiscordLiveClient(TOKEN)
    try:
        assert await client.login()
        guilds = await client.guilds()
        assert guilds, "The bot is not a member of any server"
        for guild in guilds:
            info = await client.guild_info(guild.id)
            assert info.name
            for event in await client.events(guild.id):
                assert event.guild_id == guild.id
                assert event.scheduled_start.tzinfo is not None
    finally:
        await client.close()
