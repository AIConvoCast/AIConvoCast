"""Inspect and re-record the episode intro and outro with the narration voice.

--inspect  For each current clip (Intro.mp3, Outro.mp3 in Cloud Storage), report its
           length, format, loudness and pauses (a music bed leaves few silences),
           transcribe it with ElevenLabs Speech to Text, and look for the original
           generation in ElevenLabs history (voice, model, settings, text).
--record   Narrate each clip's text in intro_outro.json with the episode voice and
           model, level it to the current intro's loudness, and save it to Cloud
           Storage under its new name. The old files are never overwritten, so
           switching back is a one-line change in workflow.json.

Both write a report to the run page; --record also leaves the new MP3s in
generated_mp3/intro_outro/ for the run's artifacts.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

V2_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(V2_DIR.parent))

from podcast_v2 import run_podcast  # noqa: E402
from podcast_v2.audio_polish import measure_loudness, normalize_loudness, probe  # noqa: E402

CONFIG_PATH = V2_DIR / "intro_outro.json"
API = "https://api.elevenlabs.io/v1"
STT_MODEL = "scribe_v2"
# Pauses quieter than this, at least this long, count as silence.
SILENCE_DB = -45
SILENCE_SECONDS = 0.3


def load_config(path=CONFIG_PATH):
    return run_podcast.load_json(path)


def episode_voice(workflow, clip):
    """The episode's ElevenLabs settings, with any per-clip overrides."""
    eleven = next(step["elevenlabs"] for step in workflow["steps"] if step["type"] == "voice")
    return dict(eleven, **clip.get("elevenlabs", {}))


def duration_seconds(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        check=True, capture_output=True, text=True)
    return float(json.loads(result.stdout)["format"]["duration"])


def silences(path, noise_db=SILENCE_DB, minimum=SILENCE_SECONDS):
    """Return the lengths of pauses in the clip, using ffmpeg's silencedetect."""
    log = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path),
         "-af", f"silencedetect=noise={noise_db}dB:d={minimum}", "-f", "null", "-"],
        check=True, capture_output=True, text=True).stderr
    return [float(value) for value in re.findall(r"silence_duration: ([\d.]+)", log)]


def transcribe(legacy, path):
    """ElevenLabs Speech to Text with audio-event tags, e.g. (music)."""
    with open(path, "rb") as audio:
        response = legacy.requests.post(
            f"{API}/speech-to-text", headers={"xi-api-key": legacy.ELEVENLABS_API_KEY},
            data={"model_id": STT_MODEL, "tag_audio_events": "true"},
            files={"file": (Path(path).name, audio, "audio/mpeg")}, timeout=(10, 180))
    response.raise_for_status()
    result = response.json()
    events = sorted({word["text"] for word in result.get("words", []) if word.get("type") == "audio_event"})
    return result.get("text", "").strip(), events


def history_matches(legacy, text, limit=5):
    """Past ElevenLabs generations whose text starts like the transcript."""
    words = re.findall(r"[A-Za-z']+", text)[:6]
    if not words:
        return []
    response = legacy.requests.get(
        f"{API}/history", headers={"xi-api-key": legacy.ELEVENLABS_API_KEY},
        params={"page_size": 100, "search": " ".join(words), "source": "TTS"}, timeout=(10, 60))
    response.raise_for_status()
    items = response.json().get("history", [])
    return items[:limit]


def inspect(legacy, config):
    lines = ["## Current intro and outro", ""]
    for name, clip in config.items():
        lines.append(f"### {name.title()} ({clip['source']})")
        path = legacy.download_mp3_file_from_gcs(clip["source"])
        if not path:
            lines += ["Could not download it from Cloud Storage.", ""]
            continue
        try:
            rate, channels = probe(path)
            length = duration_seconds(path)
            stats = measure_loudness(path)
            pauses = silences(path)
            lines.append(f"{length:.1f} seconds, {rate} Hz, {channels} channel(s), "
                         f"{float(stats['input_i']):.1f} LUFS, true peak {float(stats['input_tp']):.1f} dBTP.")
            lines.append(f"Pauses below {SILENCE_DB} dB: {len(pauses)} totalling {sum(pauses):.1f} seconds "
                         "(speech alone pauses between sentences; a music bed fills them).")
        except Exception as error:
            lines.append(f"Audio analysis failed ({error}).")
        try:
            text, events = transcribe(legacy, path)
            lines += ["Transcript:", "", f"> {text}", ""]
            lines.append(f"Audio events: {', '.join(events) if events else 'none tagged'}.")
            matches = history_matches(legacy, text)
            lines.append(f"ElevenLabs history matches: {len(matches)}.")
            for item in matches:
                made = datetime.fromtimestamp(item.get("date_unix", 0), timezone.utc).date()
                lines.append(f"- {made}: voice {item.get('voice_name')} ({item.get('voice_id')}), "
                             f"model {item.get('model_id')}, settings {json.dumps(item.get('settings'))}, "
                             f"text: {item.get('text')!r}")
        except Exception as error:
            lines.append(f"Transcription or history lookup failed ({error}).")
        lines.append("")
    return lines


def record(legacy, config, workflow, out_dir):
    """Narrate each clip with text, level it to the current intro, and upload it."""
    from pydub import AudioSegment

    for name, clip in config.items():  # check everything before any paid request
        if not clip.get("text", "").strip():
            raise RuntimeError(f"intro_outro.json has no text for the {name}; run --inspect first.")
        if clip["file"] == clip["source"]:
            raise RuntimeError(f"The new {name} must not overwrite {clip['source']}.")
    out_dir = Path(out_dir)
    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    reference_clip = config["intro"]["source"]
    reference = legacy.download_mp3_file_from_gcs(reference_clip)
    if not reference:
        raise RuntimeError(f"Could not download {reference_clip} to match its loudness.")
    target = float(measure_loudness(reference)["input_i"])
    lines = ["## New intro and outro", "", f"Leveled to the current {reference_clip}: {target:.1f} LUFS.", ""]
    for name, clip in config.items():
        text = clip["text"].strip()
        eleven = episode_voice(workflow, clip)
        raw = work / f"{name}_raw.mp3"
        path, model = run_podcast.narrate(legacy, text, eleven, raw, fallback=False)
        leveled = normalize_loudness(path, work / f"{name}_leveled.wav", target)
        final = out_dir / clip["file"]
        legacy.export_audio(AudioSegment.from_wav(leveled), final, bitrate=legacy.DEFAULT_MP3_EXPORT_BITRATE)
        stats = measure_loudness(final)
        link = legacy.upload_audio_to_gcs(final, clip["file"])
        if not link:
            raise RuntimeError(f"Uploading {clip['file']} to Cloud Storage failed.")
        lines.append(f"- {name.title()}: {model}, voice {eleven['voice_id']}, {duration_seconds(final):.1f} seconds, "
                     f"{float(stats['input_i']):.1f} LUFS, saved as {clip['file']} ({link}).")
    lines += ["", "Download the intro-outro artifact below to listen. Episodes use these files once "
              "workflow.json and topic_workflow.json name them."]
    return lines


def report(lines):
    print("\n".join(lines))
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--inspect", action="store_true", help="Describe and transcribe the current clips.")
    action.add_argument("--record", action="store_true", help="Record and upload the new clips.")
    args = parser.parse_args(argv)
    legacy = run_podcast.load_legacy()
    config = load_config()
    if args.inspect:
        report(inspect(legacy, config))
    else:
        workflow = run_podcast.load_json(run_podcast.WORKFLOW_PATH)
        report(record(legacy, config, workflow, Path(legacy.MP3_OUTPUT_DIR) / "intro_outro"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
