"""HTTP and template contracts against an isolated SQLite database."""

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
    get_settings,
    set_values,
)

TOTAL = len(koan_selector.load_koans())


class AppTestCase(unittest.TestCase):
    """Exercise Flask routes without touching the real subscriptions DB."""

    def setUp(self):
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        set_values(push_time="08:00", push_timezone="America/New_York")
        conn = koan_selector.connect(DB)
        try:
            with conn:
                conn.execute(
                    "UPDATE settings SET value = '2' WHERE key = 'current_index'"
                )
        finally:
            conn.close()

    def test_home_renders_daily_and_exposes_legacy_seed(self):
        from unittest.mock import patch

        with patch.object(app_module, "daily_index", return_value=4):
            page = self.client.get("/").get_data(as_text=True)
        self.assertIn(load_koans()[4]["title"], html.unescape(page))
        self.assertIn("localStorage.setItem('dk-index', 2)", page)
        for retired in ("/api/next", "/api/mode", "In order", ">Random</button>"):
            self.assertNotIn(retired, page)
        with self.client.get("/sw.js") as worker:
            self.assertIn("daily-koan-v4", worker.get_data(as_text=True))

    def test_deep_link_does_not_change_seed_and_missing_returns_404(self):
        response = self.client.get("/koan/4")
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            load_koans()[4]["title"], html.unescape(response.get_data(as_text=True))
        )
        self.assertEqual(get_settings()["current_index"], "2")
        self.assertEqual(self.client.get(f"/koan/{TOTAL}").status_code, 404)

    def test_missing_held_navigation_renders_today_as_html(self):
        from unittest.mock import patch

        with patch.object(app_module, "daily_index", return_value=4):
            response = self.client.get(f"/koan/{TOTAL}?resume=1")
        self.assertEqual(response.status_code, 404)
        page = html.unescape(response.get_data(as_text=True))
        self.assertIn(load_koans()[4]["title"], page)
        self.assertIn("const missing = true;", page)
        self.assertEqual(get_settings()["current_index"], "2")

    def test_retired_posts_cannot_change_settings(self):
        before = get_settings()
        for endpoint in ("/api/next", "/api/mode"):
            self.assertEqual(self.client.post(endpoint).status_code, 410)
        for key in ("progression", "mode", "current_index"):
            response = self.client.post(
                "/api/settings", json={key: "held", "push_time": "07:30"}
            )
            self.assertEqual(response.status_code, 400)
        self.assertEqual(get_settings(), before)

    def test_settings_get_roundtrip(self):
        body = self.client.get("/api/settings").get_json()
        self.assertNotIn("mode", body)
        self.assertEqual(body["push_time"], "08:00")
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

    def test_settings_post_cross_origin_403(self):
        res = self.client.post(
            "/api/settings",
            json={"push_time": "07:30"},
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(res.status_code, 403)

    # --- /api/today ---

    def test_api_today_is_stateless(self):
        from unittest.mock import patch

        with patch.object(app_module, "daily_index", return_value=4):
            body = self.client.get("/api/today").get_json()
        self.assertEqual(body, {"index": 4, "koan": load_koans()[4], "total": TOTAL})

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
