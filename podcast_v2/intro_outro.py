"""Inspect and re-record the episode intro and outro with the narration voice.

--inspect  For each current clip (Intro.mp3, Outro.mp3 in Cloud Storage), report its
           length, format, loudness and pauses, transcribe it with ElevenLabs Speech
           to Text, measure the level where nobody speaks (a music bed is not near
           silent there), look for the original generation in ElevenLabs history,
           and list the files at the top of the bucket.
--record   For each clip in intro_outro.json, narrate its text with the episode
           voice and model and make two candidates, voice only and over a light
           music bed (Eleven Music, composed once and saved so later re-records
           reuse the same music), both leveled to the current intro. Save every
           candidate to Cloud Storage under its own new name (old files are never
           overwritten) and build one review MP3: current clip, then each
           candidate, for intro and outro. With --email the review file goes to
           the usual episode address.

Episodes keep the current clips until workflow.json and topic_workflow.json name
a candidate. Both modes write a report to the run page; --record leaves the
candidates and review file in generated_mp3/intro_outro/ for the run's artifacts.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
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


def segment_level(path, start, end):
    """Mean level in dBFS of path between start and end seconds (None if too short)."""
    if end - start < 0.2:
        return None
    log = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(path),
         "-af", "volumedetect", "-f", "null", "-"],
        check=True, capture_output=True, text=True).stderr
    found = re.findall(r"mean_volume: (-?[\d.]+|-inf) dB", log)
    return float(found[-1]) if found else None


def background_levels(path, words, length):
    """Levels where nobody speaks: before the first word, between sentences, after the last.

    Speech alone is near silent there (about -60 dBFS or lower); a music bed is not.
    """
    spoken = [w for w in words if w.get("type") == "word" and "start" in w and "end" in w]
    if not spoken:
        return {}
    levels = {"before the first word": segment_level(path, 0.0, spoken[0]["start"] - 0.05),
              "after the last word": segment_level(path, spoken[-1]["end"] + 0.05, length)}
    gaps = [segment_level(path, a["end"] + 0.05, b["start"] - 0.05)
            for a, b in zip(spoken, spoken[1:]) if b["start"] - a["end"] >= 0.4]
    gaps = [g for g in gaps if g is not None]
    if gaps:
        levels["pauses between words"] = max(gaps)
    return {name: level for name, level in levels.items() if level is not None}


def bucket_root_files(legacy):
    """Files at the top of the Cloud Storage bucket (where Intro.mp3 lives), newest first."""
    client = legacy.get_gcs_client()
    if not client:
        return []
    blobs = client.bucket(legacy.GCS_BUCKET_NAME).list_blobs(delimiter="/")
    files = [(blob.name, blob.size or 0, blob.updated) for blob in blobs]
    return sorted(files, key=lambda f: f[2] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


def spectral_flatness(path, start, end):
    """0 for tonal sound such as music, towards 1 for noise, over 100-5000 Hz (None if too short)."""
    import numpy as np

    raw = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                          "-i", str(path), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         check=True, capture_output=True).stdout
    samples = np.frombuffer(raw, dtype="<i2").astype(float)
    if len(samples) < 3200:
        return None
    power = np.abs(np.fft.rfft(samples * np.hanning(len(samples)))) ** 2 + 1e-12
    freqs = np.fft.rfftfreq(len(samples), 1 / 16000)
    band = power[(freqs >= 100) & (freqs <= 5000)]
    return float(np.exp(np.mean(np.log(band))) / np.mean(band))


def quiet_spans(words, length, minimum=0.4):
    """(start, end) of stretches with no speech: before the first word, pauses, after the last."""
    spoken = [w for w in words if w.get("type") == "word" and "start" in w and "end" in w]
    if not spoken:
        return [(0.0, length)]
    edges = [0.0] + [x for w in spoken for x in (w["start"], w["end"])] + [length]
    spans = [(edges[i] + 0.05, edges[i + 1] - 0.05) for i in range(0, len(edges), 2)]
    return [(a, b) for a, b in spans if b - a >= minimum]


def describe_background(path, words, length):
    """One line on whether the quiet stretches hold music: level and spectral flatness."""
    spans = quiet_spans(words, length)
    if not spans:
        return "no pauses long enough to measure."
    measured = []
    for start, end in spans:
        level = segment_level(path, start, end)
        if level is not None:
            measured.append((level, start, end))
    if not measured:
        return "no pauses long enough to measure."
    level, start, end = max(measured)
    flatness = spectral_flatness(path, start, end)
    verdict = ("likely music" if level > -45 and flatness is not None and flatness < 0.2
               else "likely just silence or room noise" if level < -50 else "unclear")
    return (f"loudest quiet stretch {start:.1f}-{end:.1f} s at {level:.0f} dBFS, spectral flatness "
            f"{'n/a' if flatness is None else f'{flatness:.2f}'} ({verdict}).")


def object_versions(legacy, name):
    """Every stored generation of a bucket object (more than one only if versioning is on)."""
    bucket = legacy.get_gcs_client().bucket(legacy.GCS_BUCKET_NAME)
    return sorted(((b.generation, b.updated, b.size or 0) for b in bucket.list_blobs(prefix=name, versions=True)
                   if b.name == name), key=lambda v: v[1])


def download_version(legacy, name, generation, path):
    bucket = legacy.get_gcs_client().bucket(legacy.GCS_BUCKET_NAME)
    bucket.blob(name, generation=generation).download_to_filename(str(path))
    return Path(path)


def episode_samples(legacy, before, count=4):
    """Older episodes (podcasts/ folder), spread evenly over those made before `before`."""
    names = sorted(n for n in legacy.list_files_in_gcs_folder("podcasts/") if n.endswith(".mp3"))
    older = [n for n in names if Path(n).name[:8] < before.strftime("%Y%m%d")]
    if len(older) <= count:
        return older
    step = (len(older) - 1) / (count - 1)
    return [older[round(i * step)] for i in range(count)]


def clip_start(path, seconds, output):
    subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-t", f"{seconds}", "-i", str(path),
                    "-c:a", "pcm_s16le", str(output)], check=True, capture_output=True)
    return Path(output)


def history(legacy, config, work):
    """Look for the music that older intros and outros used: stored versions and older episodes."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    lines = ["## Earlier intros and outros", ""]
    newest = None
    for name, clip in config["clips"].items():
        try:
            versions = object_versions(legacy, clip["source"])
        except Exception as error:
            lines += [f"Could not list versions of {clip['source']} ({error}).", ""]
            continue
        lines.append(f"### {clip['source']}: {len(versions)} stored version(s)")
        for generation, updated, size in versions:
            lines.append(f"- {updated:%Y-%m-%d}, {size / 1e6:.2f} MB (generation {generation})")
            if name == "intro":
                newest = max(newest or updated, updated)
        for generation, updated, size in versions[:-1]:  # older generations only
            try:
                path = download_version(legacy, clip["source"], generation, work / f"{name}_{generation}.mp3")
                text, events, words = transcribe(legacy, path)
                lines.append(f"  - {updated:%Y-%m-%d}: \"{text[:120]}\" events: {', '.join(events) or 'none'}; "
                             + describe_background(path, words, duration_seconds(path)))
            except Exception as error:
                lines.append(f"  - {updated:%Y-%m-%d}: could not analyse ({error}).")
        lines.append("")
    if newest:
        lines += [f"### Older episodes (before the current intro, {newest:%Y-%m-%d}): first 25 seconds", ""]
        for blob in episode_samples(legacy, newest):
            try:
                episode = legacy.download_mp3_file_from_gcs(blob)
                start = clip_start(episode, 25, work / f"{Path(blob).stem[:15]}_start.wav")
                text, events, words = transcribe(legacy, start)
                lines.append(f"- {Path(blob).name[:8]}: \"{text[:120]}\" events: {', '.join(events) or 'none'}; "
                             + describe_background(start, words, 25.0))
            except Exception as error:
                lines.append(f"- {blob}: could not analyse ({error}).")
        lines.append("")
        samples = episode_samples(legacy, newest)
        if samples:
            lines += timeline(legacy, samples[-1], work)
    return lines


