"""Recurrence rules of Discord scheduled events.

Discord only returns the next occurrence of a recurring event, together with
its ``recurrence_rule``. This module expands that rule into future occurrence
start times. Discord supports a small subset of iCalendar RRULEs:

- daily, optionally limited to a set of weekdays
- weekly or every other week, on one weekday
- monthly, on the nth weekday of the month
- yearly, on a month and day

Occurrences keep the UTC time of day of the rule's start.
"""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

FREQUENCY_YEARLY = 0
FREQUENCY_MONTHLY = 1
FREQUENCY_WEEKLY = 2
FREQUENCY_DAILY = 3

# Upper bound on periods (days, weeks, months or years) scanned for one
# expansion, so a malformed rule can never loop forever.
_MAX_PERIODS = 5000


@dataclass(frozen=True)
class RecurrenceRule:
    """The recurrence rule of a scheduled event."""

    start: datetime
    frequency: int
    interval: int = 1
    end: datetime | None = None
    count: int | None = None
    # 0 = Monday ... 6 = Sunday
    by_weekday: tuple[int, ...] = ()
    # (n, weekday) pairs, e.g. (2, 1) is the second Tuesday
    by_n_weekday: tuple[tuple[int, int], ...] = ()
    # 1 = January ... 12 = December
    by_month: tuple[int, ...] = ()
    by_month_day: tuple[int, ...] = ()

    @classmethod
    def from_payload(cls, data: dict[str, Any] | None) -> RecurrenceRule | None:
        """Parse the ``recurrence_rule`` object of a Discord API event."""
        if not data:
            return None
        start = dt_util.parse_datetime(data.get("start") or "")
        if start is None or data.get("frequency") is None:
            return None
        end = dt_util.parse_datetime(data["end"]) if data.get("end") else None
        return cls(
            start=start,
            frequency=int(data["frequency"]),
            interval=max(int(data.get("interval") or 1), 1),
            end=end,
            count=data.get("count"),
            by_weekday=tuple(data.get("by_weekday") or ()),
            by_n_weekday=tuple(
                (int(x["n"]), int(x["day"])) for x in data.get("by_n_weekday") or ()
            ),
            by_month=tuple(data.get("by_month") or ()),
            by_month_day=tuple(data.get("by_month_day") or ()),
        )

    def occurrences(self, after: datetime, until: datetime) -> list[datetime]:
        """Return occurrence starts with ``after < start < until``."""
        out: list[datetime] = []
        for index, start in enumerate(self._iter_starts()):
            if self.count is not None and index >= self.count:
                break
            if start >= until or (self.end is not None and start > self.end):
                break
            if start > after:
                out.append(start)
        return out

    def _at(self, day: date) -> datetime:
        """Combine a date with the rule's time of day."""
        return datetime.combine(day, self.start.timetz())

    def _iter_starts(self) -> Iterator[datetime]:
        """Yield every occurrence start, from the rule start onward."""
        first = self.start.date()
        for days in self._iter_periods(first):
            for day in sorted(days):
                if day >= first:
                    yield self._at(day)

    def _iter_periods(self, first: date) -> Iterator[list[date]]:
        """Yield the candidate dates of each period, in order."""
        if self.frequency == FREQUENCY_DAILY:
            for i in range(_MAX_PERIODS):
                day = first + timedelta(days=i * self.interval)
                if not self.by_weekday or day.weekday() in self.by_weekday:
                    yield [day]

        elif self.frequency == FREQUENCY_WEEKLY:
            weekdays = self.by_weekday or (first.weekday(),)
            monday = first - timedelta(days=first.weekday())
            for i in range(_MAX_PERIODS):
                week = monday + timedelta(weeks=i * self.interval)
                yield [week + timedelta(days=wd) for wd in weekdays]

        elif self.frequency == FREQUENCY_MONTHLY:
            for i in range(_MAX_PERIODS):
                months = first.month - 1 + i * self.interval
                year, month = first.year + months // 12, months % 12 + 1
                days = [
                    d
                    for n, wd in self.by_n_weekday
                    if (d := _nth_weekday(year, month, n, wd)) is not None
                ]
                month_days = self.by_month_day or (
                    () if self.by_n_weekday else (first.day,)
                )
                days.extend(
                    date(year, month, md)
                    for md in month_days
                    if md <= monthrange(year, month)[1]
                )
                yield days

        elif self.frequency == FREQUENCY_YEARLY:
            months = self.by_month or (first.month,)
            month_days = self.by_month_day or (first.day,)
            for i in range(_MAX_PERIODS):
                year = first.year + i * self.interval
                yield [
                    date(year, m, md)
                    for m in months
                    for md in month_days
                    if md <= monthrange(year, m)[1]
                ]


def _nth_weekday(year: int, month: int, n: int, weekday: int) -> date | None:
    """Return the nth weekday of a month, or None if the month has no such day."""
    first = date(year, month, 1)
    day = 1 + (weekday - first.weekday()) % 7 + (n - 1) * 7
    if day > monthrange(year, month)[1]:
        return None
    return date(year, month, day)
