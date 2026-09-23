"""Refresh podcast_v2/models.json from the OpenAI, Anthropic and Google model APIs.

The V2 equivalent of the sheet's UM step: models are listed by name (no
numeric IDs), known models are never removed, and a model a provider stops
listing is marked "available": false.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

V2_DIR = Path(__file__).resolve().parent
MODELS_PATH = V2_DIR / "models.json"


def merge_models(existing, fetched, now):
    """Return (updated registry, added names, newly unavailable names)."""
    by_name = {m["name"]: dict(m) for m in existing.get("models", [])}
    fetched_names = {m["id"] for m in fetched}
    # A provider that returned nothing (missing key, outage) says nothing about its models.
    answered = {m["provider"] for m in fetched}
    added, removed = [], []
    for model in fetched:
        entry = by_name.get(model["id"])
        if entry is None:
            added.append(model["id"])
            entry = by_name[model["id"]] = {"name": model["id"], "provider": model["provider"],
                                            "web_search": False, "available": True}
        entry["web_search"] = bool(entry.get("web_search")) or bool(model.get("web_search"))
        entry["available"] = True
    for entry in by_name.values():
        if entry["provider"] in answered and entry["name"] not in fetched_names and entry.get("available", True):
            entry["available"] = False
            removed.append(entry["name"])
    registry = {
        "updated_at": now,
        "source": "Update Models V2 (provider model APIs)",
        "models": sorted(by_name.values(), key=lambda m: (m["provider"], m["name"])),
    }
    return registry, sorted(added), sorted(removed)


def main():
    sys.path.insert(0, str(V2_DIR.parent))
    import ai_podcast_pipeline_for_cursor as legacy

    existing = json.loads(MODELS_PATH.read_text(encoding="utf-8"))
    fetched = legacy.fetch_all_models()
    if not fetched:
        print("❌ No provider returned any models; leaving models.json unchanged.")
        return 1
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    registry, added, removed = merge_models(existing, fetched, now)
    if registry["models"] != existing.get("models"):
        MODELS_PATH.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")

    lines = [f"Models listed: {sum(m['available'] for m in registry['models'])} available, "
             f"{len(added)} new, {len(removed)} no longer offered."]
    lines += [f"- New: `{name}`" for name in added]
    lines += [f"- No longer offered: `{name}`" for name in removed]
    print("\n".join(lines))
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("## Update Models V2\n\n" + "\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