def timeline(legacy, blob, work, seconds=45):
    """Where the old intro's voice and music sit in the opening of one episode."""
    lines = [f"### Opening of {Path(blob).name} (first {seconds} s)", ""]
    try:
        start = clip_start(legacy.download_mp3_file_from_gcs(blob), seconds, Path(work) / "timeline.wav")
        text, events, words = transcribe(legacy, start)
        spoken = [w for w in words if w.get("type") == "word" and "start" in w]
        sentence, begun = [], None
        for word in spoken:
            begun = word["start"] if begun is None else begun
            sentence.append(word["text"])
            if word["text"].rstrip().endswith((".", "!", "?", ":")):
                lines.append(f"- {begun:5.1f}-{word['end']:5.1f} s speech: {' '.join(sentence)[:90]}")
                sentence, begun = [], None
        if sentence:
            lines.append(f"- {begun:5.1f}-{spoken[-1]['end']:5.1f} s speech: {' '.join(sentence)[:90]}")
        for a, b in quiet_spans(words, float(seconds), minimum=0.3):
            level, flatness = segment_level(start, a, b), spectral_flatness(start, a, b)
            lines.append(f"- {a:5.1f}-{b:5.1f} s no speech: {level:.0f} dBFS, flatness "
                         f"{'n/a' if flatness is None else f'{flatness:.2f}'}")
        for second in range(0, seconds, 3):
            level = segment_level(start, second, min(second + 3, seconds))
            lines.append(f"  - level {second:2d}-{min(second + 3, seconds):2d} s: {level:.0f} dBFS")
    except Exception as error:
        lines.append(f"Could not analyse it ({error}).")
    lines.append("")
    return lines


