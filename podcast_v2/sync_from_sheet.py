"""Copy the live Google Sheet configuration into podcast_v2/ (read-only on the sheet).

Writes, for the workflow(s) marked Active = Y:
- prompts/P<id>.txt for every prompt the workflow code references;
- the ElevenLabs settings it references into workflow.json;
- sheet_snapshot.json with the workflow rows, referenced models, locations
  and Eleven rows, for reference.
The Sync V2 From Sheet action commits the result to a branch for review.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

V2_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = V2_DIR / "prompts"
WORKFLOW_PATH = V2_DIR / "workflow.json"
SNAPSHOT_PATH = V2_DIR / "sheet_snapshot.json"
CREDS_FILE = V2_DIR.parent / "jmio-google-api.json"
SHEET_NAME = "AI Workflow"
# V1 appends this block to P4 in the sheet at run time; V2 adds it with the
# workflow's "script_tuning" part, so the synced prompt leaves it out.
SCRIPT_TUNING_BLOCK = re.compile(r"\n*Additional script requirements for this run:\n(?:- .*(?:\n|$))*", re.MULTILINE)
ELEVEN_FIELDS = ("Voice", "Model", "Stability", "Similarity Boost", "Style", "Speed")


def referenced_ids(codes, letter):
    """IDs after a letter in workflow codes, e.g. P10 in 'P10&P8&R2M221'."""
    pattern = {"P": r"(?<![A-Z])P(\d+)", "M": r"M(\d+)", "E": r"E(\d+)", "L": r"(?<![A-Z])L(\d+)"}[letter]
    return sorted({match for code in codes for match in re.findall(pattern, code)}, key=int)


def clean_prompt(text):
    return SCRIPT_TUNING_BLOCK.sub("", str(text)).strip() + "\n"


def build_sync(tabs, workflow):
    """Return (prompt files, updated workflow, snapshot) from the sheet's tab records."""
    active = [w for w in tabs["Workflows"] if str(w.get("Active", "")).strip().upper() == "Y"]
    if not active:
        raise RuntimeError("No workflow is marked Active = Y in the Workflows tab.")
    codes = [str(w.get("Workflow Code", "")) for w in active]
    prompt_ids = referenced_ids(codes, "P")
    prompts_by_id = {str(p.get("Prompt ID")): p for p in tabs["Prompts"]}
    missing = [pid for pid in prompt_ids if pid not in prompts_by_id]
    if missing:
        raise RuntimeError(f"Prompts tab has no Prompt ID {', '.join(missing)}.")
    prompt_files = {pid: clean_prompt(prompts_by_id[pid]["Prompt Description"]) for pid in prompt_ids}

    updated = json.loads(json.dumps(workflow))
    eleven_rows = {str(e.get("Eleven ID")): e for e in tabs.get("Eleven", [])}
    for eleven_id in referenced_ids(codes, "E"):
        row = eleven_rows.get(eleven_id)
        if row:
            for step in updated["steps"]:
                if step["type"] == "voice":
                    step["elevenlabs"].update({k: row[k] for k in ELEVEN_FIELDS if row.get(k) not in (None, "")})

    model_ids = set(referenced_ids(codes, "M"))
    location_ids = set(referenced_ids(codes, "L")) | {m for c in codes for m in re.findall(r"SL(\d+)", c)}
    snapshot = {
        "synced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "active_workflows": active,
        "models": [m for m in tabs.get("Models", []) if str(m.get("Model ID")) in model_ids],
        "locations": [l for l in tabs.get("Locations", []) if str(l.get("Location ID")) in location_ids],
        "eleven": [e for e in tabs.get("Eleven", []) if str(e.get("Eleven ID")) in referenced_ids(codes, "E")],
        "prompt_names": {pid: prompts_by_id[pid].get("Prompt Name", "") for pid in prompt_ids},
    }
    return prompt_files, updated, snapshot


def read_tabs():
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=[
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ])
    sheet = gspread.authorize(creds).open(SHEET_NAME)
    tabs = {}
    for name in ("Workflows", "Prompts", "Models", "Locations", "Eleven"):
        try:
            tabs[name] = sheet.worksheet(name).get_all_records()
        except gspread.exceptions.WorksheetNotFound:
            tabs[name] = []
    return tabs


def main():
    workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    prompt_files, updated, snapshot = build_sync(read_tabs(), workflow)
    for pid, text in prompt_files.items():
        (PROMPTS_DIR / f"P{pid}.txt").write_text(text, encoding="utf-8")
    WORKFLOW_PATH.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    codes = ", ".join(str(w.get("Workflow ID")) for w in snapshot["active_workflows"])
    print(f"Synced active workflow(s) {codes}: prompts {', '.join('P' + p for p in prompt_files)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
