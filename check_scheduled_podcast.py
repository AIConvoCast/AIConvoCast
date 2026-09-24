"""Allow one automatic podcast per Eastern day, at or after 4 p.m."""

import argparse
from datetime import datetime, time, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import time as clock
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


EASTERN = ZoneInfo("America/New_York")
# Generation step names in the V1 and V2 workflows.
GENERATION_STEPS = {"Run AI Podcast Pipeline", "Run AI Podcast V2"}
WARMUP_HOUR = 12
TARGET_HOUR = 16


def generation_started(repository, run, api_get):
    """A skipped/preflight-only run must not consume the day's automatic episode."""
    path = f"/repos/{repository}/actions/runs/{run['id']}/jobs"
    for page in range(1, 11):
        jobs = api_get(path, {"filter": "all", "per_page": 100, "page": page})["jobs"]
        for job in jobs:
            for step in job.get("steps", []):
                if step["name"] in GENERATION_STEPS and (
                    step["status"] == "in_progress"
                    or (step["status"] == "completed" and step.get("conclusion") != "skipped")
                ):
                    # Even a failed/cancelled generation can have paid for or
                    # published an episode. Leave retries to a manual trigger.
                    return True
        if len(jobs) < 100:
            return False
    raise RuntimeError("GitHub job history exceeded the pagination limit")


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


def evaluate_run(event_name, repository, run_id, api_get=github_api_get, now=None,
                 allow_early=False):
    """Return (should_run, explanation); API errors must prevent automatic runs."""
    if event_name == "workflow_dispatch":
        return True, "Manual trigger: run the podcast as requested."
    if event_name != "schedule":
        raise ValueError(f"Unsupported podcast trigger: {event_name}")

    now = now or datetime.now(timezone.utc)
    local_now = now.astimezone(EASTERN)
    if local_now.weekday() in {4, 5}:
        return False, "Automatic podcast skipped: Friday/Saturday in Eastern time."
    if local_now.hour < (WARMUP_HOUR if allow_early else TARGET_HOUR):
        return False, "Automatic podcast skipped: it is not yet 4:00 p.m. Eastern."

    current = api_get(f"/repos/{repository}/actions/runs/{run_id}")
    day = parse_timestamp(current["created_at"]).astimezone(EASTERN).date()
    if day != local_now.date():
        return False, "Automatic podcast skipped: this trigger is from a different Eastern day."
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
            "created": created_range, "per_page": 100, "page": page,
        })
        runs = response["workflow_runs"]
        for run in runs:
            triggered = parse_timestamp(run["created_at"])
            if (str(run["id"]) == str(run_id) or run["workflow_id"] != workflow_id
                    or not earliest <= triggered <= latest):
                continue
            if run["event"] == "workflow_dispatch":
                # The user requested any manual trigger, regardless of outcome.
                return False, (
                    f"Scheduled podcast skipped: manual run {run['id']} was triggered "
                    f"on {day} Eastern time. {run['html_url']}"
                )
            if run["event"] == "schedule" and generation_started(repository, run, api_get):
                return False, (
                    f"Scheduled podcast skipped: automatic run {run['id']} already "
                    f"started generation on {day} Eastern time. {run['html_url']}"
                )
        if len(runs) < 100:
            break
        if page >= 10:
            raise RuntimeError("GitHub history exceeded the 1,000-run search limit")
        page += 1
    return True, f"No manual trigger or prior automatic generation on {day} Eastern time."


def wait_until_target(now_fn=None, sleep_fn=clock.sleep):
    """Use the runner's actual clock, not a predicted GitHub dispatch delay."""
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    local_now = now_fn().astimezone(EASTERN)
    target = datetime.combine(local_now.date(), time(TARGET_HOUR), tzinfo=EASTERN)
    if local_now < target:
        print(f"Runner ready; waiting until {target.isoformat()} to start the podcast.", flush=True)
    while local_now < target:
        sleep_fn(min(60, (target - local_now).total_seconds()))
        local_now = now_fn().astimezone(EASTERN)
    if local_now.date() != target.date():
        raise RuntimeError("The waiting runner resumed on a different Eastern day")
    print(f"4:00 p.m. target reached; actual Eastern time: {local_now.isoformat()}", flush=True)


def main(wait=False):
    try:
        event_name = os.environ["GITHUB_EVENT_NAME"]
        repository = os.environ["GITHUB_REPOSITORY"]
        run_id = os.environ["GITHUB_RUN_ID"]
        should_run, explanation = evaluate_run(
            event_name, repository, run_id, allow_early=wait,
        )
        if should_run and wait and event_name == "schedule":
            wait_until_target()
            # A manual trigger during the wait must still suppress this episode.
            should_run, explanation = evaluate_run(event_name, repository, run_id)
    except Exception as error:
        print(f"Could not verify run history; automatic generation stopped: {error}", file=sys.stderr)
        return 1

    print(explanation)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.write(f"should_run={str(should_run).lower()}\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
            summary.write(explanation + "\n")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait-until-target", action="store_true",
                        help="Allow a runner from noon Eastern, then wait until 4 p.m.")
    sys.exit(main(wait=parser.parse_args().wait_until_target))
