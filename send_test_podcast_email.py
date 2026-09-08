"""Send the latest local podcast MP3 through the Gmail API OAuth backend."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from podcast_email import DEFAULT_RECIPIENT, DEFAULT_SENDER, send_podcast_email


def _latest_merged_audio() -> Path | None:
    candidates = list(Path("generated_mp3").glob("merged_audio_*.mp3"))
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description=(
            "Send an existing local MP3 to verify AIConvoCast Gmail OAuth "
            "without running the generation pipeline."
        )
    )
    parser.add_argument(
        "--audio",
        type=Path,
        default=_latest_merged_audio(),
        help="MP3 to attach (default: newest generated_mp3/merged_audio_*.mp3)",
    )
    parser.add_argument(
        "--to",
        default=os.getenv("PODCAST_EMAIL_TO", DEFAULT_RECIPIENT),
        help=f"Recipient (default: {DEFAULT_RECIPIENT})",
    )
    args = parser.parse_args()

    if args.audio is None or not args.audio.is_file():
        parser.error("No merged MP3 was found; pass an existing file with --audio.")

    # Force this diagnostic to exercise OAuth only; never fall back to SMTP.
    os.environ["PODCAST_EMAIL_BACKEND"] = "gmail_api"
    os.environ["PODCAST_EMAIL_FROM"] = DEFAULT_SENDER
    os.environ["PODCAST_EMAIL_TO"] = args.to

    send_podcast_email(
        args.audio,
        (
            "Title: AI Convo Cast OAuth Delivery Test\n"
            "Description: This message verifies send-only Gmail API OAuth "
            "delivery from AIConvoCast without using Ian's Gmail credentials."
        ),
        workflow_id="oauth-test",
    )
    print(f"OAuth test email sent from {DEFAULT_SENDER} to {args.to}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
