"""Download emojibase data and write a compact catalog to static/emoji.json."""

import json
import urllib.request
from pathlib import Path

SOURCE = "https://cdn.jsdelivr.net/npm/emojibase-data@16/en/compact.json"
GROUPS = {
    0: "Smileys & Emotion", 1: "People & Body", 3: "Animals & Nature",
    4: "Food & Drink", 5: "Travel & Places", 6: "Activities",
    7: "Objects", 8: "Symbols", 9: "Flags",
}

with urllib.request.urlopen(SOURCE) as response:
    raw = json.load(response)

catalog = [
    {
        "e": item["unicode"],
        "n": item["label"],
        "t": item.get("tags", []),
        "g": GROUPS[item["group"]],
    }
    for item in raw
    if item.get("group") in GROUPS
]
out = Path(__file__).parent.parent / "static" / "emoji.json"
out.write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")))
print(f"wrote {len(catalog)} emoji to {out}")
