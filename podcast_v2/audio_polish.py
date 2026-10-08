"""Audio finishing for V2 with ffmpeg: clean resampling and level-matched clips.

pydub resamples by linear interpolation when it joins clips with different
sample rates (Google's 24 kHz voice with a 44.1 kHz intro), which adds audible
grain. Here every clip is converted with ffmpeg's soxr resampler before joining,
and the narration is leveled to the intro's loudness so the episode has no jump
in volume whichever voice made it (Eleven v4 arrives about 3 LU quieter than v3
did, Google narration differs again).
"""

import json
import math
import re
import subprocess
import tempfile
from pathlib import Path

TARGET_LUFS = -16.0
TRUE_PEAK_DB = -1.5
LOUDNESS_RANGE = 11.0
# Clips within this many LU of the intro keep their own level (Eleven v3 narration
# sat about 1.5 LU below the intro, so it is left as it was).
LEVEL_TOLERANCE_LU = 2.0


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", *args],
                   check=True, capture_output=True, text=True)


def probe(path):
    """Return (sample_rate, channels) of the first audio stream."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=sample_rate,channels", "-of", "json", str(path)],
        check=True, capture_output=True, text=True)
    stream = json.loads(result.stdout)["streams"][0]
    return int(stream["sample_rate"]), int(stream["channels"])


def resample(source, destination, rate, channels):
    """Write a 16-bit WAV at rate/channels using soxr, or ffmpeg's default resampler."""
    base = ["-i", str(source), "-ar", str(rate), "-ac", str(channels), "-c:a", "pcm_s16le"]
    try:
        _ffmpeg(*base[:2], "-af", "aresample=resampler=soxr:precision=28", *base[2:], str(destination))
    except subprocess.CalledProcessError:
        _ffmpeg(*base, str(destination))
    return Path(destination)


def measure_loudness(path):
    """Return EBU R128 stats (input_i LUFS, input_tp dBTP, input_lra LU) for a clip."""
    measured = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path),
         "-af", f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK_DB}:LRA={LOUDNESS_RANGE}:print_format=json",
         "-f", "null", "-"],
        check=True, capture_output=True, text=True).stderr
    return json.loads(re.findall(r"\{[^{}]*\}", measured)[-1])


def normalize_loudness(source, destination, target_lufs=TARGET_LUFS):
    """Two-pass EBU R128 normalization to target_lufs, keeping the sample rate."""
    rate, channels = probe(source)
    target = f"I={target_lufs}:TP={TRUE_PEAK_DB}:LRA={LOUDNESS_RANGE}"
    measured = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-i", str(source),
         "-af", f"loudnorm={target}:print_format=json", "-f", "null", "-"],
        check=True, capture_output=True, text=True).stderr
    stats = json.loads(re.findall(r"\{[^{}]*\}", measured)[-1])
    second = (f"loudnorm={target}:measured_I={stats['input_i']}:measured_TP={stats['input_tp']}"
              f":measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}"
              f":offset={stats['target_offset']}:linear=true")
    # loudnorm works at 192 kHz internally; resample back with soxr.
    _ffmpeg("-i", str(source), "-af", f"{second},aresample=resampler=soxr:precision=28",
            "-ar", str(rate), "-ac", str(channels), "-c:a", "pcm_s16le", str(destination))
    return Path(destination)


def level_to_first(parts, workdir):
    """Bring any clip more than LEVEL_TOLERANCE_LU from the first clip's loudness to it.

    The first clip is the intro, so the narration matches the intro and outro
    the way Eleven v3 narration did. Leveling problems keep a clip as it is.
    """
    try:
        reference = float(measure_loudness(parts[0])["input_i"])
    except Exception as error:
        print(f"  Loudness leveling skipped ({error}).")
        return list(parts)
    if not math.isfinite(reference):
        return list(parts)
    leveled = [parts[0]]
    for index, part in enumerate(parts[1:], start=1):
        try:
            level = float(measure_loudness(part)["input_i"])
            if math.isfinite(level) and abs(level - reference) > LEVEL_TOLERANCE_LU:
                part = normalize_loudness(part, Path(workdir) / f"part_{index}_leveled.wav", reference)
                print(f"  Clip {index + 1} leveled from {level:.1f} to {reference:.1f} LUFS to match the intro.")
        except Exception as error:
            print(f"  Clip {index + 1} kept at its own level ({error}).")
        leveled.append(part)
    return leveled


def join(paths, workdir):
    """Join clips at the highest sample rate and channel count among them, leveled to the first."""
    from pydub import AudioSegment

    formats = [probe(path) for path in paths]
    rate = max(r for r, _ in formats)
    channels = max(c for _, c in formats)
    parts = [resample(path, Path(workdir) / f"part_{index}.wav", rate, channels)
             for index, path in enumerate(paths)]
    combined = None
    for part in level_to_first(parts, workdir):
        clip = AudioSegment.from_wav(part)
        combined = clip if combined is None else combined + clip
    return combined


class AudioFinisher:
    """What the V2 runner calls; `export` is the pipeline's MP3-plus-master writer."""

    def __init__(self, export, bitrate="192k"):
        self.export = export
        self.bitrate = bitrate

    def merge(self, paths, output_path):
        with tempfile.TemporaryDirectory() as workdir:
            self.export(join(paths, workdir), output_path, bitrate=self.bitrate)
        return output_path
