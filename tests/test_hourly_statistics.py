"""Hourly statistics: timestamps are hour-ending and sums must be chronological.

Run with: pip install pytest && pytest tests
helpers.py has no Home Assistant imports, so it is loaded by path.
"""

import importlib.util
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_HELPERS = Path(__file__).parents[1] / "custom_components/kub/helpers.py"
_spec = importlib.util.spec_from_file_location("kub_helpers", _HELPERS)
helpers = importlib.util.module_from_spec(_spec)
sys.modules["kub_helpers"] = helpers
_spec.loader.exec_module(helpers)

TZ = ZoneInfo("America/New_York")
CUTOFF = date(2030, 1, 1)


def kub_day(day, values, costs=None):
    """One day as KUB files it: hour-ending labels 01:00..00:00 under the day's header.

    The closing reading (label 00:00 of the next date) is stored under the key
    "00:00:00", which sorts before every other key of that day.
    """
    out = {}
    for hour, value in enumerate(values, start=1):
        label = datetime.combine(day, datetime.min.time()) + timedelta(hours=hour)
        out[label.strftime("%H:%M:%S")] = {
            "readDateTime": label.isoformat(),
            "utilityUsed": value,
            "cost": (costs or values)[hour - 1] / 10,
        }
    return out


def three_days():
    d1, d2, d3 = date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3)
    return {
        d1.isoformat(): kub_day(d1, [1.0] * 24),
        d2.isoformat(): kub_day(d2, [2.0] * 24),
        d3.isoformat(): kub_day(d3, [3.0] * 24),
    }


def test_interval_starts_an_hour_before_its_label():
    series = helpers.hourly_series(three_days(), TZ, CUTOFF)
    # The first label of the first day is 01:00, so its interval starts at 00:00 local.
    assert series[0][0].astimezone(TZ) == datetime(2026, 3, 1, 0, 0, tzinfo=TZ)
    # The closing reading of the last day (label 00:00 of the next date) starts at 23:00.
    assert series[-1][0].astimezone(TZ) == datetime(2026, 3, 3, 23, 0, tzinfo=TZ)


def test_rows_are_chronological_and_hourly():
    series = helpers.hourly_series(three_days(), TZ, CUTOFF)
    starts = [row[0] for row in series]
    assert len(starts) == 72
    assert all(b - a == timedelta(hours=1) for a, b in zip(starts, starts[1:]))


def test_cumulative_sum_never_decreases_and_ends_at_the_total():
    series = helpers.hourly_series(three_days(), TZ, CUTOFF)
    consumption, cost = helpers.build_statistics(series)
    sums = [total for _, _, total in consumption]
    assert all(b >= a for a, b in zip(sums, sums[1:]))
    assert sums[-1] == 24 * (1.0 + 2.0 + 3.0)
    assert round(cost[-1][2], 6) == 24 * (1.0 + 2.0 + 3.0) / 10


def test_daily_totals_by_local_start_day_match_kub_days():
    series = helpers.hourly_series(three_days(), TZ, CUTOFF)
    consumption, _ = helpers.build_statistics(series)
    per_day = {}
    for start, state, _ in consumption:
        day = start.astimezone(TZ).date()
        per_day[day] = per_day.get(day, 0.0) + state
    assert per_day == {date(2026, 3, 1): 24.0, date(2026, 3, 2): 48.0, date(2026, 3, 3): 72.0}


def test_incomplete_and_too_recent_days_are_skipped():
    data = three_days()
    data["2026-03-02"] = dict(list(data["2026-03-02"].items())[:19])  # fewer than 20 readings
    series = helpers.hourly_series(data, TZ, date(2026, 3, 2))  # 03-03 is after the cutoff
    assert {row[0].astimezone(TZ).date() for row in series} == {date(2026, 3, 1)}


def test_daylight_saving_day_is_handled():
    """2026-03-08 has 23 hours: there is no 02:00 label in local wall-clock time."""
    day = date(2026, 3, 8)
    labels = [h for h in range(1, 25) if h != 2]  # 01:00, 03:00, ..., 24:00
    data = {
        day.isoformat(): {
            (datetime.combine(day, datetime.min.time()) + timedelta(hours=h)).strftime("%H:%M:%S"): {
                "readDateTime": (datetime.combine(day, datetime.min.time()) + timedelta(hours=h)).isoformat(),
                "utilityUsed": 1.0,
                "cost": 0.1,
            }
            for h in labels
        }
    }
    series = helpers.hourly_series(data, TZ, CUTOFF)
    starts = [row[0] for row in series]
    assert len(starts) == 23
    assert all(b - a == timedelta(hours=1) for a, b in zip(starts, starts[1:]))
    assert starts[0] == datetime(2026, 3, 8, 5, 0, tzinfo=timezone.utc)  # midnight EST


def test_multiplier_scales_state_and_sum():
    series = helpers.hourly_series(three_days(), TZ, CUTOFF)
    consumption, _ = helpers.build_statistics(series, multiplier=2.0)
    assert consumption[0][1] == 2.0 and consumption[-1][2] == 2 * 24 * 6.0


def test_accumulating_in_key_order_is_what_broke_the_sums():
    """Reproduces the old behaviour: sum in sorted-key order, start = the label.

    The closing reading of each day sorts first ("00:00:00") but is timestamped on
    the next date, so ordered by timestamp the cumulative sum steps backwards.
    """
    old_rows, running = [], 0.0
    for day_key in sorted(three_days()):
        day = three_days()[day_key]
        for time_key in sorted(day):
            running += day[time_key]["utilityUsed"]
            label = datetime.fromisoformat(day[time_key]["readDateTime"])
            old_rows.append((label, running))
    by_time = [total for _, total in sorted(old_rows)]
    assert any(b < a for a, b in zip(by_time, by_time[1:])), "old ordering should go backwards"


def test_reimporting_a_later_window_continues_the_stored_sums():
    """A window that starts later must chain from the stored sum, not restart at zero."""
    series = helpers.hourly_series(three_days(), TZ, CUTOFF)
    stored, _ = helpers.build_statistics(series)  # what the recorder holds after the first poll
    k = 30  # the next poll's window starts 30 hours in
    base = stored[k - 1][2]
    window, _ = helpers.build_statistics(series[k:], base_usage=base)
    assert window == stored[k:]  # identical to one continuous import


def test_restarting_at_zero_leaves_a_step_at_the_window_edge():
    """What happens without the anchor: the first new row drops below the stored sum."""
    series = helpers.hourly_series(three_days(), TZ, CUTOFF)
    stored, _ = helpers.build_statistics(series)
    k = 30
    restarted, _ = helpers.build_statistics(series[k:])  # base 0, as before
    assert restarted[0][2] < stored[k - 1][2]
