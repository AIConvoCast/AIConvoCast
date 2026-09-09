"""Resend the latest completed podcast and description without regenerating it."""

from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import storage

from podcast_email import DEFAULT_RECIPIENT, DEFAULT_SENDER, send_podcast_email


GCS_BUCKET_NAME = "jmio-podcast-storage"
AUDIO_PREFIX = "podcasts/"
DESCRIPTION_PREFIX = "descriptions/"
GOOGLE_CREDENTIALS_FILE = "jmio-google-api.json"


def _latest_merged_audio() -> Path:
    candidates = list(Path("generated_mp3").glob("merged_audio_*.mp3"))
    if not candidates:
        raise RuntimeError("No merged podcast MP3 exists in generated_mp3/.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _latest_description() -> tuple[str, str]:
    client = storage.Client.from_service_account_json(GOOGLE_CREDENTIALS_FILE)
    bucket = client.bucket(GCS_BUCKET_NAME)
    candidates = [
        blob
        for blob in bucket.list_blobs(prefix=DESCRIPTION_PREFIX)
        if blob.name.lower().endswith(".txt")
    ]
    if not candidates:
        raise RuntimeError(
            f"No description text file exists under gs://{GCS_BUCKET_NAME}/"
            f"{DESCRIPTION_PREFIX}."
        )
    latest_blob = max(candidates, key=lambda blob: blob.time_created)
    description = latest_blob.download_as_bytes().decode("utf-8").strip()
    if not description:
        raise RuntimeError(f"The latest description is empty: {latest_blob.name}")
    return description, latest_blob.name


def _latest_audio_blob_name() -> str:
    client = storage.Client.from_service_account_json(GOOGLE_CREDENTIALS_FILE)
    bucket = client.bucket(GCS_BUCKET_NAME)
    candidates = [
        blob
        for blob in bucket.list_blobs(prefix=AUDIO_PREFIX)
        if blob.name.lower().endswith(".mp3")
    ]
    if not candidates:
        raise RuntimeError(
            f"No podcast MP3 exists under gs://{GCS_BUCKET_NAME}/{AUDIO_PREFIX}."
        )
    return max(candidates, key=lambda blob: blob.time_created).name


def main() -> int:
    load_dotenv()
    audio_path = _latest_merged_audio()
    audio_blob = _latest_audio_blob_name()
    description, description_blob = _latest_description()
    workflow_match = re.search(r"merged_audio_(\d+)_step_", audio_path.name)
    workflow_id = workflow_match.group(1) if workflow_match else "resend"

    # This recovery path intentionally cannot use personal Gmail SMTP credentials.
    os.environ["PODCAST_EMAIL_BACKEND"] = "gmail_api"
    os.environ["PODCAST_EMAIL_FROM"] = DEFAULT_SENDER
    os.environ.setdefault("PODCAST_EMAIL_TO", DEFAULT_RECIPIENT)

    print(f"Audio: {audio_path}")
    print(f"Audio name: gs://{GCS_BUCKET_NAME}/{audio_blob}")
    print(f"Description: gs://{GCS_BUCKET_NAME}/{description_blob}")
    print(f"From: {DEFAULT_SENDER}")
    print(f"To: {os.environ['PODCAST_EMAIL_TO']}")
    send_podcast_email(
        audio_path,
        description,
        workflow_id=workflow_id,
        audio_filename=Path(audio_blob).name,
        description_filename=Path(description_blob).name,
    )
    print("Latest completed podcast email sent successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
