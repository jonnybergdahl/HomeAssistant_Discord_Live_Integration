"""Constants for the Discord Live integration."""

from datetime import timedelta

DOMAIN = "discord_live"

CONF_GROUP_NAME = "group_name"
CONF_BOT_TOKEN = "bot_token"
CONF_GUILD_IDS = "guild_ids"

DEFAULT_UPDATE_INTERVAL = timedelta(minutes=1)
GUILD_INFO_INTERVAL = timedelta(minutes=30)
DEFAULT_EVENT_DURATION_HOURS = 2
# How long an ended event stays on the calendar after Discord stops returning it
ENDED_EVENT_RETENTION = timedelta(hours=24)
