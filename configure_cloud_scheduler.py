"""Configure one Google timer; validate without paid generation before activation."""

import argparse
import base64
from copy import deepcopy
import getpass
import json
from pathlib import Path


CONFIG = Path(__file__).with_name("cloud_scheduler_job.json")
TARGET = "https://api.github.com/repos/AIConvoCast/AIConvoCast/actions/workflows/ai_podcast_pipeline.yml/dispatches"


def build_job(token, ref="main", activate=False):
    if not token.startswith("github_pat_"):
        raise ValueError("Use a fine-grained GitHub token scoped to AIConvoCast/AIConvoCast with Actions write access.")
    if activate and ref != "main":
        raise ValueError("Production scheduling must target main.")
    job = deepcopy(json.loads(CONFIG.read_text(encoding="utf-8")))
    if job["httpTarget"]["uri"] != TARGET:
        raise ValueError("The scheduler target must be the AIConvoCast GitHub workflow.")
    body = {"ref": ref, "inputs": {"scheduled_run": True, "dry_run": not activate}}
    job["httpTarget"]["body"] = base64.b64encode(json.dumps(body).encode()).decode("ascii")
    job["httpTarget"]["headers"]["Authorization"] = f"Bearer {token}"
    return job


def configure(session, job, run_now=False):
    endpoint = "https://cloudscheduler.googleapis.com/v1/" + job["name"]
    response = session.get(endpoint, timeout=30)
    if response.status_code == 404:
        response = session.post(endpoint.rsplit("/", 1)[0], json=job, timeout=30)
    else:
        response.raise_for_status()
        existing = response.json()
        if existing.get("httpTarget", {}).get("uri") != TARGET:
            raise ValueError("An unrelated job already uses this name; refusing to overwrite it.")
        fields = ["description", "schedule", "timeZone", "attemptDeadline", "retryConfig", "httpTarget"]
        response = session.patch(endpoint, params={"updateMask": ",".join(fields)}, json=job, timeout=30)
    response.raise_for_status()
    if run_now:
        response = session.post(endpoint + ":run", json={}, timeout=30)
        response.raise_for_status()
    # Never print response bodies: Google's job resource includes the auth header.
    print("Configured " + job["name"])
    print("4:00 p.m. Eastern Sunday-Thursday, plus a 4:10 p.m. backup; one scheduler job.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", default="jmio-google-api.json")
    parser.add_argument("--token-file", help="Read the fine-grained token from a private file outside the repository.")
    parser.add_argument("--ref", default="main")
    parser.add_argument("--activate", action="store_true", help="Enable real generation after the validation dispatch passes.")
    parser.add_argument("--run-now", action="store_true", help="Dispatch a validation through Google immediately.")
    args = parser.parse_args()
    if args.activate and args.run_now:
        parser.error("--run-now is only allowed for validation, without --activate.")
    token = (Path(args.token_file).read_text(encoding="utf-8").strip() if args.token_file
             else getpass.getpass("Fine-grained GitHub scheduler token (hidden): ").strip())
    job = build_job(token, ref=args.ref, activate=args.activate)
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account
    credentials = service_account.Credentials.from_service_account_file(
        args.credentials, scopes=["https://www.googleapis.com/auth/cloud-platform"])
    configure(AuthorizedSession(credentials), job, run_now=args.run_now)
    print("Mode: " + ("production" if args.activate else "validation only; no podcast generation"))


if __name__ == "__main__":
    main()
