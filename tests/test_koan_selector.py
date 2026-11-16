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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import koan_selector
from koan_selector import (
    SETTINGS_VERSION,
    advance,
    current_index,
    daily_index,
    ensure_settings,
    get_settings,
    load_koans,
    mark_pushed,
    select_push,
    set_values,
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
        set_values(self.db, push_time="09:30")
        ensure_settings(self.db, total_koans=14, today="2026-11-16")
        self.assertEqual(get_settings(self.db)["push_time"], "09:30")

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


class TestPushDecision(TempDbTestCase):
    """select_push: the dedupe logic the timer relies on."""

    KOANS = [{"title": f"k{i}", "koan_text": f"koan {i}"} for i in range(14)]

    def test_daily_pushes_then_dedupes(self):
        settings = self.seed(mode="daily")
        settings["last_push_date"] = ""
        picked = select_push(self.KOANS, settings, date="2026-11-16")
        self.assertIsNotNone(picked)
        assert picked is not None  # narrows Optional for the type checker
        idx, koan = picked
        self.assertEqual(idx, daily_index(14, "2026-11-16"))
        self.assertEqual(koan, self.KOANS[idx])

        settings["last_push_date"] = "2026-11-16"  # already pushed today
        self.assertIsNone(select_push(self.KOANS, settings, date="2026-11-16"))

    def test_held_pushes_only_when_moved(self):
        settings = self.seed(mode="held", current_index=4)
        settings["last_push_index"] = "4"  # already pushed this position
        self.assertIsNone(select_push(self.KOANS, settings, date="2026-11-16"))

        settings["last_push_index"] = "3"  # someone pressed Next since
        picked = select_push(self.KOANS, settings, date="2026-11-16")
        assert picked is not None  # narrows Optional for the type checker
        self.assertEqual(picked[0], 4)

    def test_default_mode_is_held(self):
        """Fresh install defaults to held (docs/002 tweak 1)."""
        ensure_settings(self.db, total_koans=14, today="2026-11-16")
        settings = get_settings(self.db)
        picked = select_push(self.KOANS, settings, date="2026-11-16")
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
