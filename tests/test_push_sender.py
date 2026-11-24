"""Test the fixed notification contract without sending a push."""

import unittest

from push_sender import build_payload


class TestNudge(unittest.TestCase):
    def test_trigger_has_public_daily_text_and_no_title(self):
        self.assertEqual(build_payload("Today’s text"), {
            "body": "Your koan awaits.",
            "dailyBody": "Today’s text",
            "icon": "/static/icon-192.png",
            "badge": "/static/badge-72.png",
            "data": {"url": "/"},
        })
