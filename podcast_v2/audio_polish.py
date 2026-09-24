"""Audio finishing for V2 with ffmpeg: clean resampling and podcast loudness.

pydub resamples by linear interpolation when it joins clips with different
sample rates (Google's 24 kHz voice with a 44.1 kHz intro), which adds audible
grain. Here every clip is converted with ffmpeg's soxr resampler before joining,
and Google narration is normalized to the usual podcast loudness.
"""

import json
import re
import subprocess
import tempfile
from pathlib import Path

TARGET_LUFS = -16.0
TRUE_PEAK_DB = -1.5
LOUDNESS_RANGE = 11.0


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


def normalize_loudness(source, destination):
    """Two-pass EBU R128 normalization to podcast loudness, keeping the sample rate."""
    rate, channels = probe(source)
    target = f"I={TARGET_LUFS}:TP={TRUE_PEAK_DB}:LRA={LOUDNESS_RANGE}"
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


def join(paths, workdir):
    """Join clips at the highest sample rate and channel count among them."""
    from pydub import AudioSegment

    formats = [probe(path) for path in paths]
    rate = max(r for r, _ in formats)
    channels = max(c for _, c in formats)
    combined = None
    for index, path in enumerate(paths):
        clip = AudioSegment.from_wav(resample(path, Path(workdir) / f"part_{index}.wav", rate, channels))
        combined = clip if combined is None else combined + clip
    return combined


class AudioFinisher:
    """What the V2 runner calls; `export` is the pipeline's MP3-plus-master writer."""

    def __init__(self, export, bitrate="192k"):
        self.export = export
        self.bitrate = bitrate

    def polish_speech(self, audio_path, master_path=None):
        """Normalize loudness in place, starting from the lossless master when there is one."""
        from pydub import AudioSegment

        source = Path(master_path) if master_path and Path(master_path).is_file() else Path(audio_path)
        with tempfile.TemporaryDirectory() as workdir:
            polished = normalize_loudness(source, Path(workdir) / "polished.wav")
            self.export(AudioSegment.from_wav(polished), audio_path, bitrate=self.bitrate)
        return audio_path

    def merge(self, paths, output_path):
        with tempfile.TemporaryDirectory() as workdir:
            self.export(join(paths, workdir), output_path, bitrate=self.bitrate)
        return output_path
