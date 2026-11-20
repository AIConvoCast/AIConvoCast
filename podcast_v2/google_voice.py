"""Google narration for V2, used when ElevenLabs is out of credits.

Gemini-TTS reads the script in one of the Chirp 3 HD voices, steered by a short
newsreader style prompt. The voice step's "google_voice" entry in
workflow.json lists the Gemini models to use, newest first; the first one
Google accepts reads the whole script. If none works (an unknown model, no
access, an odd pace), the whole script is read with Chirp 3 HD at the pace the
pipeline has always used, so the episode still ships. An empty "models" list
uses Chirp 3 HD only.

The script goes in parts (Gemini-TTS takes about 4,000 bytes per request), and
Gemini does not read every part at the same volume, so each part is brought
to the same loudness before the parts are joined.
"""

import tempfile
from pathlib import Path

DEFAULTS = {
    # Newest first. A model Google rejects is skipped; Chirp 3 HD reads the script if none works.
    # On November 20, 2026 this was the newest Gemini-TTS model the project could use: the
    # 3.5 and 3.8 names, and 3.1 Pro, were "not supported" (see SAMPLE_MODELS in run_podcast.py).
    "models": ["gemini-3.1-flash-tts-preview"],
    "voice": "Alnilam",
    "prompt": (
        "Read this news script as a professional podcast newsreader: clear, natural and even, "
        "at a steady conversational pace, with the same tone and volume from start to finish. "
        "Say NVIDIA as en-VID-ee-uh, OpenAI as Open A I, and xAI as X A I."
    ),
}
# Gemini-TTS takes about 4,000 bytes of text per request. Curly quotes and
# dashes take three bytes each, so stay well under it.
CHUNK_CHARS = 3000
TIMEOUT_SECONDS = 300
# Narration runs about 13-17 characters a second. A part far outside this range
# means Gemini skipped or dragged out text, so the next model (or Chirp 3 HD) reads it.
PACE_RANGE = (8.0, 24.0)
# Every part is brought to this loudness before joining; the episode merge then
# matches the whole narration to the intro.
PART_LUFS = -21.0


def seconds(wav_bytes):
    """Length of a WAV file held in memory."""
    import io
    import wave

    with wave.open(io.BytesIO(wav_bytes)) as audio:
        return audio.getnframes() / audio.getframerate()


def settings(step):
    """The voice step's google_voice entry over the defaults, with "models" always a list."""
    merged = dict(DEFAULTS)
    given = step.get("google_voice") or {}
    merged.update({key: value for key, value in given.items() if value is not None})
    if "models" not in given and "model" in given:  # the single-model form
        merged["models"] = [given["model"]] if given["model"] else []
    merged.pop("model", None)
    merged["models"] = [model for model in merged["models"] if model]
    return merged


def loudness(path):
    from podcast_v2.audio_polish import measure_loudness

    return float(measure_loudness(path)["input_i"])


def level(path, destination, target=PART_LUFS):
    """Bring one part to the target loudness; keep it as it is if that fails."""
    from podcast_v2.audio_polish import normalize_loudness

    try:
        return normalize_loudness(path, destination, target)
    except Exception as error:  # an unleveled part is better than no episode
        print(f"  Part kept at its own level ({type(error).__name__}: {error}).")
        return path


def gemini(legacy, text, google, output_path, model=None, report=None):
    """Read text with one Gemini-TTS model, part by part, into one MP3.

    `report`, when given, collects each part's loudness before leveling.
    """
    client = getattr(legacy, "google_tts_client", None)
    if client is None:
        raise RuntimeError("The Google Text-to-Speech client is not configured.")
    model = model or google["models"][0]
    tts = legacy.texttospeech
    chunks = legacy.split_text_into_chunks(text, max_length=CHUNK_CHARS, preserve_words=True)
    if not chunks or any(not chunk.strip() for chunk in chunks):
        raise ValueError("There is no text to read.")
    voice = tts.VoiceSelectionParams(language_code="en-US", name=google["voice"], model_name=model)
    config = tts.AudioConfig(audio_encoding=tts.AudioEncoding.LINEAR16, sample_rate_hertz=24000)
    output_path = Path(output_path)
    # Nothing becomes the episode's audio until every part has been read.
    with tempfile.TemporaryDirectory(prefix="gemini_tts_", dir=output_path.parent) as folder:
        parts = []
        for index, chunk in enumerate(chunks, start=1):
            response = client.synthesize_speech(
                input=tts.SynthesisInput(text=chunk, prompt=google["prompt"]),
                voice=voice, audio_config=config, timeout=TIMEOUT_SECONDS)
            if not response.audio_content:
                raise RuntimeError(f"{model} returned no audio for part {index} of {len(chunks)}.")
            length = seconds(response.audio_content)
            pace = len(chunk) / length if length else float("inf")
            if not PACE_RANGE[0] <= pace <= PACE_RANGE[1]:
                raise RuntimeError(f"{model} part {index} read {len(chunk)} characters in {length:.1f} "
                                   f"seconds ({pace:.1f} a second), outside normal speech.")
            part = Path(folder) / f"part_{index}.wav"
            part.write_bytes(response.audio_content)  # LINEAR16 arrives as a complete WAV file
            if report is not None:
                try:
                    report.setdefault("parts_lufs", []).append(round(loudness(part), 1))
                except Exception:
                    report.setdefault("parts_lufs", []).append(None)
            parts.append(level(part, Path(folder) / f"part_{index}_leveled.wav"))
        print(f"  Gemini-TTS ({model}, {google['voice']}): {len(parts)} part(s), each leveled to {PART_LUFS} LUFS.")
        if len(parts) == 1:
            from pydub import AudioSegment

            legacy.export_audio(AudioSegment.from_wav(parts[0]), output_path, bitrate=legacy.DEFAULT_MP3_EXPORT_BITRATE)
        elif not legacy.merge_multiple_audio_files(parts, output_path):
            raise RuntimeError("The Gemini-TTS parts could not be joined.")
    if not output_path.is_file():
        raise RuntimeError("Gemini-TTS produced no audio file.")
    return output_path


def narrate(legacy, text, step, output_path):
    """(audio path or None, label): the first Gemini model that works, else Chirp 3 HD."""
    google = settings(step)
    for model in google["models"]:
        try:
            return gemini(legacy, text, google, output_path, model=model), f"Google {google['voice']} ({model})"
        except Exception as error:
            print(f"  ⚠️ Gemini-TTS {model} failed ({type(error).__name__}: {str(error)[:300]}).")
    if google["models"]:
        print("  Reading the script with Chirp 3 HD instead.")
    voice = legacy.get_google_chirp3_voice_name_by_id(step.get("google_fallback_voice_id", "1"))
    return legacy.generate_google_voice_audio(text, voice, output_path), f"Google {voice} (Chirp 3 HD)"
