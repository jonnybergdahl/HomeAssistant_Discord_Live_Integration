"""Tests for the Discord Live upcoming events sensor."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .conftest import make_event, setup_integration

SENSOR = "sensor.discord_live_test_group_upcoming"


async def test_upcoming_sensor(hass: HomeAssistant, mock_config_entry, mock_client, mock_events) -> None:
    """The sensor counts upcoming events and flattens the next five."""
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(SENSOR)
    assert state.state == "2"
    assert state.name == "Test Group Upcoming"
    assert state.attributes["event_0_title"] == "Morning Event"
    assert state.attributes["event_0_event_id"] == "1001"
    assert state.attributes["event_0_guild"] == "Test Server"
    assert state.attributes["event_0_start"] == mock_events[0].scheduled_start.isoformat()
    assert state.attributes["event_0_duration"] == 120
    assert state.attributes["event_0_live"] is False
    assert state.attributes["event_1_title"] == "Evening Event"
    assert state.attributes["event_2_title"] == ""
    assert state.attributes["event_4_duration"] == 0


async def test_upcoming_sensor_includes_live_and_truncates(
    hass: HomeAssistant, mock_config_entry, mock_client
) -> None:
    """Live events count as upcoming, past events don't, and long names are cut."""
    now = dt_util.utcnow()
    mock_client.events.return_value = [
        make_event(event_id=1, name="x" * 100, scheduled_start=now - timedelta(hours=5), live=True),
        make_event(event_id=2, scheduled_start=now - timedelta(hours=5)),
        make_event(event_id=3, scheduled_start=now + timedelta(hours=1)),
    ]
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(SENSOR)
    assert state.state == "2"
    assert state.attributes["event_0_event_id"] == "1"
    assert state.attributes["event_0_live"] is True
    assert len(state.attributes["event_0_title"]) == 80
    assert state.attributes["event_0_title"].endswith("...")
    assert state.attributes["event_1_event_id"] == "3"
