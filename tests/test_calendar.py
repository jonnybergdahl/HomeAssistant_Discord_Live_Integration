"""Tests for the Discord Live calendar."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from dataclasses import replace

from custom_components.discord_live.recurrence import FREQUENCY_WEEKLY, RecurrenceRule

from .conftest import make_event, setup_integration

CALENDAR = "calendar.discord_live_test_group"


async def _get_events(hass: HomeAssistant, start, end) -> list[dict]:
    result = await hass.services.async_call(
        "calendar",
        "get_events",
        {"entity_id": CALENDAR, "start_date_time": start, "end_date_time": end},
        blocking=True,
        return_response=True,
    )
    return result[CALENDAR]["events"]


async def test_calendar_state_and_events(
    hass: HomeAssistant, mock_config_entry, mock_client, mock_events
) -> None:
    """Scheduled events are listed with the server name in the summary."""
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(CALENDAR)
    assert state.name == "Test Group Events"
    assert state.attributes["message"] == "Test Server - Morning Event"

    now = dt_util.utcnow()
    events = await _get_events(hass, now, now + timedelta(days=1))
    assert [e["summary"] for e in events] == [
        "Test Server - Morning Event",
        "Test Server - Evening Event",
    ]
    assert events[0]["description"] == mock_events[0].url


async def test_calendar_uses_scheduled_end_and_description(
    hass: HomeAssistant, mock_config_entry, mock_client
) -> None:
    """Discord's end time and description are carried over."""
    start = dt_util.utcnow() + timedelta(hours=1)
    event = make_event(scheduled_start=start, scheduled_end=start + timedelta(minutes=45))
    event.description = "Bring snacks"
    event.location = "https://example.com/stream"
    mock_client.events.return_value = [event]
    await setup_integration(hass, mock_config_entry)

    events = await _get_events(hass, start - timedelta(hours=1), start + timedelta(hours=3))
    assert len(events) == 1
    assert dt_util.parse_datetime(events[0]["end"]) == start + timedelta(minutes=45)
    assert events[0]["description"] == f"Bring snacks\n\n{event.url}"
    assert events[0]["location"] == "https://example.com/stream"


async def test_live_event_stays_open(
    hass: HomeAssistant, mock_config_entry, mock_client
) -> None:
    """A live event past its planned end is kept open."""
    start = dt_util.utcnow() - timedelta(hours=3)
    mock_client.events.return_value = [make_event(scheduled_start=start, live=True)]
    await setup_integration(hass, mock_config_entry)

    now = dt_util.utcnow()
    events = await _get_events(hass, now - timedelta(hours=4), now + timedelta(hours=1))
    assert len(events) == 1
    assert dt_util.parse_datetime(events[0]["end"]) >= now + timedelta(minutes=29)
    assert hass.states.get(CALENDAR).state == "on"


async def test_ended_event_is_trimmed(
    hass: HomeAssistant, mock_config_entry, mock_client, freezer: FrozenDateTimeFactory
) -> None:
    """An event that ended early keeps its observed end on the calendar."""
    start = dt_util.utcnow()
    mock_client.events.return_value = [make_event(scheduled_start=start, live=True)]
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data.coordinator

    freezer.move_to(start + timedelta(minutes=30))
    mock_client.events.return_value = []
    await coordinator.async_refresh()

    events = await _get_events(hass, start - timedelta(hours=1), start + timedelta(hours=3))
    assert len(events) == 1
    assert dt_util.parse_datetime(events[0]["end"]) == start + timedelta(minutes=30)


async def test_recurring_event_occurrences(
    hass: HomeAssistant, mock_config_entry, mock_client
) -> None:
    """Future occurrences of a recurring event are expanded from its rule."""
    start = dt_util.utcnow().replace(microsecond=0) + timedelta(hours=1)
    rule = RecurrenceRule(
        start=start, frequency=FREQUENCY_WEEKLY, by_weekday=(start.weekday(),)
    )
    event = replace(
        make_event(scheduled_start=start, scheduled_end=start + timedelta(minutes=90)),
        recurrence=rule,
    )
    mock_client.events.return_value = [event]
    await setup_integration(hass, mock_config_entry)

    events = await _get_events(hass, start - timedelta(hours=1), start + timedelta(days=22))
    starts = [dt_util.parse_datetime(e["start"]) for e in events]
    assert starts == [start + timedelta(weeks=w) for w in range(4)]
    for e in events:
        duration = dt_util.parse_datetime(e["end"]) - dt_util.parse_datetime(e["start"])
        assert duration == timedelta(minutes=90)

    # The upcoming sensor lists repeats up to 30 days ahead.
    state = hass.states.get("sensor.discord_live_test_group_upcoming")
    assert state.state == "5"
    for i in range(5):
        assert dt_util.parse_datetime(state.attributes[f"event_{i}_start"]) == start + timedelta(weeks=i)
        assert state.attributes[f"event_{i}_duration"] == 90
