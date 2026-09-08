"""Create a local send-only Gmail OAuth grant for AI Convo Cast."""

from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from podcast_email import DEFAULT_GMAIL_TOKEN_FILE, GMAIL_SEND_SCOPE


DEFAULT_CLIENT_SECRETS_FILE = "client_secret.json"


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
    args = parser.parse_args()

    client_secrets_path = Path(args.client_secrets)
    token_path = Path(args.output)
    github_secret_path = Path(args.github_secret_output)
    if not client_secrets_path.is_file():
        parser.error(
            f"OAuth client file not found: {client_secrets_path}. Download a "
            "Desktop app OAuth client from Google Cloud first."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secrets_path),
        scopes=[GMAIL_SEND_SCOPE],
    )
    credentials = flow.run_local_server(
        host="localhost",
        port=0,
        access_type="offline",
        prompt="consent",
        authorization_prompt_message=(
            "Open this URL and sign in specifically as AIConvoCast@gmail.com:\n{url}"
        ),
        success_message=(
            "AI Convo Cast send-only authorization completed. You may close this tab."
        ),
    )

    token_json = credentials.to_json()
    token_path.write_text(token_json, encoding="utf-8")
    github_secret_path.write_text(
        base64.b64encode(token_json.encode("utf-8")).decode("ascii"),
        encoding="ascii",
    )
    try:
        token_path.chmod(0o600)
        github_secret_path.chmod(0o600)
    except OSError:
        pass

    print(f"Created send-only OAuth token: {token_path}")
    print(f"Created GitHub-ready secret file: {github_secret_path}")
    print("Keep both files private; repository ignore rules cover both files.")
    print(
        "For GitHub Actions, create a production environment secret named "
        "GMAIL_OAUTH_TOKEN_B64 and paste the entire .b64 file contents into it."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
