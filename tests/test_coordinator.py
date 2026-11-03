"""Tests for the Discord Live coordinator."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from freezegun.api import FrozenDateTimeFactory

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.discord_live.api import (
    STATUS_COMPLETED,
    DiscordAuthError,
    DiscordConnectionError,
    DiscordGuildUnavailable,
)
from custom_components.discord_live.const import CONF_GUILD_IDS, DOMAIN

from .conftest import GUILD_ID, OTHER_GUILD_ID, make_event, setup_integration


async def _coordinator(hass, entry):
    await setup_integration(hass, entry)
    return entry.runtime_data.coordinator


async def test_initial_data(hass: HomeAssistant, mock_config_entry, mock_client, mock_events) -> None:
    """The first refresh loads guild info and events."""
    coordinator = await _coordinator(hass, mock_config_entry)

    assert coordinator.data.events == mock_events
    assert coordinator.data.ended == []
    assert coordinator.guild_name(GUILD_ID) == "Test Server"
    assert coordinator.live_events() == []
    mock_client.events.assert_awaited_with(GUILD_ID)


async def test_live_then_completed(
    hass: HomeAssistant, mock_config_entry, mock_client, freezer: FrozenDateTimeFactory
) -> None:
    """An event that goes live and then disappears is recorded as ended."""
    start = dt_util.utcnow() + timedelta(minutes=5)
    event = make_event(scheduled_start=start)
    mock_client.events.return_value = [event]
    coordinator = await _coordinator(hass, mock_config_entry)

    freezer.move_to(start)
    live = replace(event, status="active")
    mock_client.events.return_value = [live]
    await coordinator.async_refresh()
    assert coordinator.live_events() == [live]
    assert coordinator.is_event_active(live)

    ended_at = start + timedelta(minutes=40)
    freezer.move_to(ended_at)
    mock_client.events.return_value = []
    await coordinator.async_refresh()

    assert coordinator.live_events() == []
    assert len(coordinator.data.ended) == 1
    ended = coordinator.data.ended[0]
    assert ended.event.status == STATUS_COMPLETED
    assert ended.ended_at == ended_at
    # Still on the calendar, trimmed to the observed end.
    assert coordinator.relevant_events() == [ended.event]
    assert coordinator.event_end_time(ended.event) == ended_at
    assert not coordinator.is_event_active(ended.event)


async def test_recurring_event_moves_to_next_occurrence(
    hass: HomeAssistant, mock_config_entry, mock_client, freezer: FrozenDateTimeFactory
) -> None:
    """A live recurring event that returns as scheduled keeps both occurrences."""
    start = dt_util.utcnow()
    live = make_event(scheduled_start=start, live=True)
    mock_client.events.return_value = [live]
    coordinator = await _coordinator(hass, mock_config_entry)

    freezer.move_to(start + timedelta(hours=1))
    next_week = replace(live, status="scheduled", scheduled_start=start + timedelta(days=7))
    mock_client.events.return_value = [next_week]
    await coordinator.async_refresh()

    events = coordinator.relevant_events()
    assert len(events) == 2
    assert {e.scheduled_start for e in events} == {start, start + timedelta(days=7)}
    assert coordinator.live_events() == []


async def test_ended_events_are_pruned(
    hass: HomeAssistant, mock_config_entry, mock_client, freezer: FrozenDateTimeFactory
) -> None:
    """Ended events are dropped after the retention period."""
    mock_client.events.return_value = [make_event(scheduled_start=dt_util.utcnow(), live=True)]
    coordinator = await _coordinator(hass, mock_config_entry)

    mock_client.events.return_value = []
    await coordinator.async_refresh()
    assert len(coordinator.data.ended) == 1

    freezer.tick(timedelta(hours=25))
    await coordinator.async_refresh()
    assert coordinator.data.ended == []


async def test_end_time_precedence(hass: HomeAssistant, mock_config_entry, mock_client) -> None:
    """Discord's scheduled end is used, else the default duration."""
    coordinator = await _coordinator(hass, mock_config_entry)
    start = datetime(2026, 1, 1, 18, tzinfo=timezone.utc)

    assert coordinator.event_end_time(make_event(scheduled_start=start)) == start + timedelta(hours=2)
    end = start + timedelta(minutes=45)
    assert coordinator.event_end_time(make_event(scheduled_start=start, scheduled_end=end)) == end
    # An end before the start is ignored.
    bad = make_event(scheduled_start=start, scheduled_end=start - timedelta(minutes=1))
    assert coordinator.event_end_time(bad) == start + timedelta(hours=2)


async def test_unavailable_guild(hass: HomeAssistant, mock_client) -> None:
    """A guild the bot lost access to is marked unavailable; others still update."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="two",
        title="Two",
        data={"bot_token": "t", CONF_GUILD_IDS: [str(GUILD_ID), str(OTHER_GUILD_ID)]},
    )
    other_event = make_event(event_id=2001, guild_id=OTHER_GUILD_ID)

    async def events(guild_id):
        if guild_id == GUILD_ID:
            raise DiscordGuildUnavailable("kicked")
        return [other_event]

    mock_client.events.side_effect = events
    coordinator = await _coordinator(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert coordinator.unavailable_guilds == {GUILD_ID}
    assert coordinator.data.events == [other_event]


async def test_connection_error_keeps_previous_events(
    hass: HomeAssistant, mock_config_entry, mock_client, mock_events
) -> None:
    """A transient error keeps the last known events."""
    coordinator = await _coordinator(hass, mock_config_entry)

    mock_client.events.side_effect = DiscordConnectionError("down")
    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert coordinator.data.events == mock_events


async def test_connection_error_without_data_fails_setup(
    hass: HomeAssistant, mock_config_entry, mock_client
) -> None:
    """With nothing to fall back on, setup is retried."""
    mock_client.events.side_effect = DiscordConnectionError("down")
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    mock_client.close.assert_awaited()


async def test_auth_error_starts_reauth(hass: HomeAssistant, mock_config_entry, mock_client) -> None:
    """A token revoked while running starts a reauth flow."""
    coordinator = await _coordinator(hass, mock_config_entry)

    mock_client.events.side_effect = DiscordAuthError("revoked")
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert not coordinator.last_update_success
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(f["context"]["source"] == "reauth" for f in flows)
