# AI Podcast V2 (no Google Sheet)

V2 runs the daily episode from files in this folder. The original
`Run AI Podcast Pipeline` action and its Google Sheet are unchanged and still
own the schedule; V2 is manual-only for now.

| File | What it holds |
| --- | --- |
| `workflow.json` | The steps, in order. Based on sheet Workflow 47. |
| `prompts/P*.txt` | Prompt text, one file per prompt ID. |
| `models.json` | Known models by name, with web-search support and availability. |
| `run_podcast.py` | The runner (`--check` validates only, `--no-email` skips the email). |
| `update_models.py` | Refreshes `models.json` from the OpenAI, Anthropic and Google APIs. |

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

Parts: `prompt:<id>`, `step:<step id>`, `script_tuning` (the Claude script
appendix V1 adds to P4/P12), `gcs_file:<path>`, `gcs_latest_text:<folder>`,
`gcs_latest_mp3:<folder>`. `title_from` names the step whose `Title:` line
names the saved files.

## Seeded from the repo, not the live sheet

The prompts were copied from the pipeline's built-in sheet template. The live
sheet may have been edited since, so compare before relying on V2:

- `P4`, `P8`, `P10` come from the template's prompts with the same IDs.
- `P12` is not in the template; it is seeded from template prompt 5, which
  starts with the same text as the live P12.
- ElevenLabs settings use the pipeline defaults (Liam, `eleven_v3`,
  stability 0.5, similarity 0.7, style 0, speed 1.06).
