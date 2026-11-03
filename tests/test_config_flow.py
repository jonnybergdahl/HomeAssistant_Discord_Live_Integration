"""Tests for the Discord Live config and options flows."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.discord_live.api import DiscordAuthError, DiscordConnectionError
from custom_components.discord_live.const import (
    CONF_BOT_TOKEN,
    CONF_GROUP_NAME,
    CONF_GUILD_IDS,
    DOMAIN,
)

from .conftest import GUILD_ID, OTHER_GUILD_ID, setup_integration

USER_INPUT = {CONF_GROUP_NAME: "Gaming", CONF_BOT_TOKEN: " token "}


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_full_flow(hass: HomeAssistant, mock_client) -> None:
    """Test the happy path through both steps."""
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "guilds"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_GUILD_IDS: [str(GUILD_ID), str(OTHER_GUILD_ID)]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Gaming"
    assert result["data"] == {
        CONF_BOT_TOKEN: "token",
        CONF_GUILD_IDS: [str(GUILD_ID), str(OTHER_GUILD_ID)],
    }
    assert result["result"].unique_id == "gaming"
    mock_client.close.assert_awaited()


async def test_invalid_auth(hass: HomeAssistant, mock_client) -> None:
    """Test a rejected bot token."""
    mock_client.login.side_effect = DiscordAuthError("bad")
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_cannot_connect(hass: HomeAssistant, mock_client) -> None:
    """Test Discord being unreachable."""
    mock_client.guilds.side_effect = DiscordConnectionError("down")
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_no_guilds(hass: HomeAssistant, mock_client) -> None:
    """Test a bot that is not in any server."""
    mock_client.guilds.return_value = []
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "no_guilds"}


async def test_empty_group_name(hass: HomeAssistant, mock_client) -> None:
    """Test a blank group name."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_GROUP_NAME: "  ", CONF_BOT_TOKEN: "token"}
    )
    assert result["errors"] == {"base": "no_group_name"}


async def test_no_guilds_selected(hass: HomeAssistant, mock_client) -> None:
    """Test submitting the server step without a selection."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_GUILD_IDS: []}
    )
    assert result["step_id"] == "guilds"
    assert result["errors"] == {"base": "no_guilds_selected"}


async def test_already_configured(hass: HomeAssistant, mock_client, mock_config_entry) -> None:
    """Test adding a group whose name is already in use."""
    mock_config_entry.add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_GROUP_NAME: "Test Group", CONF_BOT_TOKEN: "token"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(hass: HomeAssistant, mock_client, mock_config_entry) -> None:
    """Test replacing a rejected token."""
    await setup_integration(hass, mock_config_entry)
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    mock_client.login.side_effect = DiscordAuthError("bad")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BOT_TOKEN: "still-bad"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    mock_client.login.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BOT_TOKEN: "new-token"}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_BOT_TOKEN] == "new-token"


async def test_options_flow(hass: HomeAssistant, mock_client, mock_config_entry) -> None:
    """Test editing the servers in a group."""
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_GUILD_IDS: [str(GUILD_ID), str(OTHER_GUILD_ID)]}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.data[CONF_GUILD_IDS] == [str(GUILD_ID), str(OTHER_GUILD_ID)]
    assert hass.states.get("binary_sensor.discord_live_other_server") is not None


async def test_options_flow_cannot_connect(
    hass: HomeAssistant, mock_client, mock_config_entry
) -> None:
    """Test the options flow aborting when the guild list cannot be fetched."""
    await setup_integration(hass, mock_config_entry)
    mock_client.guilds.side_effect = DiscordConnectionError("down")

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"
