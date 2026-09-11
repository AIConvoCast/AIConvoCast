"""Regression checks for manual-trigger suppression of scheduled podcasts."""

import contextlib
from datetime import datetime, timezone
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import check_scheduled_podcast as schedule


def manual_run(created_at, **changes):
    return {
        "id": 123, "workflow_id": 10, "event": "workflow_dispatch",
        "created_at": created_at, "status": "completed", "conclusion": "success",
        "html_url": "https://github.com/example/podcast/actions/runs/123",
        **changes,
    }


class ScheduledPodcastTests(unittest.TestCase):
    def evaluate(self, runs, scheduled_at="2026-09-13T20:30:00Z", now=None):
        api = Mock(side_effect=[
            {"workflow_id": 10, "created_at": scheduled_at},
            {"workflow_runs": runs},
        ])
        result = schedule.evaluate_run(
            "schedule", "example/podcast", 456, api_get=api,
            now=now or schedule.parse_timestamp(scheduled_at),
        )
        return result, api

    def test_manual_dispatch_always_runs_without_history_request(self):
        api = Mock(side_effect=AssertionError("Manual runs must bypass the API"))
        allowed, _ = schedule.evaluate_run("workflow_dispatch", "example/podcast", 456, api_get=api)
        self.assertTrue(allowed)
        api.assert_not_called()

    def test_no_manual_run_allows_schedule(self):
        (allowed, _), api = self.evaluate([])
        self.assertTrue(allowed)
        path, params = api.call_args.args
        self.assertEqual(path, "/repos/example/podcast/actions/workflows/10/runs")
        self.assertEqual(params["event"], "workflow_dispatch")
        self.assertNotIn("status", params)
        self.assertNotIn("branch", params)

    def test_any_manual_trigger_counts_regardless_of_outcome(self):
        for state, conclusion in [
            ("queued", None), ("in_progress", None), ("completed", "success"),
            ("completed", "failure"), ("completed", "cancelled"),
        ]:
            with self.subTest(state=state, conclusion=conclusion):
                (allowed, explanation), _ = self.evaluate([
                    manual_run("2026-09-13T15:00:00Z", status=state, conclusion=conclusion)
                ])
                self.assertFalse(allowed)
                self.assertIn("manual run 123", explanation)

    def test_midnight_boundaries_use_eastern_not_utc(self):
        for scheduled_at, previous_day, same_day in [
            ("2026-01-15T21:30:00Z", "2026-01-15T04:59:59Z", "2026-01-15T05:00:00Z"),
            ("2026-07-15T20:30:00Z", "2026-07-15T03:59:59Z", "2026-07-15T04:00:00Z"),
        ]:
            with self.subTest(scheduled_at=scheduled_at):
                self.assertTrue(self.evaluate([manual_run(previous_day)], scheduled_at)[0][0])
                self.assertFalse(self.evaluate([manual_run(same_day)], scheduled_at)[0][0])

    def test_daylight_saving_transition_days_and_delayed_runner(self):
        for scheduled_at, now, expected in [
            ("2026-03-08T20:30:00Z", "2026-03-09T08:00:00Z", "2026-03-08T05:00:00+00:00..2026-03-09T03:59:59+00:00"),
            ("2026-11-01T21:30:00Z", "2026-11-02T09:00:00Z", "2026-11-01T04:00:00+00:00..2026-11-02T04:59:59+00:00"),
        ]:
            with self.subTest(scheduled_at=scheduled_at):
                (_, _), api = self.evaluate([], scheduled_at, schedule.parse_timestamp(now))
                self.assertEqual(api.call_args.args[1]["created"], expected)

    def test_unrelated_workflow_nonmanual_or_future_run_does_not_skip(self):
        (allowed, _), _ = self.evaluate([
            manual_run("2026-09-13T15:00:00Z", workflow_id=99),
            manual_run("2026-09-13T15:00:00Z", event="schedule"),
            manual_run("2026-09-13T21:00:00Z"),
        ])
        self.assertTrue(allowed)

    def test_manual_run_during_scheduled_queue_delay_counts(self):
        result, _ = self.evaluate(
            [manual_run("2026-09-13T20:35:00Z")],
            now=datetime(2026, 9, 13, 20, 40, tzinfo=timezone.utc),
        )
        self.assertFalse(result[0])

    def test_all_history_pages_are_checked(self):
        api = Mock(side_effect=[
            {"workflow_id": 10, "created_at": "2026-09-13T20:30:00Z"},
            {"workflow_runs": [manual_run("2026-09-12T15:00:00Z")] * 100},
            {"workflow_runs": [manual_run("2026-09-13T15:00:00Z")]},
        ])
        allowed, _ = schedule.evaluate_run(
            "schedule", "example/podcast", 456, api_get=api,
            now=schedule.parse_timestamp("2026-09-13T20:30:00Z"),
        )
        self.assertFalse(allowed)
        self.assertEqual(api.call_args.args[1]["page"], 2)

    def test_api_failure_never_outputs_permission_to_run(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            environment = {
                "GITHUB_EVENT_NAME": "schedule", "GITHUB_REPOSITORY": "example/podcast",
                "GITHUB_RUN_ID": "456", "GITHUB_OUTPUT": str(output),
            }
            with patch.dict(os.environ, environment), patch.object(
                schedule, "evaluate_run", side_effect=RuntimeError("API unavailable")
            ), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(schedule.main(), 1)
            self.assertFalse(output.exists())

    def test_skip_output_and_summary_are_written_for_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            summary = Path(directory) / "summary"
            environment = {
                "GITHUB_EVENT_NAME": "schedule", "GITHUB_REPOSITORY": "example/podcast",
                "GITHUB_RUN_ID": "456", "GITHUB_OUTPUT": str(output),
                "GITHUB_STEP_SUMMARY": str(summary),
            }
            with patch.dict(os.environ, environment), patch.object(
                schedule, "evaluate_run", return_value=(False, "Manual run found today.")
            ), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(schedule.main(), 0)
            self.assertEqual(output.read_text(), "should_run=false\n")
            self.assertIn("Manual run found today.", summary.read_text())


if __name__ == "__main__":
    unittest.main()
