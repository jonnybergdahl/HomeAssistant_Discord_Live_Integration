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

The integration reads events through a Discord bot that you create yourself. The bot only reads scheduled events: it never posts messages, joins voice channels or reads chat, and it needs no privileged gateway intents.

A bot can only see the events of servers it has been added to, and only someone with the **Manage Server** permission can add it. You can add it to your own servers yourself. For anyone else's server, you send the invite link to someone who runs it.

### 1. Create the bot

1. Open the [Discord Developer Portal](https://discord.com/developers/applications) and click **New Application**. Give it a name, e.g. `Home Assistant Events`. Server members will see this name in the member list.
2. On the **General Information** page, copy the **Application ID**. You need it for the invite link.
3. On the **Bot** page:
    - Click **Reset Token** and copy the token. You will paste it into Home Assistant. Keep it secret: anyone with the token can act as your bot. If it leaks, reset it again and update Home Assistant (it asks for the new token).
    - Make sure **Public Bot** is turned on if you want other server admins to be able to add it. With it off, only you can add the bot.
    - Leave all **Privileged Gateway Intents** turned off.

### 2. Create the invite link

Replace `YOUR_APP_ID` with the Application ID from step 1:

```
https://discord.com/oauth2/authorize?client_id=YOUR_APP_ID&scope=bot&permissions=1024&integration_type=0
```

- `scope=bot` adds it as a bot user.
- `permissions=1024` is **View Channels** and nothing else.
- `integration_type=0` makes it a server install.

You can also build the same link in the portal: on the **OAuth2** page, open the **URL Generator**, tick the **`bot`** scope, then tick **View Channels** under Bot Permissions, and copy the generated URL at the bottom.

### 3. Add the bot to your own server

Open the invite link, pick the server, and click **Authorize**. Only servers where you have **Manage Server** are listed. Repeat for each server you want to monitor.

### 4. Ask a server admin to add it

To monitor a server you don't run, send the invite link to its owner or an admin. Something like:

> Hi! I'd like to show the events of this server in my Home Assistant (calendar and a "live now" indicator). Could you add my bot? It only has the View Channels permission. It can't post, join voice or read messages, it just reads the scheduled events list.
>
> https://discord.com/oauth2/authorize?client_id=YOUR_APP_ID&scope=bot&permissions=1024&integration_type=0

Once they have authorized it, the server shows up in the integration's server list. Open the group's **Configure** action in Home Assistant and select it.

### 5. Private channels

Discord only returns events whose channel the bot can see. The bot sees public channels straight away. If an event is in a private stage or voice channel, someone with Manage Channels needs to open that channel's settings, go to **Permissions**, add the bot (or its role, named after the bot) and allow **View Channel**. External events (with a link or place as the location) aren't tied to a channel, so they need nothing extra.

### Trying it out without a server

If you don't run any server, create your own for testing. In Discord, click **+** (Add a Server) at the bottom of the server list, choose **Create My Own**, and invite the bot with the link above. Then create an event (click the server name, then **Create Event**) that starts in a few minutes, and click **Start Event** to see the sensors turn on.

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

**Recurring events** are shown with all their future occurrences. Discord only returns the next occurrence, so later ones are calculated from the event's repeat rule, and they keep the duration of the next occurrence. A single later occurrence that was moved or cancelled in Discord still shows at its regular time. Those one-off changes aren't part of Discord's documented API, so they aren't handled.

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

One **`sensor.discord_live_<group>_upcoming`** per group. The state is the number of upcoming or currently live events in the group, counting each repeat of a recurring event within the next 30 days.

This sensor is designed for easy consumption by ESPHome devices (e.g. using `text_sensor` with `attribute` mapping). It exposes the next 5 events, ordered by start time, as a flat list of attributes. Repeats of recurring events are included for the next 30 days, so a weekly event shows up about four times.

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
