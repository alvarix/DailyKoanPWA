"""Migration, date selection, corpus order and push timing tests."""

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import koan_selector
from koan_selector import (
    SETTINGS_VERSION,
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


class TestMigration(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = str(Path(tmp.name) / "test.db")

    def test_fresh_defaults(self):
        ensure_settings(self.db, total_koans=14, today="2026-11-16")
        self.assertEqual(
            get_settings(self.db),
            {
                "current_index": str(daily_index(14, "2026-11-16")),
                "push_time": "08:00",
                "push_timezone": "America/New_York",
                "last_push_date": "",
            },
        )

    def test_v2_migrates_twice_without_losing_delivery_state_or_subscription(self):
        expected = {
            "current_index": "11",
            "push_time": "05:00",
            "push_timezone": "Europe/Madrid",
            "last_push_date": "2026-11-24",
        }
        conn = koan_selector.connect(self.db)
        try:
            with conn:
                conn.execute(
                    "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
                conn.execute("CREATE TABLE subscriptions (endpoint TEXT PRIMARY KEY)")
                conn.execute("INSERT INTO subscriptions VALUES ('test-endpoint')")
                conn.executemany(
                    "INSERT INTO settings VALUES (?, ?)",
                    {
                        **expected,
                        "mode": "held",
                        "progression": "random",
                        "last_push_index": "10",
                    }.items(),
                )
                conn.execute("PRAGMA user_version = 2")
            for _ in range(2):
                ensure_settings(self.db, total_koans=14)
                self.assertEqual(get_settings(self.db), expected)
            self.assertEqual(
                conn.execute("PRAGMA user_version").fetchone()[0], SETTINGS_VERSION
            )
            self.assertEqual(
                conn.execute("SELECT endpoint FROM subscriptions").fetchone()[0],
                "test-endpoint",
            )
        finally:
            conn.close()

    def test_seed_cannot_be_changed_with_delivery_settings(self):
        ensure_settings(self.db, total_koans=14)
        before = get_settings(self.db)
        with self.assertRaises(ValueError):
            set_values(self.db, push_time="05:00", current_index=13)
        self.assertEqual(get_settings(self.db), before)

    def test_mark_pushed_changes_only_date(self):
        ensure_settings(self.db, total_koans=14)
        expected = {**get_settings(self.db), "last_push_date": "2026-11-24"}
        mark_pushed(self.db, date="2026-11-24")
        self.assertEqual(get_settings(self.db), expected)


class TestDelivery(unittest.TestCase):
    SETTINGS = {"push_time": "08:00", "push_timezone": "America/New_York"}

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


class TestPushGate(unittest.TestCase):
    def test_before_after_and_next_day_without_selection_state(self):
        settings = {"push_time": "05:00", "push_timezone": "America/New_York"}
        self.assertFalse(
            select_push(settings, datetime(2026, 11, 24, 9, 59, tzinfo=timezone.utc))
        )
        due = datetime(2026, 11, 24, 10, tzinfo=timezone.utc)
        self.assertTrue(select_push(settings, due))
        settings["last_push_date"] = "2026-11-24"
        self.assertFalse(select_push(settings, due))
        self.assertFalse(
            select_push(settings, datetime(2026, 11, 25, 2, tzinfo=timezone.utc))
        )
        self.assertTrue(
            select_push(settings, datetime(2026, 11, 25, 10, tzinfo=timezone.utc))
        )


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
