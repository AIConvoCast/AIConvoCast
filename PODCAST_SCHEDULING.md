# Podcast scheduling

The target is **4:00 p.m. Eastern local time, Sunday through Thursday**,
including daylight-saving changes. Google Cloud Scheduler supplies the clock;
GitHub Actions still runs the existing podcast pipeline.

## Timer and backups

One job, `aiconvocast-4pm-eastern`, in Google project `jmio-434920`, region
`us-east1`, dispatches the workflow at 4:00 p.m. and again at 4:10 p.m. Eastern.
The second dispatch is a backup; it skips if the first started generation.
HTTP failures have bounded retries. GitHub also retains one native cron fallback
at 21:17 UTC (after 4 p.m. in both EST and EDT), subject to GitHub's dispatch delays.

The Google job uses `0,10 16 * * 0-4` with `America/New_York`. The non-secret
configuration is in `cloud_scheduler_job.json`. Its authorization header and
base64 request body are supplied by `configure_cloud_scheduler.py`; never save
a real token in the repository.

[Google includes three scheduler jobs per billing account for free](https://cloud.google.com/scheduler/pricing).
Repeated executions of this one job do not consume additional job slots. The
allowance is shared across projects, and paused jobs count. Before adding the
job, verify the account has a free slot. This setup uses no Cloud Run, Cloud
Functions, or other hosted compute in Google. Existing podcast API costs remain.

## Manual runs and duplicate prevention

Use **Run workflow** as before, leaving `scheduled_run` and `dry_run` unchecked.
Manual requests remain immediate on any day. Google sets `scheduled_run=true`;
automatic runs share a concurrency group and the fixed Actions run title
`Scheduled AI Podcast Pipeline`. The title identifies automatic dispatches in
GitHub history, whose API does not expose workflow inputs. Keep it synchronized
with `AUTOMATIC_RUN_TITLE` in `check_scheduled_podcast.py`.

- Automatic generation is allowed only at/after 4 p.m. Eastern on Sun–Thu.
- Any same-day manual trigger of this workflow suppresses automatic generation,
  including failed/cancelled manual requests. A final check happens immediately
  before generation, after dependency and email preflight checks.
- Once automatic generation starts, all backups skip, even if generation fails.
  A failed preflight or skipped generation still allows a backup. Recovery after
  a partial generation remains manual to avoid duplicate costs or publication.
- `dry_run=true` exercises the guard but skips the entire generation job. These
  runs are titled `Validate Podcast Scheduler` and do not suppress a real episode.
- API errors stop automatic generation. A trigger from a different Eastern date
  skips. Manual requests bypass all scheduling restrictions.

## Provisioning and credential renewal

Use a fine-grained GitHub token limited to **AIConvoCast/AIConvoCast**, with
**Actions: read and write** (and GitHub's required metadata read access). Give it
an explicit expiration date and renew it before expiration. Google stores the
token as the scheduler job's Authorization header; users with permission to read
that job can read its configuration. The helper never prints the job response or
token. Use the hidden prompt, or a private token file outside the repository.

The existing Google service account needs scheduler job create/get/update/run
permissions. The Cloud Scheduler API and billing must already be enabled.

1. Confirm a free scheduler slot on the billing account and prepare the token.
2. Run `python configure_cloud_scheduler.py --ref main --run-now` to create/update
   this same job in validation mode and test a dispatch through Google. A feature
   branch may be used with `--ref` before merging.
3. Verify Google's HTTP result and the matching GitHub validation run: the guard
   should complete and the podcast generation job must be skipped.
4. After the tested changes are on `main`, run
   `python configure_cloud_scheduler.py --activate` to select real generation.
5. Verify the job is enabled and its next run is 4:00 p.m. Eastern on Sun–Thu.

The helper defaults to validation and refuses an immediate production dispatch.
For token renewal, update this same job rather than creating another job.

Cloud Scheduler removes GitHub's cron-dispatch delay from the primary trigger.
GitHub runner allocation and dependency setup can still add time after 4 p.m.

Validate with `python -m unittest test_scheduled_podcast test_cloud_scheduler -v`.
