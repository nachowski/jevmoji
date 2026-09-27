# /// script
# dependencies = ["playwright"]
# ///
"""Record a showcase video of the running app (uv run uvicorn server:app --port 8765)."""

import random
import shutil
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://localhost:8765"
PHRASES = sys.argv[1:] or [
    "self care", "climate change", "oktoberfest", "tokyo", "breaking bad", "awkward silence",
]
SIZE = {"width": 720, "height": 560}
ROOT = Path(__file__).parent.parent
RAW = ROOT / "demo" / "raw"
OUT = ROOT / "demo" / "showcase.mp4"

shutil.rmtree(RAW, ignore_errors=True)
with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(
        viewport=SIZE, record_video_dir=RAW, record_video_size=SIZE,
        permissions=["clipboard-read", "clipboard-write"],
    )
    page = context.new_page()
    page.goto(URL)
    page.wait_for_timeout(1000)
    page.click("#q")
    for n, phrase in enumerate(PHRASES):
        if n:
            for _ in page.input_value("#q"):
                page.keyboard.press("Backspace")
                page.wait_for_timeout(random.randint(35, 70))
            page.wait_for_timeout(random.randint(500, 800))
        for char in phrase:  # uneven human typing, but under the page's 350 ms debounce
            page.keyboard.type(char)
            page.wait_for_timeout(random.randint(60, 180))
        page.wait_for_selector("#picker.loading")
        page.wait_for_selector("#picker:not(.loading)", timeout=30_000)
        page.wait_for_timeout(2800)
    page.wait_for_timeout(1000)
    video = page.video.path()
    context.close()
    browser.close()

subprocess.run(
    ["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-c:v", "libx264", "-crf", "20",
     "-pix_fmt", "yuv420p", "-movflags", "+faststart", OUT],
    check=True,
)
shutil.rmtree(RAW)
print(f"wrote {OUT}")
