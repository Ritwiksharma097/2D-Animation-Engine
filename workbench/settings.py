"""Owner-decided values in one place: annotations/_settings.json (FORMAT.md, "Settings")."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "annotations" / "_settings.json"


def load() -> dict:
    if PATH.exists():
        return json.loads(PATH.read_text(encoding="utf-8"))
    return {"format": "workbench-settings/1", "characters": {}, "open_decisions": {}}


def save(doc: dict) -> Path:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return PATH


def game_scale(character: str) -> tuple[float | None, bool, str]:
    """(game px per cell px, confirmed by the owner?, where the value came from)."""
    c = load()["characters"].get(character)
    if c and c.get("game_scale"):
        return float(c["game_scale"]), bool(c.get("confirmed")), c.get("source", "annotations/_settings.json")
    import analyze
    m = analyze.load_manifest()["characters"][character].get("game_scale_in_old_demos")
    return (float(m), True, "manifest game_scale_in_old_demos") if m else (None, False, "not set")


def set_game_scale(character: str, value: float, confirmed: bool, source: str = "set by the owner on the review page") -> dict:
    doc = load()
    doc.setdefault("characters", {})[character] = {"game_scale": float(value), "confirmed": bool(confirmed), "source": source}
    save(doc)
    return doc


def travel_override(character: str, action: str) -> dict | None:
    """Per-action constant travel (cell px per frame) that replaces contact-derived travel, or None."""
    return load().get("travel_overrides", {}).get(f"{character}/{action}")
