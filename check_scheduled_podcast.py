"""Skip scheduled episodes after a manual trigger on the same Eastern day."""

from datetime import datetime, time, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


EASTERN = ZoneInfo("America/New_York")


def github_api_get(path, params=None):
    url = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/") + path
    if params:
        url += "?" + urlencode(params)
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "AIConvoCast-schedule-check",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        return json.load(response)


def parse_timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def evaluate_run(event_name, repository, run_id, api_get=github_api_get, now=None):
    """Return (should_run, explanation); API errors must prevent automatic runs."""
    if event_name == "workflow_dispatch":
        return True, "Manual trigger: run the podcast as requested."
    if event_name != "schedule":
        raise ValueError(f"Unsupported podcast trigger: {event_name}")

    now = now or datetime.now(timezone.utc)
    current = api_get(f"/repos/{repository}/actions/runs/{run_id}")
    # Anchor to the scheduled run's date even if a runner starts after midnight.
    day = parse_timestamp(current["created_at"]).astimezone(EASTERN).date()
    start = datetime.combine(day, time.min, tzinfo=EASTERN)
    end = start + timedelta(days=1)
    earliest = start.astimezone(timezone.utc)
    latest = min(now, end.astimezone(timezone.utc) - timedelta(seconds=1))
    created_range = f"{earliest.isoformat()}..{latest.isoformat()}"
    workflow_id = current["workflow_id"]
    path = f"/repos/{repository}/actions/workflows/{workflow_id}/runs"

    page = 1
    while True:
        response = api_get(path, {
            "event": "workflow_dispatch", "created": created_range,
            "per_page": 100, "page": page,
        })
        runs = response["workflow_runs"]
        for run in runs:
            triggered = parse_timestamp(run["created_at"])
            if (
                run["event"] == "workflow_dispatch"
                and run["workflow_id"] == workflow_id
                and earliest <= triggered <= latest
            ):
                # The user requested any manual trigger, regardless of outcome.
                return False, (
                    f"Scheduled podcast skipped: manual run {run['id']} was triggered "
                    f"on {day} Eastern time. {run['html_url']}"
                )
        if len(runs) < 100:
            break
        if page >= 10:
            raise RuntimeError("GitHub history exceeded the 1,000-run search limit")
        page += 1
    return True, f"No manual trigger on {day} Eastern time; run the scheduled podcast."


def main():
    try:
        should_run, explanation = evaluate_run(
            os.environ["GITHUB_EVENT_NAME"],
            os.environ["GITHUB_REPOSITORY"],
            os.environ["GITHUB_RUN_ID"],
        )
    except Exception as error:
        print(f"Could not verify manual-run history; automatic generation stopped: {error}", file=sys.stderr)
        return 1

    print(explanation)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.write(f"should_run={str(should_run).lower()}\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
            summary.write(explanation + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
