# Repo guide for AI agents (Claude Code, ChatGPT/Codex, etc.)

This file orients any coding agent working on this repo from a fresh session (e.g. triggered from a phone) with no prior conversation context.

## What this repo is

- **AIConvoCast.com** — a daily AI-news podcast. Two halves live in one repo:
  1. A static marketing/episodes site (`index.html`, `episodes.html`, `contact.html`, `privacy.html`, `main.js`, `contact.js`, `styles.css`) deployed to GitHub Pages at the custom domain in `CNAME`.
  2. A Python pipeline that generates each podcast episode (script → audio via ElevenLabs/Google TTS → upload → email) and updates the site's episode list.
- `_config.yml` and `index.md` are unused leftovers from the original GitHub Pages template — the real site is built by `build_site.py`, not Jekyll.

## Site deploy flow

- `.github/workflows/static.yml` runs `python -m unittest test_site -v`, then `python build_site.py --output public`, then publishes `public/` to GitHub Pages. It runs on push to `main` (for site-relevant paths) and on a schedule.
- `.github/workflows/site-checks.yml` runs the same test suite plus `check_site.py` (cert/redirect checks) on push, PR, and a daily schedule.
- Before changing site files, run `python -m unittest test_site -v` locally — that's what CI gates on.

## Podcast pipeline

- `.github/workflows/ai_podcast_pipeline_v2.yml` ("Run AI Podcast V2") is the main pipeline: targets Sun–Thu 4pm Eastern, plus manual `workflow_dispatch` (with a `send_email` input, on by default). Early UTC wake-ups wait until 4pm using `America/New_York`; backups skip after a manual V2 trigger or prior automatic generation that day. See `PODCAST_SCHEDULING.md`. It runs `podcast_v2/run_podcast.py` from `podcast_v2/` config files with no Google Sheet access, in the `production` environment. See `podcast_v2/README.md`.
- `update_models_v2.yml` refreshes `podcast_v2/models.json`; `sync_v2_from_sheet.yml` copies prompts and settings from the Google Sheet (read-only) to a `sheet-sync/*` branch for review.
- `.github/workflows/ai_podcast_pipeline.yml` ("Run AI Podcast Pipeline", V1) is now manual only. It runs `ai_podcast_pipeline_for_cursor.py` driven by the Google Sheet (with `custom_topic`, `workflow_id`, `force_run` inputs). V2 reuses that module's helpers, so don't remove it.
- `manual_ai_podcast_pipeline.yml` is a `workflow_dispatch`-only variant — check with the repo owner before assuming both are still needed.
- Required secrets (see `.env.example` for local dev equivalents): `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `ELEVENLABS_API_KEY`, `GOOGLE_CREDS_JSON`, `GMAIL_OAUTH_TOKEN_B64`, `SHARE_SHEET_WITH_EMAIL`.

## Things to never commit

- `jmio-google-api.json`, `client_secret.json`, `token.pickle`, `.env`, `gmail_oauth_token.b64` — all real credentials, already gitignored. Don't touch `.gitignore` to allow these back in.
- Generated output: `generated_mp3/`, `public/`, `.site-qa/`, `*.mp3`.

## Conventions

- Tests are plain `unittest` files at repo root (`test_*.py`), run individually via `python -m unittest <module> -v` — there's no single aggregate test command wired up yet.
- Root also has several one-off historical fix writeups (`*_SUMMARY.md`, `*_FIX*.md`) — these are notes from past debugging sessions, not living docs; don't treat them as current architecture.
- `main` has no branch protection — pushes go live immediately (site redeploys, and workflow changes take effect on the next scheduled run). Be conservative with direct pushes to `main`; prefer a branch + PR for anything you're not fully confident in, especially changes to the podcast pipeline or its schedule.
