"""Tests for recurrence rule expansion."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from custom_components.discord_live.recurrence import (
    FREQUENCY_DAILY,
    FREQUENCY_MONTHLY,
    FREQUENCY_WEEKLY,
    FREQUENCY_YEARLY,
    RecurrenceRule,
)

# Tuesday 6 January 2026, 18:00 UTC
START = datetime(2026, 1, 6, 18, tzinfo=timezone.utc)
UNTIL = START + timedelta(days=60)


def _dates(rule: RecurrenceRule, after=START, until=UNTIL) -> list[str]:
    return [d.strftime("%a %Y-%m-%d %H:%M") for d in rule.occurrences(after, until)]


def test_from_payload() -> None:
    """A Discord API recurrence_rule object is parsed."""
    rule = RecurrenceRule.from_payload(
        {
            "start": "2026-01-06T18:00:00+00:00",
            "end": None,
            "frequency": 1,
            "interval": 1,
            "by_weekday": None,
            "by_n_weekday": [{"n": 2, "day": 1}],
            "by_month": None,
            "by_month_day": None,
            "by_year_day": None,
            "count": None,
        }
    )
    assert rule == RecurrenceRule(
        start=START, frequency=FREQUENCY_MONTHLY, by_n_weekday=((2, 1),)
    )
    assert RecurrenceRule.from_payload(None) is None
    assert RecurrenceRule.from_payload({"frequency": 2}) is None


def test_weekly() -> None:
    """Weekly on Tuesday, excluding the current occurrence."""
    rule = RecurrenceRule(start=START, frequency=FREQUENCY_WEEKLY, by_weekday=(1,))
    assert _dates(rule, until=START + timedelta(days=22)) == [
        "Tue 2026-01-13 18:00",
        "Tue 2026-01-20 18:00",
        "Tue 2026-01-27 18:00",
    ]


def test_every_other_week() -> None:
    """Weekly with an interval of 2."""
    rule = RecurrenceRule(
        start=START, frequency=FREQUENCY_WEEKLY, interval=2, by_weekday=(1,)
    )
    assert _dates(rule, until=START + timedelta(days=43)) == [
        "Tue 2026-01-20 18:00",
        "Tue 2026-02-03 18:00",
        "Tue 2026-02-17 18:00",
    ]


def test_expansion_starts_after_current_occurrence() -> None:
    """Occurrences are computed from the rule start, then filtered."""
    rule = RecurrenceRule(start=START, frequency=FREQUENCY_WEEKLY, by_weekday=(1,))
    after = datetime(2026, 2, 3, 18, tzinfo=timezone.utc)
    assert _dates(rule, after=after, until=after + timedelta(days=8)) == [
        "Tue 2026-02-10 18:00",
    ]


def test_daily_on_weekdays() -> None:
    """Daily, limited to Monday to Friday."""
    rule = RecurrenceRule(
        start=START, frequency=FREQUENCY_DAILY, by_weekday=(0, 1, 2, 3, 4)
    )
    assert _dates(rule, until=START + timedelta(days=7, hours=1)) == [
        "Wed 2026-01-07 18:00",
        "Thu 2026-01-08 18:00",
        "Fri 2026-01-09 18:00",
        "Mon 2026-01-12 18:00",
        "Tue 2026-01-13 18:00",
    ]


def test_monthly_nth_weekday() -> None:
    """Monthly on the first Tuesday."""
    rule = RecurrenceRule(
        start=START, frequency=FREQUENCY_MONTHLY, by_n_weekday=((1, 1),)
    )
    assert _dates(rule, until=START + timedelta(days=100)) == [
        "Tue 2026-02-03 18:00",
        "Tue 2026-03-03 18:00",
        "Tue 2026-04-07 18:00",
    ]


def test_monthly_fifth_weekday_skips_short_months() -> None:
    """A fifth weekday is skipped in months that don't have one."""
    start = datetime(2026, 3, 31, 18, tzinfo=timezone.utc)  # 5th Tuesday
    rule = RecurrenceRule(
        start=start, frequency=FREQUENCY_MONTHLY, by_n_weekday=((5, 1),)
    )
    assert _dates(rule, after=start, until=start + timedelta(days=200)) == [
        "Tue 2026-06-30 18:00",
        "Tue 2026-09-29 18:00",
    ]


def test_yearly() -> None:
    """Yearly on a month and day."""
    rule = RecurrenceRule(
        start=START, frequency=FREQUENCY_YEARLY, by_month=(1,), by_month_day=(6,)
    )
    assert _dates(rule, until=START + timedelta(days=800)) == [
        "Wed 2027-01-06 18:00",
        "Thu 2028-01-06 18:00",
    ]


def test_count_and_end() -> None:
    """A count or end date stops the series."""
    rule = RecurrenceRule(
        start=START, frequency=FREQUENCY_WEEKLY, by_weekday=(1,), count=3
    )
    assert len(_dates(rule)) == 2  # the first of the 3 is the current occurrence
    rule = RecurrenceRule(
        start=START,
        frequency=FREQUENCY_WEEKLY,
        by_weekday=(1,),
        end=START + timedelta(days=14),
    )
    assert len(_dates(rule)) == 2
