"""Bounded retries for operations that are safe to repeat."""

import random
import time
import smtplib

import requests
import httpx
from google.auth.exceptions import TransportError


def is_transient_error(exc):
    text = str(exc).lower()
    if any(marker in text for marker in (
        "invalid_grant", "quota_exceeded", "insufficient_quota",
        "insufficient credits", "payment_required", "invalid_api_key",
    )):
        return False
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None) or getattr(exc, "status_code", None)
    status = status or getattr(getattr(exc, "resp", None), "status", None)
    code = getattr(exc, "code", None)
    if status is None and isinstance(code, int):
        status = code
    if status is not None:
        return status in {408, 429, 500, 502, 503, 504}
    if isinstance(exc, smtplib.SMTPResponseException):
        return 400 <= exc.smtp_code < 500
    return isinstance(exc, (ConnectionError, TimeoutError, requests.ConnectionError,
                            requests.Timeout, TransportError, httpx.TransportError,
                            smtplib.SMTPServerDisconnected)) or bool(
        getattr(exc, "retryable", False)
    )


def retry_transient(operation, *, attempts=3, label="Connection", predicate=is_transient_error):
    """Retry only known transient failures; never print credential-bearing errors."""
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:
            if attempt == attempts - 1 or not predicate(exc):
                raise
            delay = min(2 ** (attempt + 1), 8) + random.uniform(0, 0.5)
            print(f"{label}: temporary failure; retrying ({attempt + 2}/{attempts}).")
            time.sleep(delay)


def elevenlabs_audio_with_retry(client, **kwargs):
    # Consume the stream inside the retry boundary. Discard partial bytes and
    # retry only this chunk; disable nested SDK retries.
    return (retry_transient(
        lambda: b"".join(client.text_to_speech.convert(
            **kwargs, request_options={"max_retries": 0, "timeout_in_seconds": 180}
        )), label="ElevenLabs audio",
    ),)
