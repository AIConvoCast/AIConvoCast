"""Google narration for V2, used when ElevenLabs is out of credits.

Gemini-TTS reads the script in one of the Chirp 3 HD voices, steered by a
podcast-host style prompt, which sounds more natural than Chirp 3 HD's plain
read. If Google refuses the Gemini request (an unknown model, a project
without access, a field this client library lacks), the whole script is read
with Chirp 3 HD at the pace the pipeline has always used, so the episode
still ships. Settings live in the voice step's "google_voice" entry in
workflow.json; an empty "model" uses Chirp 3 HD only.
"""

import tempfile
from pathlib import Path

DEFAULTS = {
    # Google's Gemini-TTS model for controllable long-form narration such as podcasts.
    "model": "gemini-2.5-pro-tts",
    "voice": "Alnilam",
    "prompt": (
        "Read this as the host of a daily AI news podcast: warm, confident and conversational, "
        "at a brisk but unhurried pace with clear diction. Stress names and numbers naturally, "
        "pause briefly between paragraphs, and keep the same voice and energy from start to "
        "finish. Say NVIDIA as en-VID-ee-uh, OpenAI as Open A I, and xAI as X A I."
    ),
}
# Gemini-TTS takes about 4,000 bytes of text per request. Curly quotes and
# dashes take three bytes each, so stay well under it.
CHUNK_CHARS = 3000
TIMEOUT_SECONDS = 300


def settings(step):
    """The voice step's google_voice entry over the defaults."""
    merged = dict(DEFAULTS)
    merged.update({key: value for key, value in (step.get("google_voice") or {}).items() if value is not None})
    return merged


def gemini(legacy, text, google, output_path):
    """Read text with Gemini-TTS, a few thousand characters per request, into one MP3."""
    client = getattr(legacy, "google_tts_client", None)
    if client is None:
        raise RuntimeError("The Google Text-to-Speech client is not configured.")
    tts = legacy.texttospeech
    chunks = legacy.split_text_into_chunks(text, max_length=CHUNK_CHARS, preserve_words=True)
    if not chunks or any(not chunk.strip() for chunk in chunks):
        raise ValueError("There is no text to read.")
    voice = tts.VoiceSelectionParams(language_code="en-US", name=google["voice"], model_name=google["model"])
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
                raise RuntimeError(f"Gemini-TTS returned no audio for part {index} of {len(chunks)}.")
            part = Path(folder) / f"part_{index}.wav"
            part.write_bytes(response.audio_content)  # LINEAR16 arrives as a complete WAV file
            parts.append(part)
        print(f"  Gemini-TTS ({google['model']}, {google['voice']}): {len(parts)} part(s).")
        if len(parts) == 1:
            from pydub import AudioSegment

            legacy.export_audio(AudioSegment.from_wav(parts[0]), output_path, bitrate=legacy.DEFAULT_MP3_EXPORT_BITRATE)
        elif not legacy.merge_multiple_audio_files(parts, output_path):
            raise RuntimeError("The Gemini-TTS parts could not be joined.")
    if not output_path.is_file():
        raise RuntimeError("Gemini-TTS produced no audio file.")
    return output_path


def narrate(legacy, text, step, output_path):
    """(audio path or None, label): Gemini-TTS, or Chirp 3 HD if Gemini fails or is switched off."""
    google = settings(step)
    if google.get("model"):
        try:
            return gemini(legacy, text, google, output_path), f"Google {google['voice']} ({google['model']})"
        except Exception as error:
            print(f"  ⚠️ Gemini-TTS ({google['model']}) failed ({type(error).__name__}: {str(error)[:300]}); "
                  "reading the script with Chirp 3 HD instead.")
    voice = legacy.get_google_chirp3_voice_name_by_id(step.get("google_fallback_voice_id", "1"))
    return legacy.generate_google_voice_audio(text, voice, output_path), f"Google {voice} (Chirp 3 HD)"
