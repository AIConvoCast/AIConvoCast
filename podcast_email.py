"""Email delivery for completed AI Convo Cast podcast runs."""

from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


DEFAULT_RECIPIENT = "ianeoconnell@gmail.com"
DEFAULT_SENDER = "AIConvoCast@gmail.com"
DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 465
DEFAULT_GMAIL_TOKEN_FILE = "gmail_oauth_token.json"
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Email delivery is not configured: set {name} in the local .env "
            "file and as a GitHub Actions secret."
        )
    return value


def _attachment_type(path: Path) -> tuple[str, str]:
    guessed_type, _ = mimetypes.guess_type(path.name)
    if guessed_type and "/" in guessed_type:
        main_type, sub_type = guessed_type.split("/", 1)
        return main_type, sub_type
    return "application", "octet-stream"


def _attachment_filename(requested_name: str | None, fallback: str) -> str:
    """Return a safe attachment basename, preserving the supplied GCS name."""
    if requested_name is None:
        return fallback

    filename = Path(str(requested_name).strip()).name
    if not filename:
        raise ValueError("Email attachment filename cannot be empty.")
    return filename


def build_podcast_email(
    audio_path: str | Path,
    description_text: str,
    *,
    workflow_id: str | int,
    sender: str,
    recipient: str = DEFAULT_RECIPIENT,
    audio_filename: str | None = None,
    description_filename: str | None = None,
) -> EmailMessage:
    """Build one message containing both the final MP3 and description text file."""
    audio_file = Path(audio_path)
    if not audio_file.is_file():
        raise FileNotFoundError(f"Final podcast audio was not found: {audio_file}")

    description_text = str(description_text or "").strip()
    if not description_text:
        raise RuntimeError("The podcast title and description output is empty.")

    title = ""
    for line in description_text.splitlines():
        if line.lower().lstrip("# ").startswith("title:"):
            title = line.split(":", 1)[1].strip()
            break

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = title or f"AI Convo Cast - workflow {workflow_id}"
    message.set_content(
        "Your AI Convo Cast generation completed successfully.\n\n"
        "The final podcast audio and its title/description script are attached "
        "to this email.\n\n"
        f"{description_text}\n"
    )

    audio_main_type, audio_sub_type = _attachment_type(audio_file)
    attachment_audio_filename = _attachment_filename(
        audio_filename,
        audio_file.name,
    )
    message.add_attachment(
        audio_file.read_bytes(),
        maintype=audio_main_type,
        subtype=audio_sub_type,
        filename=attachment_audio_filename,
    )

    attachment_description_filename = _attachment_filename(
        description_filename,
        f"{audio_file.stem}_description.txt",
    )
    message.add_attachment(
        description_text.encode("utf-8"),
        maintype="text",
        subtype="plain",
        filename=attachment_description_filename,
    )
    return message


def _load_gmail_oauth_credentials() -> Credentials:
    """Load a send-only Gmail OAuth grant from an env secret or local file."""
    token_b64 = os.getenv("GMAIL_OAUTH_TOKEN_B64", "").strip()
    token_json = os.getenv("GMAIL_OAUTH_TOKEN_JSON", "").strip()
    token_file = Path(
        os.getenv("GMAIL_OAUTH_TOKEN_FILE", DEFAULT_GMAIL_TOKEN_FILE).strip()
        or DEFAULT_GMAIL_TOKEN_FILE
    )

    if token_b64:
        try:
            token_json = base64.b64decode(token_b64, validate=True).decode("utf-8")
            token_info = json.loads(token_json)
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "GMAIL_OAUTH_TOKEN_B64 is not valid base64-encoded token JSON."
            ) from exc
    elif token_json:
        try:
            token_info = json.loads(token_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError("GMAIL_OAUTH_TOKEN_JSON is not valid JSON.") from exc
    elif token_file.is_file():
        try:
            token_info = json.loads(token_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Could not read Gmail OAuth credentials from {token_file}."
            ) from exc
    else:
        raise RuntimeError(
            "Gmail API email delivery is not configured. Run "
            "'python configure_gmail_oauth.py' locally, then add the generated "
            "token as the GMAIL_OAUTH_TOKEN_B64 GitHub secret."
        )

    credentials = Credentials.from_authorized_user_info(
        token_info,
        scopes=[GMAIL_SEND_SCOPE],
    )
    if not credentials.refresh_token:
        raise RuntimeError(
            "The Gmail OAuth grant has no refresh token. Run "
            "'python configure_gmail_oauth.py' again to reauthorize."
        )
    if not credentials.valid:
        try:
            credentials.refresh(Request())
        except Exception as exc:
            raise RuntimeError(
                "The Gmail OAuth grant could not be refreshed. Reauthorize "
                "AIConvoCast with configure_gmail_oauth.py."
            ) from exc
    return credentials


def _send_with_gmail_api(message: EmailMessage) -> None:
    credentials = _load_gmail_oauth_credentials()
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    service = build(
        "gmail",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )
    service.users().messages().send(
        userId="me",
        body={"raw": raw_message},
    ).execute()


def _send_with_smtp(message: EmailMessage) -> None:
    username = _required_env("PODCAST_SMTP_USERNAME")
    password = _required_env("PODCAST_SMTP_PASSWORD")
    host = os.getenv("PODCAST_SMTP_HOST", DEFAULT_SMTP_HOST).strip()

    try:
        port = int(os.getenv("PODCAST_SMTP_PORT", str(DEFAULT_SMTP_PORT)))
    except ValueError as exc:
        raise RuntimeError("PODCAST_SMTP_PORT must be a number.") from exc

    with smtplib.SMTP_SSL(host, port, timeout=60) as smtp:
        smtp.login(username, password)
        smtp.send_message(message)


def send_podcast_email(
    audio_path: str | Path,
    description_text: str,
    *,
    workflow_id: str | int,
    audio_filename: str | None = None,
    description_filename: str | None = None,
) -> None:
    """Send the completed podcast using Gmail API OAuth or legacy SMTP."""
    backend = os.getenv("PODCAST_EMAIL_BACKEND", "gmail_api").strip().lower()
    if backend not in {"gmail_api", "smtp"}:
        raise RuntimeError(
            "PODCAST_EMAIL_BACKEND must be either 'gmail_api' or 'smtp'."
        )

    if backend == "gmail_api":
        sender = os.getenv("PODCAST_EMAIL_FROM", DEFAULT_SENDER).strip()
    else:
        sender = os.getenv(
            "PODCAST_EMAIL_FROM",
            os.getenv("PODCAST_SMTP_USERNAME", ""),
        ).strip()
        if not sender:
            sender = _required_env("PODCAST_SMTP_USERNAME")
    recipient = os.getenv("PODCAST_EMAIL_TO", DEFAULT_RECIPIENT).strip()

    message = build_podcast_email(
        audio_path,
        description_text,
        workflow_id=workflow_id,
        sender=sender,
        recipient=recipient,
        audio_filename=audio_filename,
        description_filename=description_filename,
    )

    if backend == "gmail_api":
        _send_with_gmail_api(message)
    else:
        _send_with_smtp(message)
