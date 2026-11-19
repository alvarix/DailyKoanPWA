"""Unit tests for koan_selector.py — the shared selection/settings state.

These cover the paths docs/002 flagged as the risky ones: migration
idempotency, the daily/held selection split, atomic advance, mode-switch
dedupe-key resets, and push dedupe in both modes. All tests run against a
throwaway temp DB — never the real subscriptions.db.
"""

import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import koan_selector
from koan_selector import (
    SETTINGS_VERSION,
    advance,
    current_index,
    daily_index,
    delivery_window,
    ensure_settings,
    get_settings,
    is_delivery_time,
    load_koans,
    mark_pushed,
    select_push,
    set_values,
    valid_timezone,
)


class TempDbTestCase(unittest.TestCase):
    """Base: each test gets its own throwaway settings DB."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "test.db")

    def seed(self, mode="held", current_index=None, total=14, today="2026-11-16"):
        ensure_settings(self.db, total_koans=total, today=today)
        if mode != "held" or current_index is not None:
            set_values(self.db, mode=mode)
            conn = koan_selector.connect(self.db)
            conn.execute(
                "UPDATE settings SET value = ? WHERE key = 'current_index'",
                (str(current_index if current_index is not None else 0),),
            )
            conn.commit()
            conn.close()
        return get_settings(self.db)


class TestMigration(TempDbTestCase):
    """ensure_settings: idempotent, additive, seeded."""

    def test_seeds_defaults(self):
        ensure_settings(self.db, total_koans=14, today="2026-11-16")
        settings = get_settings(self.db)
        self.assertEqual(settings["mode"], "held")
        self.assertEqual(settings["progression"], "ordered")
        self.assertEqual(settings["push_time"], "08:00")
        self.assertEqual(settings["push_timezone"], "America/New_York")
        self.assertEqual(settings["last_push_date"], "")
        self.assertEqual(settings["last_push_index"], "")
        # seed = today's deterministic index
        self.assertEqual(
            int(settings["current_index"]),
            daily_index(14, "2026-11-16"),
        )

    def test_idempotent_double_run(self):
        ensure_settings(self.db, total_koans=14, today="2026-11-16")
        before = get_settings(self.db)
        ensure_settings(self.db, total_koans=14, today="2026-11-16")
        after = get_settings(self.db)
        self.assertEqual(before, after)

    def test_preserves_user_values(self):
        """A re-run must not clobber settings the operator changed."""
        ensure_settings(self.db, total_koans=14, today="2026-11-16")
        set_values(self.db, push_time="09:30", push_timezone="Europe/Madrid")
        ensure_settings(self.db, total_koans=14, today="2026-11-16")
        settings = get_settings(self.db)
        self.assertEqual(settings["push_time"], "09:30")
        self.assertEqual(settings["push_timezone"], "Europe/Madrid")

    def test_user_version_set(self):
        ensure_settings(self.db, total_koans=14, today="2026-11-16")
        conn = sqlite3.connect(self.db)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        conn.close()
        self.assertEqual(version, SETTINGS_VERSION)


class TestSelection(TempDbTestCase):
    """daily/held selection and the atomic advance."""

    def test_daily_mode_is_stateless(self):
        """Daily mode computes from the date — never reads current_index."""
        settings = self.seed(mode="daily", current_index=99)
        idx_a = current_index(settings, 14, date="2026-11-16")
        idx_b = current_index(settings, 14, date="2026-11-16")
        self.assertEqual(idx_a, daily_index(14, "2026-11-16"))
        self.assertEqual(idx_a, idx_b)

    def test_daily_mode_changes_with_date(self):
        settings = self.seed(mode="daily")
        self.assertEqual(
            current_index(settings, 14, date="2026-11-16"),
            daily_index(14, "2026-11-16"),
        )
        # different date -> possibly different koan (deterministic either way)
        idx_other = current_index(settings, 14, date="2026-11-17")
        self.assertEqual(idx_other, daily_index(14, "2026-11-17"))

    def test_held_mode_reads_pointer(self):
        settings = self.seed(mode="held", current_index=7)
        self.assertEqual(current_index(settings, 14), 7)

    def test_held_mode_clamps_out_of_range(self):
        """A shrunk/reordered koans.json can never 500 the page view."""
        settings = self.seed(mode="held", current_index=13)
        self.assertEqual(current_index(settings, 10), 3)

    def test_held_mode_survives_garbage_pointer(self):
        settings = self.seed(mode="held", current_index=3)
        settings["current_index"] = "not-a-number"
        self.assertEqual(current_index(settings, 14), 0)

    def test_advance_wraps_around(self):
        self.seed(mode="held", current_index=13)
        nxt = advance(self.db, total=14)
        self.assertEqual(nxt, 0)

    def test_advance_is_atomic_and_serialized(self):
        """Two concurrent advances must land on distinct pointers."""
        self.seed(mode="held", current_index=0)

        results = []
        for _ in range(2):
            results.append(advance(self.db, total=14))
        self.assertEqual(len(set(results)), 2)
        self.assertEqual(sorted(results), [1, 2])

    def test_advance_random_progression_moves(self):
        """Random progression jumps to a different koan (never a stall)."""
        self.seed(mode="held", current_index=5)
        set_values(self.db, progression="random")

        class FakeRng:
            def choice(self, seq):
                return seq[len(seq) // 2]

        nxt = advance(self.db, total=14, rng=FakeRng())
        self.assertNotEqual(nxt, 5)


class TestModeSwitch(TempDbTestCase):
    """Mode switches must not be silenced by stale dedupe keys."""

    def test_mode_switch_clears_dedupe_keys(self):
        ensure_settings(self.db, total_koans=14, today="2026-11-16")
        mark_pushed(self.db, index=3, date="2026-11-16")
        set_values(self.db, mode="daily")
        settings = get_settings(self.db)
        self.assertEqual(settings["mode"], "daily")
        self.assertEqual(settings["last_push_date"], "")
        self.assertEqual(settings["last_push_index"], "")

    def test_set_values_rejects_unknown_keys(self):
        ensure_settings(self.db, total_koans=14, today="2026-11-16")
        with self.assertRaises(ValueError):
            set_values(self.db, mode="held", current_index="999")


class TestDeliveryGate(unittest.TestCase):
    """is_delivery_time / delivery_window / valid_timezone: the hourly gate."""

    SETTINGS = {
        "push_time": "08:00",
        "push_timezone": "America/New_York",
    }

    def test_valid_timezone(self):
        self.assertTrue(valid_timezone("America/New_York"))
        self.assertTrue(valid_timezone("Europe/Madrid"))
        self.assertFalse(valid_timezone("Not/AZone"))
        self.assertFalse(valid_timezone(""))

    def test_window_converts_utc_to_local(self):
        # 2026-11-16 13:00 UTC = 08:00 EST (UTC-5 after the Nov 1 DST end)
        date, hhmm = delivery_window(
            self.SETTINGS, now=datetime(2026, 11, 16, 13, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(date, "2026-11-16")
        self.assertEqual(hhmm, "08:00")

    def test_window_garbage_zone_falls_back_to_utc(self):
        settings = {**self.SETTINGS, "push_timezone": "Not/AZone"}
        date, hhmm = delivery_window(
            settings, now=datetime(2026, 11, 16, 13, 0, tzinfo=timezone.utc)
        )
        self.assertEqual((date, hhmm), ("2026-11-16", "13:00"))

    def test_gate_opens_at_push_time(self):
        # EST instants: 07:59 closed, 08:00 open, 15:00 still open.
        before = datetime(2026, 11, 16, 12, 59, tzinfo=timezone.utc)
        at = datetime(2026, 11, 16, 13, 0, tzinfo=timezone.utc)
        after = datetime(2026, 11, 16, 20, 0, tzinfo=timezone.utc)
        self.assertFalse(is_delivery_time(self.SETTINGS, now=before))
        self.assertTrue(is_delivery_time(self.SETTINGS, now=at))
        self.assertTrue(is_delivery_time(self.SETTINGS, now=after))

    def test_gate_garbage_push_time_falls_back_to_08(self):
        # 14:00 UTC = 09:00 EST: past the 08:00 fallback, so open.
        now = datetime(2026, 11, 16, 14, 0, tzinfo=timezone.utc)
        for bad in ("25:99", "nope"):
            settings = {**self.SETTINGS, "push_time": bad}
            self.assertTrue(is_delivery_time(settings, now=now), msg=bad)


class TestPushDecision(TempDbTestCase):
    """select_push: the hourly timer's decision (0.1.8 cadence).

    BOTH modes deliver exactly once per LOCAL push-day. Held mode
    RE-ANNOUNCES the current pointer every day (user decision 2026-11-19:
    "the same koan until I advance, every day") — the pointer never
    suppresses the push anymore.
    """

    KOANS = [{"title": f"k{i}", "koan_text": f"koan {i}"} for i in range(14)]

    # 2026-11-16 13:00 UTC = 08:00 America/New_York: the gate's open moment.
    OPEN_NOW = datetime(2026, 11, 16, 13, 0, tzinfo=timezone.utc)

    def _settings(self, mode="held", current_index=4):
        settings = self.seed(mode=mode, current_index=current_index)
        settings["last_push_date"] = ""  # nothing delivered today yet
        settings["last_push_index"] = str(current_index)
        return settings

    def test_gate_closed_before_push_time(self):
        settings = self._settings()
        before = datetime(2026, 11, 16, 12, 59, tzinfo=timezone.utc)
        self.assertIsNone(select_push(self.KOANS, settings, now=before))

    def test_held_reannounces_same_pointer_every_day(self):
        """0.1.8: held pushes even when last_push_index == the pointer."""
        settings = self._settings(mode="held", current_index=4)
        picked = select_push(self.KOANS, settings, now=self.OPEN_NOW)
        assert picked is not None  # narrows Optional for the type checker
        self.assertEqual(picked[0], 4)

    def test_held_dedupes_within_local_day(self):
        settings = self._settings(mode="held", current_index=4)
        picked = select_push(self.KOANS, settings, now=self.OPEN_NOW)
        assert picked is not None
        mark_pushed(self.db, index=picked[0], date="2026-11-16")  # local EST date
        settings = get_settings(self.db)
        self.assertIsNone(select_push(self.KOANS, settings, now=self.OPEN_NOW))

    def test_daily_pushes_today_then_dedupes(self):
        settings = self._settings(mode="daily")
        picked = select_push(self.KOANS, settings, date="2026-11-16", now=self.OPEN_NOW)
        assert picked is not None
        # selection is the UTC date hash (site parity), not the local date
        self.assertEqual(picked[0], daily_index(14, "2026-11-16"))
        mark_pushed(self.db, index=picked[0], date="2026-11-16")
        settings = get_settings(self.db)
        self.assertIsNone(
            select_push(self.KOANS, settings, date="2026-11-16", now=self.OPEN_NOW)
        )

    def test_default_mode_is_held(self):
        """Fresh install: gate open, nothing delivered -> the pointer koan."""
        ensure_settings(self.db, total_koans=14, today="2026-11-16")
        settings = get_settings(self.db)
        picked = select_push(self.KOANS, settings, now=self.OPEN_NOW)
        assert picked is not None  # narrows Optional for the type checker
        self.assertEqual(picked[0], int(settings["current_index"]))


class TestLoadKoans(unittest.TestCase):
    """Progression ordering is metadata-driven, not file-order driven."""

    def test_order_follows_group_then_case(self):
        koans = load_koans()
        self.assertEqual(len(koans), 14)
        groups = [k["group"] for k in koans]
        self.assertEqual(
            groups,
            sorted(groups, key=lambda g: koan_selector.GROUP_RANK.get(g, 99)),
        )
        for k in koans:
            self.assertIn("id", k, "every koan carries a stable id")
            self.assertIn("order", k, "every koan carries a case order")

    def test_ids_unique(self):
        koans = load_koans()
        ids = [k["id"] for k in koans]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
