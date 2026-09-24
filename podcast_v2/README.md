# AI Podcast V2 (no Google Sheet)

V2 runs the daily episode from files in this folder. The **Run AI Podcast V2**
action runs it automatically at 4 p.m. Eastern, Sunday through Thursday (see
`PODCAST_SCHEDULING.md`), and on demand. The original `Run AI Podcast Pipeline`
action and its Google Sheet are unchanged but are now manual only.

| File | What it holds |
| --- | --- |
| `workflow.json` | The steps, in order. Based on sheet Workflow 47. |
| `prompts/P*.txt` | Prompt text, one file per prompt ID. |
| `prompts/script_tuning.txt` | Claude script requirements (length, quotes, structure) added by the `script_tuning` part. |
| `models.json` | Known models by name, with web-search support and availability. |
| `run_podcast.py` | The runner (`--check` validates only, `--no-email` skips the email). |
| `update_models.py` | Refreshes `models.json` from the OpenAI, Anthropic and Google APIs. |
| `audio_polish.py` | ffmpeg finishing: soxr resampling when joining intro/narration/outro, and -16 LUFS loudness for Google narration. |

Google credentials (`GOOGLE_CREDS_JSON`) are still used for Cloud Storage and
Google text-to-speech, but nothing reads or writes the sheet.

## Changing a model

Edit the `model` (and `web_search`) of the step in `workflow.json`, using the
model's API name, e.g. `"model": "claude-opus-5-5"`. No numeric model IDs are
involved. `python podcast_v2/run_podcast.py --check` confirms the name is in
`models.json` and supports web search if the step asks for it.

## Steps

| Type | Does | V1 code |
| --- | --- | --- |
| `recent_episodes` | Reads the last `count` episodes straight from the RSS feed | `PPU,PPL15` |
| `model` | Joins `parts` with blank lines and calls `model` | `P10&P8&R2M221` etc. |
| `save_text` | Cleans and saves text to a Cloud Storage folder | `R5SL10T5` |
| `voice` | ElevenLabs narration, Google voice fallback on quota errors | `L8E1SL4T5` |
| `merge_audio` | Joins intro, narration and outro | `L1&L9&L2SL3T5` |

Parts: `prompt:<id>`, `step:<step id>`, `script_tuning` (the contents of
`prompts/script_tuning.txt`), `gcs_file:<path>`, `gcs_latest_text:<folder>`,
`gcs_latest_mp3:<folder>`. `title_from` names the step whose `Title:` line
names the saved files.

## Syncing from the Google Sheet

The **Sync V2 From Sheet** action (`sync_from_sheet.py`) reads the sheet
read-only and copies, for the workflow marked Active = Y:

- every prompt its code references into `prompts/` (without the Claude
  script-tuning block V1 appends to P4, which V2 adds itself);
- the ElevenLabs settings it references into the `voice` step of `workflow.json`;
- the workflow row, referenced models and locations into `sheet_snapshot.json`.

Model choices in `workflow.json` are never overwritten. Changes land on a
`sheet-sync/<run id>` branch to review as a pull request.

The prompts in `prompts/` have since been tuned in the repo (P4, P8, P10, P12),
so a sync will propose replacing those edits with the sheet text. Review the
prompt diffs in the sync pull request before merging it.

## Prior-episode check

The first step reads the newest 15 episodes from the RSS feed and passes them,
with P8, to the research step, as V1 did through the Posted Podcasts tab. If
the feed can't be read or lists no episodes, the run stops before any paid calls.
