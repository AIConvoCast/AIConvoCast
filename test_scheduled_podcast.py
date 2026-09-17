"""Regression checks for the 4 p.m. Eastern automatic podcast and backups."""

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
    def evaluate(self, runs, scheduled_at="2026-09-13T20:30:00Z", now=None,
                 jobs=None, allow_early=False, event_name="schedule", scheduled_run=False):
        def response(path, params=None):
            if path.endswith("/actions/runs/456"):
                return {"workflow_id": 10, "created_at": scheduled_at}
            if path.endswith("/jobs"):
                return {"jobs": jobs or []}
            return {"workflow_runs": runs}
        api = Mock(side_effect=response)
        result = schedule.evaluate_run(
            event_name, "example/podcast", 456, api_get=api,
            now=now or schedule.parse_timestamp(scheduled_at),
            allow_early=allow_early,
            scheduled_run=scheduled_run,
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
        self.assertNotIn("event", params)
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

    def test_daylight_saving_transition_days_use_correct_midnight(self):
        for scheduled_at, now, expected in [
            ("2026-03-08T20:30:00Z", "2026-03-08T20:30:00Z", "2026-03-08T05:00:00+00:00..2026-03-08T20:30:00+00:00"),
            ("2026-11-01T21:30:00Z", "2026-11-01T21:30:00Z", "2026-11-01T04:00:00+00:00..2026-11-01T21:30:00+00:00"),
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

    def test_scheduled_generation_never_starts_before_four_in_either_season(self):
        for early, due in [
            ("2026-07-15T19:59:59Z", "2026-07-15T20:00:00Z"),
            ("2026-01-15T20:59:59Z", "2026-01-15T21:00:00Z"),
        ]:
            with self.subTest(early=early):
                self.assertFalse(self.evaluate([], early)[0][0])
                self.assertTrue(self.evaluate([], due)[0][0])

    def test_warmup_allowed_from_noon_only(self):
        self.assertFalse(self.evaluate([], "2026-09-13T15:59:59Z", allow_early=True)[0][0])
        self.assertTrue(self.evaluate([], "2026-09-13T16:00:00Z", allow_early=True)[0][0])
        self.assertFalse(self.evaluate([], "2026-09-13T16:00:00Z")[0][0])

    def test_only_sunday_through_thursday_are_automatic(self):
        for day in range(13, 20):  # Sunday through Saturday, September 2026.
            with self.subTest(day=day):
                self.assertEqual(self.evaluate([], f"2026-09-{day}T20:00:00Z")[0][0], day < 18)

    def test_stale_run_from_previous_eastern_day_is_skipped(self):
        (allowed, _), _ = self.evaluate([], "2026-09-13T20:00:00Z",
                                        now=schedule.parse_timestamp("2026-09-14T20:00:00Z"))
        self.assertFalse(allowed)

    def test_manual_run_bypasses_weekend_and_time_gates(self):
        api = Mock(side_effect=AssertionError("No API needed for a manual run"))
        self.assertTrue(schedule.evaluate_run("workflow_dispatch", "example/podcast", 456,
                                             api_get=api, now=schedule.parse_timestamp("2026-09-19T13:00:00Z"))[0])

    def test_backup_skips_after_automatic_generation_even_if_it_failed(self):
        for state, conclusion in [("in_progress", None), ("completed", "success"),
                                  ("completed", "failure"), ("completed", "cancelled")]:
            with self.subTest(state=state, conclusion=conclusion):
                prior = manual_run("2026-09-13T20:00:00Z", event="schedule")
                jobs = [{"steps": [{"name": schedule.GENERATION_STEP, "status": state,
                                     "conclusion": conclusion}]}]
                (allowed, explanation), _ = self.evaluate([prior], jobs=jobs)
                self.assertFalse(allowed)
                self.assertIn("already started generation", explanation)

    def test_backup_can_run_after_skipped_guard_or_failed_preflight(self):
        for steps in [[], [{"name": schedule.GENERATION_STEP, "status": "completed", "conclusion": "skipped"}],
                      [{"name": "Verify email authorization before paid generation", "status": "completed", "conclusion": "failure"}],
                      [{"name": schedule.GENERATION_STEP, "status": "queued", "conclusion": None}]]:
            with self.subTest(steps=steps):
                prior = manual_run("2026-09-13T20:00:00Z", event="schedule")
                self.assertTrue(self.evaluate([prior], jobs=[{"steps": steps}])[0][0])

    def test_current_run_is_excluded_from_duplicate_check(self):
        current = manual_run("2026-09-13T20:00:00Z", id=456, event="schedule")
        (allowed, _), api = self.evaluate([current])
        self.assertTrue(allowed)
        self.assertFalse(any(call.args[0].endswith("/jobs") for call in api.call_args_list))

    def test_generation_from_earlier_attempt_or_job_page_counts(self):
        api = Mock(side_effect=[{"jobs": [{"steps": []}] * 100}, {"jobs": [{"steps": [
            {"name": schedule.GENERATION_STEP, "status": "completed", "conclusion": "success"}
        ]}]}])
        self.assertTrue(schedule.generation_started("example/podcast", {"id": 123}, api))
        self.assertEqual(api.call_args.args[1], {"filter": "all", "per_page": 100, "page": 2})

    def test_wait_uses_four_pm_eastern_across_daylight_saving(self):
        for start, end in [("2026-03-08T19:59:00Z", "2026-03-08T20:00:00Z"),
                           ("2026-11-01T20:59:00Z", "2026-11-01T21:00:00Z")]:
            with self.subTest(start=start), contextlib.redirect_stdout(io.StringIO()):
                now = Mock(side_effect=[schedule.parse_timestamp(start), schedule.parse_timestamp(end)])
                sleeper = Mock()
                schedule.wait_until_target(now_fn=now, sleep_fn=sleeper)
                sleeper.assert_called_once_with(60)

    def test_wait_does_not_delay_late_runner(self):
        sleeper = Mock()
        with contextlib.redirect_stdout(io.StringIO()):
            schedule.wait_until_target(now_fn=lambda: schedule.parse_timestamp("2026-09-13T20:17:00Z"),
                                       sleep_fn=sleeper)
        sleeper.assert_not_called()

    def test_wait_fails_closed_if_runner_resumes_next_day(self):
        now = Mock(side_effect=[schedule.parse_timestamp("2026-09-13T19:59:00Z"),
                                schedule.parse_timestamp("2026-09-14T20:00:00Z")])
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            schedule.wait_until_target(now_fn=now, sleep_fn=Mock())

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

    def test_manual_trigger_during_wait_prevents_output_permission(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            environment = {"GITHUB_EVENT_NAME": "schedule", "GITHUB_REPOSITORY": "example/podcast",
                           "GITHUB_RUN_ID": "456", "GITHUB_OUTPUT": str(output), "GITHUB_STEP_SUMMARY": ""}
            with patch.dict(os.environ, environment), patch.object(schedule, "evaluate_run", side_effect=[
                (True, "Ready to wait."), (False, "Manual run triggered during wait.")
            ]) as evaluate, patch.object(schedule, "wait_until_target") as wait, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(schedule.main(wait=True), 0)
            wait.assert_called_once()
            self.assertTrue(evaluate.call_args_list[0].kwargs["allow_early"])
            self.assertNotIn("allow_early", evaluate.call_args_list[1].kwargs)
            self.assertEqual(output.read_text(), "should_run=false\n")

    def test_manual_dispatch_never_waits(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REPOSITORY": "example/podcast",
                           "GITHUB_RUN_ID": "456", "GITHUB_OUTPUT": str(Path(directory) / "output"),
                           "GITHUB_STEP_SUMMARY": ""}
            with patch.dict(os.environ, environment), patch.object(schedule, "wait_until_target") as wait, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(schedule.main(wait=True), 0)
            wait.assert_not_called()

    def test_google_dispatch_obeys_time_day_and_manual_history(self):
        for created, history, expected in [
            ("2026-09-13T19:59:59Z", [], False),
            ("2026-09-13T20:00:00Z", [], True),
            ("2026-09-18T20:00:00Z", [], False),
            ("2026-09-13T20:00:00Z", [manual_run("2026-09-13T19:00:00Z")], False),
        ]:
            with self.subTest(created=created, history=history):
                result, _ = self.evaluate(history, created, event_name="workflow_dispatch", scheduled_run=True)
                self.assertEqual(result[0], expected)

    def test_google_dispatch_is_automatic_not_a_manual_suppressor(self):
        google_run = manual_run("2026-09-13T20:00:00Z", display_title=schedule.AUTOMATIC_RUN_TITLE)
        # An accepted HTTP dispatch that failed before generation allows the backup.
        self.assertTrue(self.evaluate([google_run], jobs=[{"steps": []}])[0][0])
        jobs = [{"steps": [{"name": schedule.GENERATION_STEP, "status": "completed", "conclusion": "success"}]}]
        result, _ = self.evaluate([google_run], jobs=jobs)
        self.assertFalse(result[0])
        self.assertIn("automatic run", result[1])

    def test_validation_dispatch_never_suppresses_real_episode(self):
        validation = manual_run("2026-09-13T20:00:00Z", display_title=schedule.VALIDATION_RUN_TITLE)
        result, api = self.evaluate([validation])
        self.assertTrue(result[0])
        self.assertFalse(any(call.args[0].endswith("/jobs") for call in api.call_args_list))

    def test_cli_passes_automatic_dispatch_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REPOSITORY": "example/podcast",
                           "GITHUB_RUN_ID": "456", "GITHUB_OUTPUT": str(Path(directory) / "output"),
                           "GITHUB_STEP_SUMMARY": "", "PODCAST_SCHEDULED_RUN": "true"}
            with patch.dict(os.environ, environment), patch.object(schedule, "evaluate_run", return_value=(False, "Not due")) as evaluate, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(schedule.main(), 0)
            self.assertTrue(evaluate.call_args.kwargs["scheduled_run"])


if __name__ == "__main__":
    unittest.main()
