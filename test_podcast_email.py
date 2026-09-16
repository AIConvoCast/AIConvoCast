import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from podcast_email import (
    GMAIL_SEND_SCOPE,
    _load_gmail_oauth_credentials,
    build_podcast_email,
    send_podcast_email,
)


class PodcastEmailTests(unittest.TestCase):
    def test_build_email_attaches_audio_and_description_together(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "episode.mp3"
            audio_path.write_bytes(b"fake mp3")

            message = build_podcast_email(
                audio_path,
                "Title: The Test Episode\nDescription: Test description.",
                workflow_id=43,
                sender="sender@example.com",
            )

        self.assertEqual(message["To"], "ianeoconnell@gmail.com")
        self.assertEqual(message["Subject"], "The Test Episode")
        self.assertIn("Description: Test description.", message.get_body().get_content())
        attachments = list(message.iter_attachments())
        self.assertEqual(len(attachments), 2)
        self.assertEqual(attachments[0].get_filename(), "episode.mp3")
        self.assertEqual(
            attachments[1].get_filename(), "episode_description.txt"
        )
        self.assertIn(
            b"Description: Test description.",
            attachments[1].get_payload(decode=True),
        )

    def test_build_email_uses_exact_gcs_attachment_filenames(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "merged_audio_47_step_9.mp3"
            audio_path.write_bytes(b"fake mp3")

            message = build_podcast_email(
                audio_path,
                "Title: The Test Episode\nDescription: Test description.",
                workflow_id=47,
                sender="sender@example.com",
                audio_filename="podcasts/20260909_120000_The_Test_Episode.mp3",
                description_filename=(
                    "descriptions/20260909_115900_The_Test_Episode.txt"
                ),
            )

        attachments = list(message.iter_attachments())
        self.assertEqual(
            attachments[0].get_filename(),
            "20260909_120000_The_Test_Episode.mp3",
        )
        self.assertEqual(
            attachments[1].get_filename(),
            "20260909_115900_The_Test_Episode.txt",
        )

    @patch("podcast_email.smtplib.SMTP_SSL")
    def test_send_uses_one_smtp_message(self, smtp_ssl):
        smtp = MagicMock()
        smtp_ssl.return_value = smtp

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "episode.mp3"
            audio_path.write_bytes(b"fake mp3")
            with patch.dict(
                os.environ,
                {
                    "PODCAST_EMAIL_BACKEND": "smtp",
                    "PODCAST_SMTP_USERNAME": "sender@example.com",
                    "PODCAST_SMTP_PASSWORD": "app-password",
                },
                clear=True,
            ):
                send_podcast_email(
                    audio_path,
                    "Title: Test\nDescription: Together.",
                    workflow_id=43,
                )

        smtp.login.assert_called_once_with("sender@example.com", "app-password")
        smtp.send_message.assert_called_once()

    def test_send_requires_credentials(self):
        with patch.dict(
            os.environ,
            {"PODCAST_EMAIL_BACKEND": "smtp"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "PODCAST_SMTP_USERNAME"):
                send_podcast_email(
                    "missing.mp3",
                    "Title: Test\nDescription: Test.",
                    workflow_id=43,
                )

    @patch("podcast_email.build")
    @patch("podcast_email._load_gmail_oauth_credentials")
    def test_gmail_api_uses_aiconvocast_sender_without_smtp_credentials(
        self,
        load_credentials,
        build_service,
    ):
        load_credentials.return_value = MagicMock()
        gmail_service = MagicMock()
        build_service.return_value = gmail_service

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "episode.mp3"
            audio_path.write_bytes(b"fake mp3")
            with patch.dict(
                os.environ,
                {
                    "PODCAST_EMAIL_BACKEND": "gmail_api",
                    "PODCAST_EMAIL_FROM": "AIConvoCast@gmail.com",
                    "PODCAST_EMAIL_TO": "ianeoconnell@gmail.com",
                },
                clear=True,
            ):
                send_podcast_email(
                    audio_path,
                    "Title: Test\nDescription: OAuth delivery.",
                    workflow_id=43,
                )

        send_call = gmail_service.users.return_value.messages.return_value.send
        send_call.assert_called_once()
        send_call.return_value.execute.assert_called_once()
        self.assertEqual(send_call.call_args.kwargs["userId"], "me")
        self.assertIn("raw", send_call.call_args.kwargs["body"])

    def test_rejects_unknown_email_backend(self):
        with patch.dict(
            os.environ,
            {"PODCAST_EMAIL_BACKEND": "unknown"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "gmail_api.*smtp"):
                send_podcast_email(
                    "missing.mp3",
                    "Title: Test\nDescription: Test.",
                    workflow_id=43,
                )

    @patch("podcast_email.Credentials.from_authorized_user_info")
    def test_loads_base64_github_oauth_secret(self, from_authorized_user_info):
        credentials = MagicMock()
        credentials.refresh_token = "refresh-token"
        credentials.valid = True
        from_authorized_user_info.return_value = credentials
        token_info = {
            "client_id": "client-id",
            "client_secret": "client-secret",
            "refresh_token": "refresh-token",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        encoded_token = base64.b64encode(
            json.dumps(token_info).encode("utf-8")
        ).decode("ascii")

        with patch.dict(
            os.environ,
            {"GMAIL_OAUTH_TOKEN_B64": encoded_token},
            clear=True,
        ):
            loaded = _load_gmail_oauth_credentials()

        self.assertIs(loaded, credentials)
        from_authorized_user_info.assert_called_once_with(
            token_info,
            scopes=[GMAIL_SEND_SCOPE],
        )


if __name__ == "__main__":
    unittest.main()