def transcribe(legacy, path):
    """ElevenLabs Speech to Text with audio-event tags, e.g. (music)."""
    with open(path, "rb") as audio:
        response = legacy.requests.post(
            f"{API}/speech-to-text", headers={"xi-api-key": legacy.ELEVENLABS_API_KEY},
            data={"model_id": STT_MODEL, "tag_audio_events": "true"},
            files={"file": (Path(path).name, audio, "audio/mpeg")}, timeout=(10, 180))
    response.raise_for_status()
    result = response.json()
    words = result.get("words", [])
    events = sorted({word["text"] for word in words if word.get("type") == "audio_event"})
    return result.get("text", "").strip(), events, words


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
    for name, clip in config["clips"].items():
        lines.append(f"### {name.title()} ({clip['source']})")
        path = legacy.download_mp3_file_from_gcs(clip["source"])
        if not path:
            lines += ["Could not download it from Cloud Storage.", ""]
            continue
        length = None
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
            text, events, words = transcribe(legacy, path)
            lines += ["Transcript:", "", f"> {text}", ""]
            lines.append(f"Audio events: {', '.join(events) if events else 'none tagged'}.")
            if length:
                levels = background_levels(path, words, length)
                if levels:
                    lines.append("Level where nobody speaks (speech alone is about -60 dBFS or lower there; "
                                 "music is much higher): " +
                                 "; ".join(f"{where} {level:.0f} dBFS" for where, level in levels.items()) + ".")
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
    try:
        files = bucket_root_files(legacy)
        lines += ["### Files at the top of the Cloud Storage bucket", ""]
        lines += [f"- {name} ({size / 1e6:.2f} MB, updated {updated:%Y-%m-%d})" if updated
                  else f"- {name} ({size / 1e6:.2f} MB)" for name, size, updated in files]
        lines.append("")
    except Exception as error:
        lines += [f"Could not list the bucket ({error}).", ""]
    return lines


def compose_music(legacy, music, seconds, output):
    """Instrumental bed from Eleven Music, at least `seconds` long."""
    response = legacy.requests.post(
        f"{API}/music", headers={"xi-api-key": legacy.ELEVENLABS_API_KEY, "Accept": "audio/mpeg"},
        json={"prompt": music["prompt"], "music_length_ms": int(seconds * 1000), "force_instrumental": True},
        timeout=(10, 300))
    if response.status_code != 200:
        kind = ("credit/quota error" if legacy.is_elevenlabs_credit_quota_error(response.text, response.status_code)
                else f"HTTP {response.status_code}")
        raise RuntimeError(f"Eleven Music refused the request ({kind}): {response.text[:300]}")
    if not response.content:
        raise RuntimeError("Eleven Music returned empty audio.")
    Path(output).write_bytes(response.content)
    return Path(output)


def music_description(music):
    if music.get("source", "synth") == "eleven":
        return "a light synth bed from Eleven Music"
    from podcast_v2.synth_bed import STYLES

    return f"a synth bed made for the show ({STYLES[music.get('style', 'calm')]})"


def make_music_bed(legacy, music, seconds, work):
    """Compose a bed of at least `seconds`: synthesized here (default) or by Eleven Music."""
    if music.get("source", "synth") == "eleven":
        return compose_music(legacy, music, seconds, Path(work) / "music_bed.mp3")
    from podcast_v2 import synth_bed

    return synth_bed.compose(seconds, Path(work) / "music_bed.wav", seed=int(music.get("seed", 7)),
                             style=music.get("style", "calm"))


