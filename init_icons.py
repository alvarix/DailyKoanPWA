#!/usr/bin/env python3
"""Generate simple placeholder icons for the PWA."""

import os
import subprocess
import sys

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Installing Pillow...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow", "-q"])
    from PIL import Image, ImageDraw


def make_icon(size, color, filename):
    try:
        img = Image.new("RGB", (size, size), color)
        draw = ImageDraw.Draw(img)
        margin = size // 4
        bbox = [margin, margin, size - margin, size - margin]
        draw.ellipse(bbox, fill="#d97706")
        img.save(filename)
        print(f"Generated {filename}")
    except Exception as e:
        print(f"Failed to generate {filename}: {e}")


if __name__ == "__main__":
    try:
        os.makedirs("static", exist_ok=True)
    except OSError as e:
        print(f"ERROR: cannot create static directory: {e}")
        sys.exit(1)
    make_icon(192, "#1c1917", "static/icon-192.png")
    make_icon(512, "#1c1917", "static/icon-512.png")
    make_icon(72, "#1c1917", "static/badge-72.png")
    print("Done.")
