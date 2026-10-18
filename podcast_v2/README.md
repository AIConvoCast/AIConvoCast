# AI Podcast V2 (no Google Sheet)

V2 runs the daily episode from files in this folder. The **Run AI Podcast V2**
action runs it automatically at 4 p.m. Eastern, Sunday through Thursday (see
`PODCAST_SCHEDULING.md`), and on demand. The original `Run AI Podcast Pipeline`
action and its Google Sheet are unchanged but are now manual only.

| File | What it holds |
| --- | --- |
| `workflow.json` | The steps, in order. Based on sheet Workflow 47. |
| `topic_workflow.json` | The single-topic episode used when a custom topic is given. |
| `prompts/P20.txt`, `P21.txt`, `topic_*_system.txt` | Topic-episode research request, script prompt, and research/editor instructions. |
| `prompts/P*.txt` | Prompt text, one file per prompt ID. |
| `prompts/script_tuning.txt` | Claude script requirements (length, quotes, structure) added by the `script_tuning` part. |
| `models.json` | Known models by name, with web-search support and availability. |
| `run_podcast.py` | The runner (`--check` validates only, `--no-email` skips the email). |
| `eleven_v4.py` | Single-voice V4 narration through the Text to Dialogue REST API. |
| `voice_sample.txt` | Sample narration text for the `voice_sample` preview. |
| `intro_outro.py`, `intro_outro.json` | Inspect and re-record the intro and outro (the **Intro and Outro V2** action). |
| `synth_bed.py` | The light synth music bed for the intro and outro candidates. |
| `update_models.py` | Refreshes `models.json` from the OpenAI, Anthropic and Google APIs. |
| `audio_polish.py` | ffmpeg finishing: soxr resampling when joining intro/narration/outro, and narration leveled to the intro's loudness. |

Google credentials (`GOOGLE_CREDS_JSON`) are still used for Cloud Storage and
Google text-to-speech, but nothing reads or writes the sheet.

## Narration

Daily and custom-topic episodes use `eleven_v4` with the existing voice ID
`TX3LPaxmHKxFdv7VOQHJ`. V2 sends Stability and Similarity through the Text to
Dialogue endpoint, using sentence-aware chunks below its recommended 2,000
character request limit and 100-character adjacent-text context for continuity.
The output format stays MP3 at 44.1 kHz/128 kbps, avoiding new subscription-tier
requirements; existing chunk assembly and final episode finishing still apply.
V4 audio arrives at about -26 LUFS, about 3.5 LU quieter than V3 narration and
5 LU below the intro (-20.8 LUFS). When the episode is assembled, any clip more
than 2 LU from the intro's loudness (V4 or Google narration) is leveled to
match it, so there is no jump in volume after the intro.

V4 does not support Speed or Style, so those fields are omitted. V3 also did not
support the former Speed setting; no audio speed adjustment is added. The same
voice ID can sound different on V4. Google fallback still uses Alnilam at 1.08
on ElevenLabs credit/quota errors. If V4 fails for any other reason, the same
voice is retried once on Eleven v3 so the episode still ships; the log and the
run page's **Narration** line say which model and voice were used.

To hear the voice before an episode uses it, run **Preview V2 Research** with
`voice_sample` on. It narrates `voice_sample.txt` (two V4 requests, about 2,200
characters, with no fallback so a V4 problem shows as a failure), attaches the
MP3 (leveled to the intro, as in an episode) to the run as the `voice-sample`
artifact, reports its pace and loudness next to the intro, outro and latest
saved audio, and uploads or emails nothing.

To roll back narration, set `elevenlabs.Model` to `eleven_v3` in both workflow
files. V2 still supports the existing Text to Speech helper for that model.

## Intro and outro

