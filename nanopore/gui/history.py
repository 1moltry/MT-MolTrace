"""Recent-file history stored in the same QSettings scope as the GUI options."""

from __future__ import annotations

import json
from pathlib import Path

from PyQt5.QtCore import QSettings

# Legacy QSettings scope kept after the product rename: existing users keep
# their recent-file list and last protocol.
SETTINGS = ("SDL-Nanopore", "gui")
_KEY = "recent_files"
_LIMIT = 8


def add_recent(path: str | Path, limit: int = _LIMIT) -> None:
    """Move ``path`` to the front of the recent list (deduplicated)."""
    p = str(Path(path).resolve())
    items = [x for x in recent_files(limit=1000) if x != p]
    items.insert(0, p)
    QSettings(*SETTINGS).setValue(_KEY, json.dumps(items[:limit], ensure_ascii=False))


def recent_files(limit: int = _LIMIT) -> list[str]:
    raw = QSettings(*SETTINGS).value(_KEY, "")
    try:
        items = json.loads(str(raw)) if raw else []
    except Exception:                    # noqa: BLE001 — corrupt history is not fatal
        items = []
    out = [str(x) for x in items if Path(str(x)).exists()]
    return out[:limit]


def clear_recent() -> None:
    QSettings(*SETTINGS).remove(_KEY)