def mix_over_music(voice, music, output, music_settings):
    """Voice over the bed: lead-in, ducking under speech, fade out after the tail."""
    lead = float(music_settings["lead_in_seconds"])
    tail = float(music_settings["tail_seconds"])
    total = lead + duration_seconds(voice) + tail
    if duration_seconds(music) < total:
        raise RuntimeError(f"The music bed is shorter than the {total:.1f}-second clip it must cover.")
    gain = (float(measure_loudness(voice)["input_i"]) - float(music_settings["below_voice_lu"])
            - float(measure_loudness(music)["input_i"]))
    fade = min(2.5, tail)
    # The bed is thinned below 70 Hz and around 350 Hz so it leaves room for the voice.
    graph = (f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={gain:.2f}dB,"
             "highpass=f=70,equalizer=f=350:t=q:w=1.0:g=-4,"
             f"atrim=0:{total:.3f},afade=t=in:st=0:d=0.8,afade=t=out:st={total - fade:.3f}:d={fade:.3f}[bed];"
             f"[0:a]aresample=48000,aformat=channel_layouts=stereo,adelay={int(lead * 1000)}:all=1,"
             f"apad=whole_dur={total:.3f}[voice];"
             "[voice]asplit=2[key][speech];"
             "[bed][key]sidechaincompress=threshold=0.02:ratio=4:attack=20:release=900[ducked];"
             "[ducked][speech]amix=inputs=2:duration=first:normalize=0[out]")
    subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-i", str(voice), "-i", str(music),
                    "-filter_complex", graph, "-map", "[out]", "-c:a", "pcm_s16le", str(output)],
                   check=True, capture_output=True, text=True)
    return Path(output)


def silence(path, seconds):
    subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-f", "lavfi", "-i",
                    f"anullsrc=r=48000:cl=stereo", "-t", f"{seconds}", "-c:a", "pcm_s16le", str(path)],
                   check=True, capture_output=True, text=True)
    return Path(path)


def clock(seconds):
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def check_config(config):
    """Everything record needs, checked before any paid request."""
    names = set()
    for name, clip in config["clips"].items():
        if not clip.get("text", "").strip():
            raise RuntimeError(f"intro_outro.json has no text for the {name}; run --inspect first.")
        for key in ("file", "music_file"):
            if clip[key] == clip["source"]:
                raise RuntimeError(f"The new {name} must not overwrite {clip['source']}.")
            names.add(clip[key])
    if len(names) != 2 * len(config["clips"]):
        raise RuntimeError("Every candidate in intro_outro.json needs its own file name.")