Episodes join the intro, narration and outro named in the `merge_audio` step of
`workflow.json` and `topic_workflow.json`. They now use
`Intro_v4_original_music.mp3` and `Outro_v4_original_music.mp3` (Eleven v4 over
the show's own music), approved on 2026-10-12. `Intro.mp3` and `Outro.mp3`
remain in Cloud Storage but episodes no longer use them; switching back is a
two-line change in each workflow file. The **Intro and Outro V2** action
manages the clips:

- `check` joins each workflow's intro, the latest saved narration and its
  outro exactly as an episode's merge step does, without uploading or emailing
  anything. It reports every part and the join (length, loudness, true peak),
  fails if a part is missing or the join is off, and attaches the opening and
  ending of the join. Run it after changing the intro or outro.

- `history` (read-only) looks for the music older clips used: stored versions
  of the clips, the voice-cancelled music under the current ones (attached to
  the run), and the opening of older episodes.
- `inspect` (read-only) reports each current clip's length, loudness, pauses and
  ElevenLabs transcript, and the original generation if it is still in
  ElevenLabs history. With the show's own track as the music, it also
  describes the track (length, level over time, tempo) and finds where the
  current clips' music sits in it and how far under the voice it was.
- `record` narrates the text in `intro_outro.json` with the episode voice and
  model and makes two candidates per clip (each clip's `source` is the one
  episodes use now, for comparison and loudness; `record` refuses to write any
  file the episode workflows use): voice only (the clip's `file`, e.g.
  `Intro_v4.mp3`) and over the music bed (its `music_file`). The bed is one of:
  - The show's own track (`"source": "url"`; now `Music Bed.wav`, the music
    under the original intro and outro: a 35-minute, very quiet loop bed, of
    which both original clips use the stretch from 26:56.4, hence
    `"start_seconds": 1616.4`). Give its link as the action's
    `music_link` input; a Google Drive share link works once its General
    access is "Anyone with the link". The repo and its logs are public, so the
    link is masked and never committed. `record` saves the track to Cloud
    Storage as the music's `file`, so later runs need no link. A link that may be public
    can go in `"url"` instead.
  - A synth bed from `synth_bed.py` (`"source": "synth"`) in one of two
    styles: `upbeat` (a relaxed 112 BPM groove with electric-piano-like bells,
    a pulsing bass, soft drums and pads) or `calm` (soft pads, a gentle
    arpeggio and a low bass at 100 BPM).
  - Eleven Music (`"source": "eleven"`), which needs the API key's
    music_generation permission.

  `"start_seconds"` picks where in the track the bed starts; a clip's own
  `"music"` settings (e.g. `{"start_seconds": 30}` on the outro) override the
  shared ones. The bed starts `lead_in_seconds` before the voice, sits about
  `below_voice_lu` (9) LU under it on its own, ducks under speech, and fades
  out `tail_seconds` after it; a track that runs out sooner plays once and
  fades at its end. The bed is saved once (as the music's `file`) so later
  re-records reuse the same music; change that name to make or download a new one. Candidates are
  leveled to the current intro, saved to Cloud Storage under their new names,
  and attached to the run with a review MP3 (current clip, then each
  candidate) that is also emailed when `send_email` is on. It never overwrites
  the old files; episodes switch only when the workflow files name a
  candidate, so switching back is a one-line change.

## Resending an episode

If the emailed episode won't open, run the **Resend V2 Episode Email** action
(`resend_episode.py`). It takes the newest episode in `podcasts/` (or the one
named in `episode`) and its description in `descriptions/`, checks that the MP3
decodes from start to end without errors and matches its reported length, and
that the email built from it carries the file intact and under Gmail's size
limit. It then emails the episode again with the same attachment names, but only
if every check passes; `check_only` stops after the checks. Nothing is
regenerated or uploaded.

## Changing a model

Edit the `model` (and `web_search`) of the step in `workflow.json`, using the
model's API name, e.g. `"model": "claude-opus-5-5"`. No numeric model IDs are
involved. `python podcast_v2/run_podcast.py --check` confirms the name is in
`models.json` and supports web search if the step asks for it.

Research steps with web search go through `news_research.py`, which caps spend
using per-token prices in its `RATES` table, so a new research model needs its
prices added there. Research currently uses `gpt-6.1-sol`, which searches and
writes the brief in one pass. `gpt-6-astra` instead means a 5.6 Sol search plus
an Astra editing pass.

To confirm the API key can use a model, run **Update Models V2** with
`probe_model` set. To see what research would pick today without making an
episode, run **Preview V2 Research**: it runs only the prior-episode check and
research, shows the brief on the run page, uploads and emails nothing, and does
not count as the day's episode. Turn on `include_script` to also see the script
and title/description it would write (still no audio, uploads or email).

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

## Custom-topic episodes

Enter a **Custom topic** when starting **Run AI Podcast V2** (or pass `--topic` /
`CUSTOM_TOPIC`) to make a full episode on that one topic, e.g. "Meta Muse new AI tool
and adoption". It replaces the daily multi-story format with `topic_workflow.json`:
research focused on the topic's latest news, adoption, feedback and perspectives
(with verified quotes), a 3-5 segment single-topic script of the same length
(about 7 minutes: 5,800-6,800 characters, under 7,300), then the usual title/description,
narration, intro/outro and email. Recent episodes are still passed to research so
it focuses on what is new. Like any manual V2 run, it counts as that day's episode,
so the 4 p.m. automatic run skips.

## Prior-episode check

The first step reads the newest 15 episodes from the RSS feed and passes them,
with P8, to the research step, as V1 did through the Posted Podcasts tab. If
the feed can't be read or lists no episodes, the run stops before any paid calls.
The script step also sees the list so it can skip repeats. An update on an earlier
story is told as today's news, and the script and description are told never to
mention past episodes or earlier coverage.

The feed is read past any cache (twice, keeping the copy with the newest
episode) and sorted by publish date. As a backstop, any episode this pipeline
saved to `descriptions/` in Cloud Storage between 8 hours and 4 days ago that
the feed doesn't list yet is added to prior coverage, so a stale feed can't let
a published story repeat. Each run logs the feed's newest episode and any
episode added this way.
