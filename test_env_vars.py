#!/usr/bin/env python3
"""
Simple script to test environment variables in GitHub Actions.
"""

import os
from pathlib import Path

from dotenv import load_dotenv


def test_environment_variables():
    """Test if environment variables are properly set."""
    print("Testing Environment Variables in GitHub Actions...")

    # Load .env file if it exists
    load_dotenv()

    # Check each required variable
    required_vars = [
        "OPENAI_API_KEY",
        "ELEVENLABS_API_KEY",
        "SHARE_SHEET_WITH_EMAIL",
        "ANTHROPIC_API_KEY",
    ]

    email_backend = os.getenv("PODCAST_EMAIL_BACKEND", "gmail_api").strip().lower()
    if email_backend == "gmail_api":
        required_vars.append("PODCAST_EMAIL_FROM")
    elif email_backend == "smtp":
        required_vars.extend(["PODCAST_SMTP_USERNAME", "PODCAST_SMTP_PASSWORD"])
    else:
        print(f"INVALID PODCAST_EMAIL_BACKEND: {email_backend}")
        return False

    all_good = True
    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"OK {var}: set (length: {len(value)})")
        else:
            print(f"MISSING {var}: Not set")
            all_good = False

    if email_backend == "gmail_api":
        token_b64_set = bool(os.getenv("GMAIL_OAUTH_TOKEN_B64", "").strip())
        token_json_set = bool(os.getenv("GMAIL_OAUTH_TOKEN_JSON", "").strip())
        token_file = Path(
            os.getenv("GMAIL_OAUTH_TOKEN_FILE", "gmail_oauth_token.json")
        )
        if token_b64_set:
            print("OK GMAIL_OAUTH_TOKEN_B64: set (value hidden)")
        elif token_json_set:
            print("OK GMAIL_OAUTH_TOKEN_JSON: set (value hidden)")
        elif token_file.is_file():
            print(f"OK Gmail OAuth token file: {token_file}")
        else:
            print(
                "MISSING Gmail OAuth authorization: set GMAIL_OAUTH_TOKEN_B64 "
                "or run python configure_gmail_oauth.py"
            )
            all_good = False

    # Check if we're in GitHub Actions
    if os.getenv("GITHUB_ACTIONS"):
        print("\nRunning in GitHub Actions")
        print(f"   Workflow: {os.getenv('GITHUB_WORKFLOW', 'Unknown')}")
        print(f"   Run ID: {os.getenv('GITHUB_RUN_ID', 'Unknown')}")
        print(f"   Environment: {os.getenv('GITHUB_ENV', 'Not set')}")
    else:
        print("\nRunning locally")

    return all_good


if __name__ == "__main__":
    success = test_environment_variables()
    if success:
        print("\nAll environment variables are properly configured!")
    else:
        print("\nSome environment variables are missing!")
        print("Please check your GitHub environment configuration.")

    exit(0 if success else 1)
