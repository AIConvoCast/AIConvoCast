"""Email delivery for completed AI Convo Cast podcast runs."""

from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import os
import smtplib
import ssl
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
from email import policy
from email.parser import BytesParser
from email.utils import formatdate, make_msgid
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from service_retry import retry_transient


DEFAULT_RECIPIENT = "ianeoconnell@gmail.com"
DEFAULT_SENDER = "AIConvoCast@gmail.com"
DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 465
DEFAULT_GMAIL_TOKEN_FILE = "gmail_oauth_token.json"
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


class DeliveryNotAttempted(RuntimeError):
    """An alternate backend is safe because no message was submitted."""


class DeliveryRejected(RuntimeError):
    """The server explicitly rejected the message; it was not accepted."""


class DeliveryUncertain(RuntimeError):
    """Do not automatically resend: the server may have accepted the message."""


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise DeliveryNotAttempted(
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
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[-1])
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


def _load_gmail_oauth_credentials(*, force_refresh=False) -> Credentials:
    """Load a send-only Gmail OAuth grant from an env secret or local file."""
    token_b64 = os.getenv("GMAIL_OAUTH_TOKEN_B64", "").strip()
    token_json = os.getenv("GMAIL_OAUTH_TOKEN_JSON", "").strip()
    default_token_file = Path(__file__).resolve().with_name(DEFAULT_GMAIL_TOKEN_FILE)
    token_file = Path(os.getenv("GMAIL_OAUTH_TOKEN_FILE", "").strip() or default_token_file)

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
    if force_refresh or not credentials.valid:
        try:
            retry_transient(lambda: credentials.refresh(Request()), label="Gmail authorization")
        except Exception as exc:
            raise RuntimeError(
                "The Gmail OAuth grant could not be refreshed. Reauthorize "
                "AIConvoCast with configure_gmail_oauth.py. For GitHub runs, also "
                "replace GMAIL_OAUTH_TOKEN_B64 in the production environment secrets."
            ) from exc
    return credentials


def _send_with_gmail_api(message: EmailMessage, credentials=None) -> None:
    try:
        if credentials is None:
            credentials = _load_gmail_oauth_credentials()
        service = retry_transient(
            lambda: build("gmail", "v1", credentials=credentials, cache_discovery=False),
            label="Gmail connection",
        )
    except Exception as exc:
        raise DeliveryNotAttempted(
            "Gmail could not connect or authorize. An expired/revoked grant requires "
            "configure_gmail_oauth.py; temporary connection failures were retried."
        ) from exc
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    try:
        # Retry an explicit rate-limit rejection. Timeouts/5xx after submission
        # are ambiguous, so do not automatically send a duplicate via SMTP.
        retry_transient(
            lambda: service.users().messages().send(userId="me", body={"raw": raw_message}).execute(),
            label="Gmail rate limit",
            predicate=lambda exc: isinstance(exc, HttpError) and exc.resp.status == 429,
        )
    except HttpError as exc:
        if 400 <= exc.resp.status < 500 and exc.resp.status != 408:
            raise DeliveryRejected(f"Gmail rejected delivery (HTTP {exc.resp.status}).") from exc
        raise DeliveryUncertain("Gmail delivery was not confirmed; check Sent before resending.") from exc
    except Exception as exc:
        raise DeliveryUncertain("Gmail delivery was not confirmed; check Sent before resending.") from exc


def _connect_smtp():
    """Authenticate without submitting a message, for delivery or preflight."""
    username = _required_env("PODCAST_SMTP_USERNAME")
    password = _required_env("PODCAST_SMTP_PASSWORD")
    host = os.getenv("PODCAST_SMTP_HOST", DEFAULT_SMTP_HOST).strip()

    try:
        port = int(os.getenv("PODCAST_SMTP_PORT", str(DEFAULT_SMTP_PORT)))
    except ValueError as exc:
        raise RuntimeError("PODCAST_SMTP_PORT must be a number.") from exc

    def connect():
        smtp = smtplib.SMTP_SSL(host, port, timeout=60, context=ssl.create_default_context())
        try:
            smtp.login(username, password)
            return smtp
        except Exception:
            smtp.close()
            raise

    try:
        return retry_transient(connect, label="SMTP connection")
    except Exception as exc:
        raise DeliveryNotAttempted("SMTP could not connect or authenticate.") from exc


def _send_with_smtp(message: EmailMessage) -> None:
    smtp = _connect_smtp()
    try:
        retry_transient(
            lambda: smtp.send_message(message),
            label="SMTP rate limit",
            predicate=lambda exc: isinstance(exc, smtplib.SMTPDataError) and 400 <= exc.smtp_code < 500,
        )
    except (smtplib.SMTPDataError, smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused) as exc:
        raise DeliveryRejected("SMTP rejected the email; it remains saved locally.") from exc
    except Exception as exc:
        raise DeliveryUncertain("SMTP delivery was not confirmed; check Sent before resending.") from exc
    finally:
        # A failed QUIT must not turn a successful send into a retry.
        smtp.close()


def _smtp_fallback_enabled():
    return bool(os.getenv("PODCAST_SMTP_USERNAME") and os.getenv("PODCAST_SMTP_PASSWORD")
                and os.getenv("PODCAST_SMTP_FALLBACK", "true").lower() not in {"0", "false", "no"})


