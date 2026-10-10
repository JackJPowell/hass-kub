"""Helpers for KUB account data."""

from datetime import UTC, date, datetime, timedelta, tzinfo
from typing import Any


def get_service_utility(account: dict[str, Any], service_key: str) -> str:
    """Return the utility name from either supported account data format."""
    service = account[service_key]
    if isinstance(service, dict):
        return service["utility"]
    return service_key.rsplit("_", 1)[0]


def get_service_id(account: dict[str, Any], service_key: str) -> str:
    """Return the service-point ID from either supported account data format."""
    service = account[service_key]
    if isinstance(service, dict):
        return service["id"]
    return service


def hourly_series(
    utility_data: dict[str, dict[str, dict[str, Any]]],
    tz: tzinfo,
    latest_complete_date: date,
) -> list[tuple[datetime, float, float]]:
    """Flatten KUB's per-day usage into chronological (start, usage, cost) rows.

    KUB's ``readDateTime`` labels the *end* of each hourly interval, and the
    reading that closes a day (00:00 of the next date) is filed under that day's
    header. Rows therefore have to be shifted back an hour and sorted by their
    real start time; accumulating in key order puts that closing reading first
    and corrupts the cumulative sum.

    Days after ``latest_complete_date`` and days with fewer than 20 hourly
    readings are skipped because KUB routinely publishes and revises them late.
    """
    rows: dict[datetime, tuple[float, float]] = {}
    for day_key, day in utility_data.items():
        if date.fromisoformat(day_key) > latest_complete_date or len(day) < 20:
            continue
        for hour in day.values():
            label = datetime.fromisoformat(hour["readDateTime"]).replace(tzinfo=None)
            # Convert to UTC before subtracting so daylight saving is handled.
            start = label.replace(tzinfo=tz).astimezone(UTC) - timedelta(
                hours=1
            )
            rows[start] = (hour.get("utilityUsed") or 0.0, hour.get("cost") or 0.0)
    return [(start, usage, cost) for start, (usage, cost) in sorted(rows.items())]


def build_statistics(
    series: list[tuple[datetime, float, float]],
    multiplier: float = 1.0,
    base_usage: float = 0.0,
    base_cost: float = 0.0,
) -> tuple[list[tuple[datetime, float, float]], list[tuple[datetime, float, float]]]:
    """Return (consumption, cost) rows of (start, state, cumulative sum).

    ``base_usage`` and ``base_cost`` are the stored cumulative sums of the hour just
    before the first row, so a re-imported window continues the existing series
    instead of restarting it at zero.
    """
    usage_sum, cost_sum = base_usage, base_cost
    consumption: list[tuple[datetime, float, float]] = []
    cost: list[tuple[datetime, float, float]] = []
    for start, usage, hour_cost in series:
        usage *= multiplier
        hour_cost *= multiplier
        usage_sum += usage
        cost_sum += hour_cost
        consumption.append((start, usage, usage_sum))
        cost.append((start, hour_cost, cost_sum))
    return consumption, cost