def record(legacy, config, workflow, out_dir, email=False):
    """Make voice-only and music candidates for each clip, save them, and build a review file."""
    from pydub import AudioSegment

    from podcast_v2.audio_polish import join

    check_config(config)
    out_dir = Path(out_dir)
    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    clips = config["clips"]
    music = config["music"]
    reference_clip = clips["intro"]["source"]
    reference = legacy.download_mp3_file_from_gcs(reference_clip)
    if not reference:
        raise RuntimeError(f"Could not download {reference_clip} to match its loudness.")
    target = float(measure_loudness(reference)["input_i"])
    lines = ["## New intro and outro candidates", "", f"All leveled to the current {reference_clip}: {target:.1f} LUFS.", ""]

    def finish(name, wav, blob):
        leveled = normalize_loudness(wav, work / f"{Path(blob).stem}_leveled.wav", target)
        final = out_dir / blob
        legacy.export_audio(AudioSegment.from_wav(leveled), final, bitrate=legacy.DEFAULT_MP3_EXPORT_BITRATE)
        if not legacy.upload_audio_to_gcs(final, blob):
            raise RuntimeError(f"Uploading {blob} to Cloud Storage failed.")
        lines.append(f"- {name}: {blob}, {duration_seconds(final):.1f} seconds, "
                     f"{float(measure_loudness(final)['input_i']):.1f} LUFS.")
        return final

    voices = {}
    for name, clip in clips.items():
        eleven = episode_voice(workflow, clip)
        path, model = run_podcast.narrate(legacy, clip["text"].strip(), eleven, work / f"{name}_voice.mp3",
                                          fallback=False)
        voices[name] = path
        lines.append(f"{name.title()} narrated with {model}, voice {eleven['voice_id']}.")

    longest = max(duration_seconds(path) for path in voices.values())
    needed = float(music["lead_in_seconds"]) + longest + float(music["tail_seconds"]) + 1.0
    music_problem = None
    bed = legacy.download_mp3_file_from_gcs(music["file"])
    if bed and duration_seconds(bed) >= needed:
        lines.append(f"Music: reusing {music['file']} from Cloud Storage.")
    else:
        try:
            bed = make_music_bed(legacy, music, needed, work)
            saved = bed
            if bed.suffix.lower() == ".wav":  # keep the WAV for mixing, save an MP3 copy
                saved = work / "music_bed_upload.mp3"
                legacy.export_audio(AudioSegment.from_wav(bed), saved, bitrate=legacy.DEFAULT_MP3_EXPORT_BITRATE)
            if not legacy.upload_audio_to_gcs(saved, music["file"]):
                raise RuntimeError(f"Uploading {music['file']} to Cloud Storage failed.")
            lines.append(f"Music: composed {music_description(music)}, "
                         f"{duration_seconds(bed):.0f} seconds, and saved it as {music['file']}.")
        except Exception as error:  # the voice-only candidates are still worth reviewing
            bed, music_problem = None, str(error)
            lines.append(f"Music: unavailable, so only voice-only candidates were made ({music_problem}).")
    lines.append("")

    review = []
    gap = silence(work / "gap.wav", 1.5)
    for name, clip in clips.items():
        current = legacy.download_mp3_file_from_gcs(clip["source"])
        plain = finish(f"{name.title()}, voice only", voices[name], clip["file"])
        if current:
            review.append((f"Current {name} ({clip['source']})", current))
        review.append((f"New {name}, voice only ({clip['file']})", plain))
        if bed:
            mixed = mix_over_music(voices[name], bed, work / f"{name}_music_mix.wav", music)
            scored = finish(f"{name.title()} over music", mixed, clip["music_file"])
            review.append((f"New {name} over light synth music ({clip['music_file']})", scored))

    parts, timeline, position = [], [], 0.0
    for label, path in review:
        timeline.append(f"{clock(position)}  {label}")
        position += duration_seconds(path) + 1.5
        parts += [path, gap]
    review_path = out_dir / "Intro_Outro_review.mp3"
    with tempfile.TemporaryDirectory() as joined:
        legacy.export_audio(join(parts[:-1], joined), review_path, bitrate=legacy.DEFAULT_MP3_EXPORT_BITRATE)
    lines += ["", "Review file (Intro_Outro_review.mp3), in order:", "", *[f"- {line}" for line in timeline], ""]

    description = "\n".join([
        "Title: New AI Convo Cast intro and outro samples to approve",
        "",
        "Description:",
        "The attached file plays these in order (minute:second):",
        *timeline,
        "",
        "The new versions use the episode voice on Eleven v4."
        + (f" The music versions sit over {music_description(music)}, ducked under the "
           "voice, with a short lead-in and fade-out." if bed else
           f" Light synth music versions could not be made this time ({music_problem});"
           " the voice-only versions match the current clips, which have no music under them."),
        "Reply with which intro and outro to use (voice only" + (", with music" if bed else "")
        + ", or keep the current ones). Episodes keep the current intro and outro until you approve a change.",
    ])
    if email:
        legacy.send_podcast_email(review_path, description, workflow_id="intro/outro review",
                                  audio_filename="AI_Convo_Cast_intro_outro_review.mp3",
                                  description_filename="intro_outro_review.txt")
        lines.append("Emailed the review file to the usual episode address.")
    lines += ["Download the intro-outro artifact below to listen. Episodes use a candidate once "
              "workflow.json and topic_workflow.json name it."]
    return lines


def report(lines):
    print("\n".join(lines))
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--inspect", action="store_true", help="Describe and transcribe the current clips.")
    action.add_argument("--record", action="store_true", help="Make, save and review the new candidates.")
    action.add_argument("--history", action="store_true",
                        help="Look for the music older intros and outros used (stored versions, older episodes).")
    parser.add_argument("--email", action="store_true", help="With --record, email the review file.")
    args = parser.parse_args(argv)
    legacy = run_podcast.load_legacy()
    config = load_config()
    if args.inspect:
        report(inspect(legacy, config))
    elif args.history:
        report(history(legacy, config, Path(legacy.MP3_OUTPUT_DIR) / "history"))
    else:
        workflow = run_podcast.load_json(run_podcast.WORKFLOW_PATH)
        report(record(legacy, config, workflow, Path(legacy.MP3_OUTPUT_DIR) / "intro_outro", email=args.email))
    return 0


if __name__ == "__main__":
    sys.exit(main())
