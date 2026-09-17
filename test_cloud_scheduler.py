"""Check the dispatch contract and secret handling without cloud mutations."""

import base64
import contextlib
import io
import json
import unittest
from unittest.mock import Mock

import configure_cloud_scheduler as scheduler


class CloudSchedulerTests(unittest.TestCase):
    def test_default_is_a_single_free_tier_job_with_no_generation(self):
        job = scheduler.build_job("github_pat_test_only", ref="fix/test")
        self.assertEqual(job["schedule"], "0,10 16 * * 0-4")
        self.assertEqual(job["timeZone"], "America/New_York")
        body = json.loads(base64.b64decode(job["httpTarget"]["body"]))
        self.assertEqual(body, {"ref": "fix/test", "inputs": {"scheduled_run": True, "dry_run": True}})

    def test_production_requires_main_and_marks_dispatch_automatic(self):
        with self.assertRaises(ValueError):
            scheduler.build_job("github_pat_test_only", ref="fix/test", activate=True)
        body = json.loads(base64.b64decode(scheduler.build_job("github_pat_test_only", activate=True)["httpTarget"]["body"]))
        self.assertEqual(body, {"ref": "main", "inputs": {"scheduled_run": True, "dry_run": False}})

    def test_rejects_a_broad_classic_or_oauth_token(self):
        for token in ["", "ghp_test_only", "gho_test_only"]:
            with self.subTest(token=token), self.assertRaises(ValueError):
                scheduler.build_job(token)

    def test_creating_and_testing_job_never_prints_token(self):
        session = Mock()
        session.get.return_value.status_code = 404
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            scheduler.configure(session, scheduler.build_job("github_pat_test_only"), run_now=True)
        self.assertEqual(session.post.call_count, 2)
        self.assertTrue(session.post.call_args.args[0].endswith(":run"))
        self.assertNotIn("github_pat_test_only", output.getvalue())

    def test_update_reuses_same_job_and_rejects_unrelated_target(self):
        session = Mock()
        session.get.return_value.status_code = 200
        session.get.return_value.json.return_value = {"httpTarget": {"uri": scheduler.TARGET}}
        with contextlib.redirect_stdout(io.StringIO()):
            scheduler.configure(session, scheduler.build_job("github_pat_test_only", activate=True))
        session.patch.assert_called_once()
        session.post.assert_not_called()
        session.get.return_value.json.return_value = {"httpTarget": {"uri": "https://example.com/unrelated"}}
        with self.assertRaises(ValueError):
            scheduler.configure(session, scheduler.build_job("github_pat_test_only"))


if __name__ == "__main__":
    unittest.main()
