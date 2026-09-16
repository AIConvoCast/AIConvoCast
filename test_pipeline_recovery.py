"""Offline outage tests: no paid API calls and no real email delivery."""

import ast
import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from google.auth.exceptions import RefreshError, TransportError
from googleapiclient.errors import HttpError

import podcast_email
from local_artifacts import LocalArtifacts, ReusableAudioCache
from service_retry import elevenlabs_audio_with_retry, retry_transient


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.audio = self.directory / "episode.mp3"
        self.audio.write_bytes(b"complete audio")
        self.env = patch.dict(os.environ, {
            "PODCAST_EMAIL_BACKEND": "gmail_api",
            "PODCAST_SMTP_USERNAME": "sender@example.com",
            "PODCAST_SMTP_PASSWORD": "test-password",
        }, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.sleep = patch("service_retry.time.sleep").start()
        self.addCleanup(patch.stopall)

    def send(self):
        return podcast_email.send_podcast_email(
            self.audio, "Title: Outage test\nDescription: Complete script.", workflow_id=47)

    def status(self):
        path = next((self.directory / "email_outbox").glob("*.json"))
        return json.loads(path.read_text())

    @patch("podcast_email._send_with_smtp")
    @patch("podcast_email._load_gmail_oauth_credentials", side_effect=RuntimeError("invalid_grant"))
    def test_expired_gmail_uses_smtp_and_preserves_email(self, credentials, smtp):
        self.send()
        smtp.assert_called_once()
        self.assertEqual(self.status()["status"], "sent")
        saved = next((self.directory / "email_outbox").glob("*.eml"))
        self.assertIn(b"episode.mp3", saved.read_bytes())
        with self.assertRaisesRegex(RuntimeError, "already sent"):
            podcast_email.resend_saved_email(saved)

    @patch("podcast_email._send_with_smtp")
    @patch("podcast_email._load_gmail_oauth_credentials")
    @patch("podcast_email.build")
    def test_timeout_after_send_does_not_duplicate_via_smtp(self, build, credentials, smtp):
        execute = build.return_value.users.return_value.messages.return_value.send.return_value.execute
        execute.side_effect = TimeoutError("ambiguous")
        with self.assertRaises(podcast_email.DeliveryUncertain):
            self.send()
        smtp.assert_not_called()
        execute.assert_called_once()
        self.assertEqual(self.status()["status"], "uncertain")
        saved = next((self.directory / "email_outbox").glob("*.eml"))
        with self.assertRaisesRegex(RuntimeError, "Check Sent"):
            podcast_email.resend_saved_email(saved)

    @patch("podcast_email._load_gmail_oauth_credentials")
    @patch("podcast_email.build")
    def test_explicit_rate_limit_retries_same_message(self, build, credentials):
        send = build.return_value.users.return_value.messages.return_value.send
        send.return_value.execute.side_effect = [HttpError(SimpleNamespace(status=429, reason="rate limit"), b'{}'), {}]
        self.send()
        self.assertEqual(send.call_count, 2)
        self.assertEqual(send.call_args_list[0], send.call_args_list[1])
        self.assertEqual(self.status()["status"], "sent")

    @patch("podcast_email.Credentials.from_authorized_user_info")
    def test_refresh_retries_transient_but_not_revoked_grant(self, factory):
        os.environ["GMAIL_OAUTH_TOKEN_JSON"] = "{}"
        credentials = factory.return_value
        credentials.valid = False
        credentials.refresh.side_effect = [TransportError("connection reset"), None]
        podcast_email._load_gmail_oauth_credentials()
        self.assertEqual(credentials.refresh.call_count, 2)
        credentials.refresh.reset_mock(side_effect=True)
        credentials.refresh.side_effect = RefreshError("invalid_grant: revoked")
        with self.assertRaisesRegex(RuntimeError, "Reauthorize"):
            podcast_email._load_gmail_oauth_credentials()
        credentials.refresh.assert_called_once()

    def test_retry_limit_and_real_quota(self):
        operation = Mock(side_effect=TimeoutError())
        with self.assertRaises(TimeoutError):
            retry_transient(operation)
        self.assertEqual(operation.call_count, 3)
        operation = Mock(side_effect=ValueError("quota_exceeded"))
        with self.assertRaises(ValueError):
            retry_transient(operation)
        operation.assert_called_once()

    def test_stream_retry_discards_partial_chunk(self):
        def broken_stream():
            yield b"partial"
            raise httpx.ReadError("disconnected")
        client = Mock()
        client.text_to_speech.convert.side_effect = [broken_stream(), iter([b"complete"])]
        result = b"".join(elevenlabs_audio_with_retry(client, text="NVIDIA", voice_id="voice"))
        self.assertEqual(result, b"complete")
        self.assertEqual(client.text_to_speech.convert.call_count, 2)

    def test_cloud_auth_failure_keeps_current_run_audio_for_merge(self):
        source = Path("ai_podcast_pipeline_for_cursor.py")
        names = {"upload_file_to_gcs", "download_file_from_gcs", "get_latest_file_in_gcs_folder"}
        tree = ast.parse(source.read_text(encoding="utf-8"))
        store = LocalArtifacts(self.directory / "runs")
        client = Mock(side_effect=RefreshError("invalid_grant"))
        namespace = dict(LOCAL_ARTIFACTS=store, register_uploaded_audio_master=Mock(),
                         get_gcs_client=client, GCS_RETRY=None, GCS_BUCKET_NAME="test")
        exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[]), str(source), "exec"), namespace)
        saved = namespace["upload_file_to_gcs"](self.audio, "narration/current.mp3")
        self.audio.unlink()
        self.assertTrue(Path(saved).is_file())
        self.assertEqual(namespace["get_latest_file_in_gcs_folder"]("narration/"), "narration/current.mp3")
        restored = namespace["download_file_from_gcs"]("narration/current.mp3", self.audio)
        self.assertEqual(restored.read_bytes(), b"complete audio")
        self.assertEqual(client.call_count, 1)
        self.assertIsNone(LocalArtifacts(self.directory / "runs").latest("narration/"))

    def test_failed_sheet_logging_does_not_block_or_repeat(self):
        store = LocalArtifacts(self.directory)
        log = Mock(side_effect=RefreshError("invalid_grant"))
        self.assertFalse(store.log_to_sheet(log))
        self.assertFalse(store.log_to_sheet(log))
        log.assert_called_once()
        path = store.write_json("workflow_steps.json", [["generated", "episode.mp3"]])
        self.assertEqual(json.loads(path.read_text())[0][0], "generated")

    def test_reusable_audio_cache_survives_run_without_reusing_other_assets(self):
        cache = ReusableAudioCache(self.directory / "asset_cache")
        cache.save("assets/Intro.mp3", self.audio)
        self.audio.unlink()
        recovered = ReusableAudioCache(cache.directory).restore("assets/Intro.mp3", self.audio)
        self.assertEqual(recovered.read_bytes(), b"complete audio")
        self.assertIsNone(cache.restore("assets/Other.mp3", self.directory / "missing.mp3"))

    def test_rate_limits_do_not_trigger_credit_fallback(self):
        source = Path("ai_podcast_pipeline_for_cursor.py")
        tree = ast.parse(source.read_text(encoding="utf-8"))
        namespace = {}
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "is_elevenlabs_credit_quota_error")
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
        classify = namespace[node.name]
        self.assertFalse(classify("Rate limit exceeded; retry later", 429))
        self.assertFalse(classify("too_many_concurrent_requests", 429))
        self.assertTrue(classify("quota_exceeded: 481 credits available", 401))
        self.assertTrue(classify("", 402))

    @patch("podcast_email.sys.stdin.isatty", return_value=True)
    @patch("configure_gmail_oauth.authorize_local_gmail")
    @patch("podcast_email._send_with_gmail_api")
    def test_interactive_local_run_can_renew_expired_grant(self, gmail, authorize, tty):
        os.environ.pop("PODCAST_SMTP_PASSWORD")
        expired = podcast_email.DeliveryNotAttempted("cannot authorize")
        expired.__cause__ = RefreshError("invalid_grant")
        gmail.side_effect = [expired, None]
        self.send()
        authorize.assert_called_once()
        self.assertEqual(gmail.call_count, 2)
        self.assertEqual(gmail.call_args.kwargs["credentials"], authorize.return_value)
        self.assertEqual(self.status()["status"], "sent")

    @patch("podcast_email.sys.stdin.isatty", return_value=True)
    def test_github_never_opens_local_auth_or_changes_credentials(self, tty):
        os.environ["GITHUB_ACTIONS"] = "true"
        self.assertFalse(podcast_email._can_renew_local_grant(RefreshError("invalid_grant")))
        os.environ.pop("GITHUB_ACTIONS")
        os.environ["GMAIL_OAUTH_TOKEN_B64"] = "explicit-secret"
        self.assertFalse(podcast_email._can_renew_local_grant(RefreshError("invalid_grant")))


if __name__ == "__main__":
    unittest.main()
