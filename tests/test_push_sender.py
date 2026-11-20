"""Unit tests for push_sender.py helpers."""

import sys
import unittest
from pathlib import Path

# Make the repo root importable so we can load push_sender.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from push_sender import truncate_utf8_bytes  # type: ignore


class TestTruncateUtf8Bytes(unittest.TestCase):
    """Tests for the byte-safe body truncate used in bare-alert pushes."""

    def test_short_text_unchanged(self):
        """A koan text below the byte budget is returned unchanged."""
        text = "What is the sound of one hand?"
        self.assertEqual(truncate_utf8_bytes(text), text)

    def test_exact_limit_unchanged(self):
        """A text whose UTF-8 byte length equals the limit is returned unchanged."""
        text = "x" * 750
        self.assertEqual(truncate_utf8_bytes(text), text)

    def test_long_ascii_truncated(self):
        """A long ASCII string is truncated and ends with an ellipsis."""
        text = "word " * 1000  # well over 750 bytes
        result = truncate_utf8_bytes(text)
        self.assertLessEqual(
            len(result.encode("utf-8")), 750
        )  # ellipsis already budgeted
        self.assertTrue(result.endswith("…"))

    def test_multibyte_codepoint_not_split(self):
        """Truncation backs up to a complete codepoint boundary."""
        # Each snowman is 3 bytes; force a cut inside the third byte at byte 750.
        text = "☃" * 500
        result = truncate_utf8_bytes(text)
        # The returned text must be valid UTF-8.
        result.encode("utf-8")
        self.assertTrue(result.endswith("…"))
        self.assertLessEqual(len(result.encode("utf-8")), 750)

    def test_empty_string(self):
        """An empty string stays empty."""
        self.assertEqual(truncate_utf8_bytes(""), "")


if __name__ == "__main__":
    unittest.main()
