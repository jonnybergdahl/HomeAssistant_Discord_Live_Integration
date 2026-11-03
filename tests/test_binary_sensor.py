"""Tests for the Discord Live binary sensors."""

from __future__ import annotations

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.discord_live.api import DiscordGuildUnavailable

from .conftest import GUILD_ID, make_event, setup_integration

GUILD_SENSOR = "binary_sensor.discord_live_test_server"
GROUP_SENSOR = "binary_sensor.discord_live_test_group_any_live"


async def test_sensors_off(hass: HomeAssistant, mock_config_entry, mock_client) -> None:
    """Without live events both sensors are off."""
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(GUILD_SENSOR)
    assert state.state == STATE_OFF
    assert state.name == "Test Group Test Server"
    assert state.attributes["guild_id"] == str(GUILD_ID)
    assert state.attributes["group"] == "Test Group"
    assert state.attributes["event_id"] is None
    assert state.attributes["entity_picture"].endswith("/icon.png")

    state = hass.states.get(GROUP_SENSOR)
    assert state.state == STATE_OFF
    assert state.name == "Test Group Live"
    assert state.attributes["live_count"] == 0
    assert "live_event_name" not in state.attributes


async def test_sensors_on(hass: HomeAssistant, mock_config_entry, mock_client) -> None:
    """A live event turns both sensors on and fills the attributes."""
    live = make_event(event_id=1001, name="Game Night", live=True)
    mock_client.events.return_value = [live, make_event(event_id=1002)]
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(GUILD_SENSOR)
    assert state.state == STATE_ON
    assert state.attributes["event_id"] == "1001"
    assert state.attributes["event_name"] == "Game Night"
    assert state.attributes["url"] == live.url
    assert state.attributes["event_type"] == "voice"
    assert state.attributes["interested_count"] == 7
    assert state.attributes["entity_picture"] == live.cover_url

    state = hass.states.get(GROUP_SENSOR)
    assert state.state == STATE_ON
    assert state.attributes["live_event_ids"] == ["1001"]
    assert state.attributes["live_count"] == 1
    assert state.attributes["live_guild_name"] == "Test Server"
    assert state.attributes["live_event_name"] == "Game Night"
    assert state.attributes["live_url"] == live.url


async def test_guild_sensor_unavailable(hass: HomeAssistant, mock_config_entry, mock_client) -> None:
    """A guild the bot lost access to shows as unavailable."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data.coordinator

    mock_client.events.side_effect = DiscordGuildUnavailable("kicked")
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(GUILD_SENSOR).state == STATE_UNAVAILABLE
    assert hass.states.get(GROUP_SENSOR).state == STATE_OFF


async def test_stale_guild_entity_removed(
    hass: HomeAssistant, mock_config_entry, mock_client
) -> None:
    """Entities for servers removed from the group are deleted on setup."""
    mock_config_entry.add_to_hass(hass)
    ent_reg = er.async_get(hass)
    stale = ent_reg.async_get_or_create(
        "binary_sensor",
        "discord_live",
        f"{mock_config_entry.entry_id}_999_live",
        config_entry=mock_config_entry,
    )
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert ent_reg.async_get(stale.entity_id) is None
    assert ent_reg.async_get(GUILD_SENSOR) is not None