def check_email_authorization():
    """Check a usable delivery credential before paid generation; send no email."""
    backend = os.getenv("PODCAST_EMAIL_BACKEND", "gmail_api").strip().lower()
    if backend not in {"gmail_api", "smtp"}:
        raise RuntimeError("PODCAST_EMAIL_BACKEND must be either 'gmail_api' or 'smtp'.")
    if backend == "gmail_api":
        try:
            # A cached access token can still be valid after its grant expires.
            _load_gmail_oauth_credentials(force_refresh=True)
            return "gmail_api"
        except Exception as gmail_error:
            if not _smtp_fallback_enabled():
                raise RuntimeError(
                    "Gmail authorization failed before generation. Run python "
                    "configure_gmail_oauth.py locally, then replace GMAIL_OAUTH_TOKEN_B64 "
                    "in GitHub's production environment secrets with gmail_oauth_token.b64. "
                    "Temporary connection failures were retried; no email was sent."
                ) from gmail_error
            print("Gmail authorization failed; checking the configured SMTP fallback.")
    try:
        smtp = _connect_smtp()
        smtp.close()
    except Exception as exc:
        raise RuntimeError(
            "Email authorization failed before generation. Repair the configured "
            "Gmail grant or SMTP credentials; no email was sent."
        ) from exc
    return "smtp"


def _deliver(message, backend):
    if backend == "smtp":
        _send_with_smtp(message)
        return "smtp"
    try:
        _send_with_gmail_api(message)
        return "gmail_api"
    except (DeliveryNotAttempted, DeliveryRejected) as gmail_error:
        if _smtp_fallback_enabled():
            print("Gmail did not accept the message; using the configured SMTP fallback.")
            try:
                _send_with_smtp(message)
                return "smtp"
            except (DeliveryNotAttempted, DeliveryRejected):
                pass  # Both attempts definitively failed before acceptance.
        # Only an interactive local run may renew an expired local grant.
        # Never prompt on a GitHub runner, retry ambiguous delivery, or replace
        # an explicitly supplied token secret with a different credential.
        if _can_renew_local_grant(gmail_error):
            from configure_gmail_oauth import authorize_local_gmail
            print("Local Gmail authorization expired. Complete the Google sign-in to deliver this saved episode.")
            try:
                credentials = authorize_local_gmail()
            except Exception as exc:
                raise DeliveryNotAttempted("Local sign-in was not completed. Run python configure_gmail_oauth.py, then resend the saved email.") from exc
            _send_with_gmail_api(message, credentials=credentials)
            return "gmail_api"
        raise gmail_error


def _can_renew_local_grant(error):
    if (os.getenv("GITHUB_ACTIONS") or not sys.stdin.isatty()
            or os.getenv("GMAIL_OAUTH_TOKEN_B64") or os.getenv("GMAIL_OAUTH_TOKEN_JSON")
            or os.getenv("GMAIL_OAUTH_TOKEN_FILE")
            or os.getenv("PODCAST_LOCAL_REAUTHORIZE", "true").lower() in {"0", "false", "no"}):
        return False
    while error is not None:
        if "invalid_grant" in str(error).lower():
            return True
        error = error.__cause__
    return False


def _write_status(path, state, **details):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"status": state, "updated_at": datetime.now(timezone.utc).isoformat(),
                                     **details}, indent=2), encoding="utf-8")
    temporary.replace(path)


def _deliver_saved(message, message_path, backend):
    status_path = message_path.with_suffix(".json")
    # A crash during submission has an unknown result; never auto-resend it.
    _write_status(status_path, "sending", message_id=str(message["Message-ID"]))
    try:
        used_backend = _deliver(message, backend)
    except Exception as exc:
        state = "failed" if isinstance(exc, (DeliveryNotAttempted, DeliveryRejected)) else "uncertain"
        _write_status(status_path, state, error_type=type(exc).__name__)
        print(f"Email {state}. Audio and description are preserved in {message_path}")
        raise
    _write_status(status_path, "sent", backend=used_backend)


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

    outbox = Path(os.getenv("PODCAST_EMAIL_OUTBOX", str(Path(audio_path).parent / "email_outbox")))
    outbox.mkdir(parents=True, exist_ok=True)
    message_path = outbox / (str(message["Message-ID"]).strip("<>").split("@")[0] + ".eml")
    with message_path.open("xb") as stream:
        stream.write(message.as_bytes())
    _deliver_saved(message, message_path, backend)


def resend_saved_email(path, *, allow_uncertain=False):
    """Explicit recovery command; never regenerate audio or silently duplicate mail."""
    path = Path(path)
    status_path = path.with_suffix(".json")
    state = json.loads(status_path.read_text(encoding="utf-8")).get("status") if status_path.exists() else "uncertain"
    if state == "sent":
        raise RuntimeError("This email was already sent.")
    if state in {"sending", "uncertain"} and not allow_uncertain:
        raise RuntimeError("Check Sent first, then use --confirm-not-delivered if the email is missing.")
    message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    _deliver_saved(message, path, os.getenv("PODCAST_EMAIL_BACKEND", "gmail_api"))


def main(argv=None):
    import argparse
    from dotenv import load_dotenv
    load_dotenv()
    parser = argparse.ArgumentParser(description="Check email authorization or resend a saved podcast email.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--resend", type=Path)
    action.add_argument("--check-auth", action="store_true", help="Validate credentials without sending email or generating audio.")
    parser.add_argument("--confirm-not-delivered", action="store_true")
    args = parser.parse_args(argv)
    if args.check_auth:
        try:
            backend = check_email_authorization()
        except RuntimeError as exc:
            print(str(exc))
            return 1
        print(f"Email authorization verified via {backend}. No email sent.")
    else:
        resend_saved_email(args.resend, allow_uncertain=args.confirm_not_delivered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
