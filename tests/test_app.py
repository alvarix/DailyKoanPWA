"""Route tests for app.py — the 002 surface: mode, next, settings, deep links.

Uses Flask's test client against a throwaway temp DB (patched into
koan_selector.DB_PATH BEFORE importing app, so the app's own startup
migration never touches the real subscriptions.db). No network, no VAPID,
no subscriptions table needed for these paths.
"""

import html
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import koan_selector

# Patch the DB path before app.py imports (its module-level ensure_settings
# runs against whatever DB_PATH is at import time).
_TMP = tempfile.TemporaryDirectory()
DB = str(Path(_TMP.name) / "app-test.db")
koan_selector.DB_PATH = DB

import app as app_module  # noqa: E402  (must come after the patch)
from koan_selector import (  # noqa: E402
    daily_index,
    get_settings,
    set_values,
)

TOTAL = len(koan_selector.load_koans())


class AppTestCase(unittest.TestCase):
    """One shared test DB; each test sets the mode it needs."""

    def setUp(self):
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        self.reset(mode="held", current_index=2)

    @staticmethod
    def reset(mode, current_index):
        """Force a known global state (mode + pointer)."""
        set_values(mode=mode)
        conn = koan_selector.connect(DB)
        conn.execute(
            "UPDATE settings SET value = ? WHERE key = 'current_index'",
            (str(current_index),),
        )
        conn.commit()
        conn.close()

    # --- pages ---

    def test_index_serves_current_koan_held(self):
        self.reset(mode="held", current_index=5)
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        # Jinja autoescapes (&#39;), so compare against the unescaped page.
        page = html.unescape(res.get_data(as_text=True))
        self.assertIn(load_koans()[5]["title"], page)

    def test_index_serves_daily_koan(self):
        self.reset(mode="daily", current_index=5)
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        page = html.unescape(res.get_data(as_text=True))
        expected = load_koans()[daily_index(TOTAL)]["title"]
        self.assertIn(expected, page)

    def test_koan_deep_link_renders_without_moving_pointer(self):
        """Deep links are per-visitor navigation only (docs/002)."""
        self.reset(mode="held", current_index=2)
        res = self.client.get("/koan/9")
        self.assertEqual(res.status_code, 200)
        page = html.unescape(res.get_data(as_text=True))
        self.assertIn(load_koans()[9]["title"], page)
        settings = get_settings()
        self.assertEqual(int(settings["current_index"]), 2)

    def test_koan_deep_link_out_of_range_404s(self):
        res = self.client.get(f"/koan/{TOTAL + 5}")
        self.assertEqual(res.status_code, 404)

    # --- /api/next ---

    def test_next_advances_pointer_held(self):
        res = self.client.post("/api/next")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(body["index"], 3)  # 2 -> 3

    def test_next_wraps_around(self):
        self.reset(mode="held", current_index=TOTAL - 1)
        res = self.client.post("/api/next")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["index"], 0)

    def test_next_409_in_daily_mode(self):
        self.reset(mode="daily", current_index=2)
        res = self.client.post("/api/next")
        self.assertEqual(res.status_code, 409)

    # --- /api/mode ---

    def test_mode_switch(self):
        res = self.client.post(
            "/api/mode",
            json={"mode": "daily"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["mode"], "daily")
        self.assertEqual(get_settings()["mode"], "daily")

    def test_mode_switch_clears_dedupe_keys(self):
        """Fresh push in the new mode, not silenced by stale dedupe keys."""
        from koan_selector import mark_pushed

        mark_pushed(DB, index=2, date="2026-11-16")
        self.client.post("/api/mode", json={"mode": "daily"})
        settings = get_settings()
        self.assertEqual(settings["last_push_date"], "")
        self.assertEqual(settings["last_push_index"], "")

    def test_mode_invalid_value_400(self):
        res = self.client.post("/api/mode", json={"mode": "weekly"})
        self.assertEqual(res.status_code, 400)

    def test_mode_cross_origin_403(self):
        res = self.client.post(
            "/api/mode",
            json={"mode": "daily"},
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(res.status_code, 403)

    def test_next_cross_origin_403(self):
        res = self.client.post(
            "/api/next",
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(res.status_code, 403)

    # --- /api/settings ---

    def test_settings_get_roundtrip(self):
        res = self.client.get("/api/settings")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["mode"], "held")
        self.assertEqual(body["push_time"], "08:00")
        # 0.1.8: the delivery zone is settings data (default from the seed)
        self.assertEqual(body["push_timezone"], "America/New_York")

    def test_settings_post_push_time(self):
        res = self.client.post("/api/settings", json={"push_time": "07:30"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(get_settings()["push_time"], "07:30")

    def test_settings_post_push_time_invalid(self):
        for bad in ("25:00", "8am", "", None):
            res = self.client.post("/api/settings", json={"push_time": bad})
            self.assertEqual(res.status_code, 400, msg=repr(bad))

    def test_settings_post_push_timezone(self):
        """0.1.8: the delivery timezone round-trips through /api/settings."""
        res = self.client.post("/api/settings", json={"push_timezone": "Europe/Madrid"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(get_settings()["push_timezone"], "Europe/Madrid")

    def test_settings_post_push_timezone_invalid(self):
        """Only a loadable IANA zone is accepted (app.valid_timezone gate).

        Note "EST" is deliberately absent: zoneinfo can load the legacy
        fixed-offset name, so it is accepted too — DST-less but functional.
        """
        for bad in ("Not/AZone", "America/Nowhere", "", None):
            res = self.client.post("/api/settings", json={"push_timezone": bad})
            self.assertEqual(res.status_code, 400, msg=repr(bad))

    def test_settings_post_progression(self):
        res = self.client.post("/api/settings", json={"progression": "random"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(get_settings()["progression"], "random")

    def test_settings_post_no_valid_keys_400(self):
        res = self.client.post("/api/settings", json={"current_index": "999"})
        self.assertEqual(res.status_code, 400)

    def test_settings_post_cross_origin_403(self):
        res = self.client.post(
            "/api/settings",
            json={"push_time": "07:30"},
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(res.status_code, 403)

    # --- /api/today ---

    def test_api_today_carries_mode(self):
        self.reset(mode="held", current_index=4)
        res = self.client.get("/api/today")
        body = res.get_json()
        self.assertEqual(body["mode"], "held")
        self.assertEqual(body["index"], 4)
        self.assertEqual(body["current_index"], 4)
        self.assertEqual(body["koan"]["title"], load_koans()[4]["title"])

    # --- 0.1.7 template surface (bell toggle redesign) ---

    def test_index_has_drawer_notification_switch(self):
        """Drawer carries a proper switch, first section (user request 2026-11-17)."""
        page = html.unescape(self.client.get("/").get_data(as_text=True))
        self.assertIn('role="switch"', page)
        self.assertIn("aria-checked", page)
        self.assertIn(">Notifications</p>", page)

    def test_index_has_on_badge_and_toast(self):
        """Bell shows an explicit ON badge; feedback is an in-page toast."""
        page = html.unescape(self.client.get("/").get_data(as_text=True))
        self.assertIn("bg-gold-400", page)  # badge dot
        self.assertIn('x-show="toast"', page)  # toast element
        self.assertIn('x-text="toastMessage"', page)
        self.assertIn("showToast", page)  # Alpine method exists

    def test_index_has_no_alert_popups(self):
        """All alert() popups replaced by toasts (002 known-warnings cleanup).

        Checks `alert('` (call sites) rather than `alert(` — comments still
        reference the removed function by name, which is fine.
        """
        page = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("alert('", page)

    def test_bell_aria_reflects_state_template(self):
        """aria-label is Alpine-bound, not the old static string."""
        page = self.client.get("/").get_data(as_text=True)
        self.assertNotIn('aria-label="Toggle notifications"', page)


def load_koans():
    return koan_selector.load_koans()


if __name__ == "__main__":
    unittest.main()
