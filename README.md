# Discord Live for Home Assistant

A Home Assistant custom integration that monitors Discord servers for **scheduled events**. Servers are organised into **groups** (e.g. "Gaming", "Community"): each group becomes a device in Home Assistant with a calendar of its upcoming events, a binary sensor for every server in the group, and an aggregate "any server live" binary sensor.

An event counts as **live** while Discord reports it as *active*: when someone starts it, or when Discord starts it automatically at its scheduled time.

## Features

- **Server groups**: organise the servers you monitor into named groups (one config entry per group)
- **Per-group calendar** listing scheduled events for that group's servers
- **Per-server binary sensor** that turns on when an event on that server is live
- **Aggregate group sensor** that turns on when *any* server in the group has a live event
- Edit the servers in a group at any time via the integration's options
- Polls Discord's REST API every minute. No gateway connection and no privileged intents.

## Bot setup

The integration reads events through a Discord bot that you create yourself.

1. Open the [Discord Developer Portal](https://discord.com/developers/applications) and click **New Application**.
2. On the **Bot** page, click **Reset Token** and copy the token. You will paste it into Home Assistant.
3. On the **OAuth2** page, use the URL generator: select the scope **`bot`** and the permission **View Channels**, then open the generated URL and add the bot to each server you want to monitor.

No privileged gateway intents are needed. Events tied to a channel the bot can't view are not returned by Discord, so make sure the bot can see the channels your events use.

## Installation

### HACS (recommended)

Click the button to add this repository to HACS.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jonnybergdahl&category=Integration&repository=HomeAssistant_Discord_Live_Integration)

Then restart Home Assistant.

You can also do the above manually:
1. Open HACS in your Home Assistant instance
2. Click the three-dot menu in the top right corner and select **Custom repositories**
3. Add `https://github.com/jonnybergdahl/HomeAssistant_Discord_Live_Integration` as a custom repository with category **Integration**
4. Click **Add**
5. Search for **Discord Live** in HACS and click **Download**
6. Restart Home Assistant

### Manual

1. Copy the `custom_components/discord_live` folder into your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Setup

Click the button to add a Discord Live server group to Home Assistant.

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=discord_live)

1. Pick a **group name** (e.g. `Gaming`, `Community`). This becomes the device name in Home Assistant.
2. Paste the **bot token**.
3. Select the **servers** to include in the group. The list shows every server the bot is a member of.
4. Click **Submit**.

You can also set it up manually:

1. Go to **Settings** > **Devices & services** > **Add integration**
2. Search for **Discord Live**
3. Enter a group name and the bot token, then select the servers
4. Click **Submit**

 > To add or remove servers later, open the integration's **Configure** action and edit the selection. Changes take effect immediately.

Create additional groups the same way. Each group is independent and gets its own device, calendar and sensors, and groups can share the same bot token.

If the bot token is reset or revoked, Home Assistant asks you to re-authenticate and enter the new token.

## Entities

Every group produces one Home Assistant device containing:

### Calendar

One **`calendar.discord_live_<group>`** entity listing the scheduled events for that group's servers.

Each event uses `<server> - <event name>` as its summary, the event description followed by the event link as its description, and the external location (for external events) as its location. An event uses the end time set in Discord, or lasts 2 hours if none is set. A live event stays open while it is live. Once an event ends, its end time is trimmed to when it actually ended, and it stays on the calendar for 24 hours.

### Per-server binary sensors

One **`binary_sensor.discord_live_<server>`** per server in the group. The sensor turns **on** while any event on that server is live, and **off** otherwise. It shows as **unavailable** if the bot loses access to the server.

The entity picture shows the live event's cover image while live, and the server icon otherwise.

| Attribute | Description |
|---|---|
| `guild_id` | Server ID |
| `guild_name` | Server name |
| `group` | Name of the group this server belongs to |
| `event_id` | ID of the live event |
| `event_name` | Name of the live event |
| `url` | Link to the live event |
| `event_start` | Start time of the live event (ISO 8601) |
| `event_type` | `stage`, `voice` or `external` |
| `location` | Location of an external event |
| `interested_count` | Number of members marked as interested |

The event attributes are populated only while the server has a live event; otherwise they are `null`.

### Group aggregate sensor

One **`binary_sensor.discord_live_<group>_any_live`** per group. Turns **on** whenever any server in the group has a live event.

| Attribute | Description |
|---|---|
| `group` | Group name |
| `guild_ids` | IDs of the servers in the group |
| `live_event_ids` | IDs of events currently live |
| `live_count` | Number of events currently live |

When at least one event is live, these additional attributes describe the first live event:

| Attribute | Description |
|---|---|
| `live_guild_id` | ID of the live server |
| `live_guild_name` | Name of the live server |
| `live_event_name` | Name of the live event |
| `live_url` | Link to the live event |

### Upcoming events sensor (for ESPHome)

One **`sensor.discord_live_<group>_upcoming`** per group. The state is the number of upcoming or currently live events in the group.

This sensor is designed for easy consumption by ESPHome devices (e.g. using `text_sensor` with `attribute` mapping). It exposes the next 5 events, ordered by start time, as a flat list of attributes.

| Attribute | Description |
|---|---|
| `event_i_title` | Event name (truncated to 80 chars) |
| `event_i_start` | Scheduled start time (ISO 8601 UTC) |
| `event_i_event_id` | Discord event ID |
| `event_i_guild` | Server name |
| `event_i_live` | Whether the event is live |
| `event_i_duration` | Duration in minutes |

...where `i` is 0 to 4. Unused slots use empty strings `""` for the text fields, `false` for `event_i_live` and `0` for `event_i_duration`.

## Usage

To get a single sensor that tells if *any* server across *all* groups is live, create a binary Template sensor:

Show as: Running<br/>
State:
```yaml
{{ integration_entities('discord_live')
   | select('search', '_any_live$')
   | select('is_state', 'on')
   | list | count > 0 }}
```

## Development

```bash
uv sync
uv run pytest
```

Live tests against the real Discord API are skipped unless a bot token is set:

```bash
DISCORD_BOT_TOKEN=... uv run pytest live_tests -v
```
