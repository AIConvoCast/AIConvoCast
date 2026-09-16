"""Create a local send-only Gmail OAuth grant for AI Convo Cast."""

from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from podcast_email import DEFAULT_GMAIL_TOKEN_FILE, GMAIL_SEND_SCOPE


DEFAULT_CLIENT_SECRETS_FILE = "client_secret.json"


def authorize_local_gmail(*, client_secrets=None, output=None, github_output=None,
                          open_browser=True, timeout_seconds=180):
    """Renew the local grant only. Never modify GitHub's working secret."""
    directory = Path(__file__).resolve().parent
    client_secrets_path = Path(client_secrets or directory / DEFAULT_CLIENT_SECRETS_FILE)
    token_path = Path(output or directory / DEFAULT_GMAIL_TOKEN_FILE)
    github_path = Path(github_output or directory / "gmail_oauth_token.b64")
    if not client_secrets_path.is_file():
        raise FileNotFoundError(f"Google OAuth Desktop client file is missing: {client_secrets_path}")
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_path), scopes=[GMAIL_SEND_SCOPE])
    credentials = flow.run_local_server(
        host="localhost", port=0, access_type="offline", prompt="consent",
        login_hint="AIConvoCast@gmail.com", open_browser=open_browser,
        timeout_seconds=timeout_seconds,
        authorization_prompt_message="Sign in as AIConvoCast@gmail.com to restore local email:\n{url}",
        success_message="AI Convo Cast local email authorization completed. You may close this tab.",
    )
    token_json = credentials.to_json()
    token_path.write_text(token_json, encoding="utf-8")
    github_path.write_text(base64.b64encode(token_json.encode()).decode("ascii"), encoding="ascii")
    for path in (token_path, github_path):
        try:
            path.chmod(0o600)
        except OSError:
            pass
    print(f"Local Gmail grant saved to {token_path}. GitHub credentials were not changed.")
    return credentials


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Authorize the AIConvoCast Gmail account with send-only access. "
            "No Gmail password or app password is collected."
        )
    )
    parser.add_argument(
        "--client-secrets",
        default=os.getenv(
            "GMAIL_OAUTH_CLIENT_SECRETS_FILE",
            DEFAULT_CLIENT_SECRETS_FILE,
        ),
        help="Google OAuth Desktop client JSON file (default: client_secret.json)",
    )
    parser.add_argument(
        "--output",
        default=os.getenv("GMAIL_OAUTH_TOKEN_FILE", DEFAULT_GMAIL_TOKEN_FILE),
        help=f"Authorized-user token output (default: {DEFAULT_GMAIL_TOKEN_FILE})",
    )
    parser.add_argument(
        "--github-secret-output",
        default="gmail_oauth_token.b64",
        help="Base64 token output for GitHub (default: gmail_oauth_token.b64)",
    )
    parser.add_argument("--no-browser", action="store_true", help="Print the login link without opening a browser.")
    parser.add_argument("--timeout", type=int, default=180, help="Seconds to wait for local sign-in.")
    args = parser.parse_args()

    client_secrets_path = Path(args.client_secrets)
    token_path = Path(args.output)
    github_secret_path = Path(args.github_secret_output)
    if not client_secrets_path.is_file():
        parser.error(
            f"OAuth client file not found: {client_secrets_path}. Download a "
            "Desktop app OAuth client from Google Cloud first."
        )

    try:
        authorize_local_gmail(client_secrets=client_secrets_path, output=token_path,
                              github_output=github_secret_path, open_browser=not args.no_browser,
                              timeout_seconds=args.timeout)
    except Exception as exc:
        print(f"Local Google sign-in did not complete ({type(exc).__name__}). "
              "Run this command again when ready to finish the browser sign-in. "
              "GitHub credentials were not changed.")
        return 1

    print(f"Created send-only OAuth token: {token_path}")
    print(f"Created GitHub-ready secret file: {github_secret_path}")
    print("Keep both files private; repository ignore rules cover both files.")
    print(
        "GitHub's existing email authorization is unchanged. Only update its "
        "GMAIL_OAUTH_TOKEN_B64 secret if GitHub delivery also needs reauthorization."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
