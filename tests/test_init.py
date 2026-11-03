"""Tests for Discord Live setup and unload."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.discord_live.api import DiscordAuthError, DiscordConnectionError
from custom_components.discord_live.const import DOMAIN

from .conftest import setup_integration


async def test_setup_and_unload(hass: HomeAssistant, mock_config_entry, mock_client) -> None:
    """Test that the entry sets up, creates entities, and unloads cleanly."""
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("binary_sensor.discord_live_test_server") is not None
    assert hass.states.get("binary_sensor.discord_live_test_group_any_live") is not None
    assert hass.states.get("calendar.discord_live_test_group") is not None
    assert hass.states.get("sensor.discord_live_test_group_upcoming") is not None

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
    mock_client.close.assert_awaited()


async def test_setup_invalid_token_starts_reauth(
    hass: HomeAssistant, mock_config_entry, mock_client
) -> None:
    """A rejected token puts the entry in error and starts a reauth flow."""
    mock_client.login.side_effect = DiscordAuthError("bad token")
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(f["context"]["source"] == "reauth" for f in flows)
    mock_client.close.assert_awaited()


async def test_setup_connection_error_retries(
    hass: HomeAssistant, mock_config_entry, mock_client
) -> None:
    """A connection error at login makes setup retry later."""
    mock_client.login.side_effect = DiscordConnectionError("down")
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
