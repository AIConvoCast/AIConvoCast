# Podcast scheduling

The daily automatic episode runs from **Run AI Podcast V2**
(`.github/workflows/ai_podcast_pipeline_v2.yml`), which builds the episode from
`podcast_v2/` with no Google Sheet. The original **Run AI Podcast Pipeline**
(V1) is now manual only.

The target is **4:00 p.m. Eastern local time, Sunday through Thursday**,
including daylight-saving changes. Manual **Run workflow** requests remain
immediate and can be used on any day.

GitHub's cron dispatcher has delivered this repository's scheduled events
hours late. A single earlier cron time did not produce consistent timing.
The workflow now gives GitHub multiple chances to allocate a runner before
4 p.m., then uses that runner's clock to wait for the target time.

## How it works

- `17 15-22 * * 0-4` creates eight hourly wake-up opportunities in UTC, away
  from the busy start of the hour. These are attempts to prepare a runner,
  not eight podcast episodes. UTC avoids having to change the cron twice a year.
- `check_scheduled_podcast.py --wait-until-target` uses `America/New_York`.
  Before noon, or on Friday/Saturday, it skips. Between noon and 4 p.m., it
  waits. At or after 4 p.m., it releases the pipeline if the day's checks pass.
  The pipeline's normal runner/dependency setup then takes place.
- Automatic runs share a concurrency group. A later wake-up cannot cancel
  the active runner or start a second automatic pipeline concurrently.
  GitHub can replace pending backups; cancelled pending runs are expected.
- Any same-day manual trigger of the V2 workflow, including a custom-topic
  episode, suppresses automation,
  including failed or cancelled manual runs. History is checked before and
  after waiting, and again immediately before generation. A manual V1 run
  does not count, so running V1 by hand on a scheduled day adds a second episode.
- Once an automatic run has started the `Run AI Podcast V2` generation
  step, backups skip, even if that generation later fails. This avoids paying
  for or publishing a second episode. Recovery after that point is manual.
  A failed preflight or skipped generation does not consume the day's run.
- API errors prevent automatic generation. A later wake-up can retry the
  checks. A trigger whose runner resumes on a different Eastern date skips.

The wait job has a 250-minute timeout, covering the maximum four-hour wait
plus setup and API calls. Podcast generation keeps its separate 30-minute
timeout. The waiting job occupies one hosted runner; manual runs do not wait
behind it. No new service, credential, or manual setup is needed.

This improves the chance of a start near 4 p.m. but remains best effort:
GitHub can delay or drop every wake-up, and runner startup/setup can add time.
See [GitHub's scheduling limitations](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

Validate scheduling changes with `python -m unittest test_scheduled_podcast -v`.
