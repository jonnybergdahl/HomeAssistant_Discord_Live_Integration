"""Shared entity helpers for the Discord Live integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

if TYPE_CHECKING:
    from . import DiscordLiveConfigEntry


def group_device_info(entry: DiscordLiveConfigEntry) -> DeviceInfo:
    """Return the shared device info for a group's entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        entry_type=DeviceEntryType.SERVICE,
    )
