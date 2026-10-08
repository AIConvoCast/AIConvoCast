"""Single-voice V4 narration through ElevenLabs' Text to Dialogue REST API.

Keep the legacy TTS path available for explicit V3 configurations. REST avoids
requiring a newer ElevenLabs SDK just to use the new dialogue request schema.
"""

import math
import shutil
import tempfile
from pathlib import Path

DIALOGUE_URL = "https://api.elevenlabs.io/v1/text-to-dialogue"
# The dialogue endpoint recommends <=2,000 characters per request even though
# the model advertises a larger limit. Leave room below that request boundary.
CHUNK_MAX_CHARS = 1900


def _setting(config, name, default):
    value = float(config.get(name, default))
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"Eleven v4 {name} must be between 0 and 1.")
    return value


def generate_voice_audio(text, voice_id, output_path, config, legacy):
    """Generate bounded chunks with one voice and clean up on every failure.

Use the existing quota classifier and bounded transient retry policy so V2's
Google fallback continues to work. Never send unsupported speed/style fields.
"""
    if config.get("Model") != "eleven_v4":
        raise ValueError("The V4 dialogue generator requires Model=eleven_v4.")
    if not str(text).strip() or not voice_id:
        raise ValueError("Eleven v4 requires script text and a voice ID.")
    if not legacy.ELEVENLABS_API_KEY:
        raise ValueError("ELEVENLABS_API_KEY is not configured.")
    settings = {
        "stability": _setting(config, "Stability", 0.5),
        "similarity": _setting(config, "Similarity Boost", 0.7),
    }
    chunks = legacy.split_text_into_chunks(text, max_length=CHUNK_MAX_CHARS, preserve_words=True)
    if not chunks or any(not chunk.strip() or len(chunk) > CHUNK_MAX_CHARS for chunk in chunks):
        raise ValueError("Eleven v4 narration chunks are empty or exceed the request limit.")
    output_path = Path(output_path)
    headers = {"xi-api-key": legacy.ELEVENLABS_API_KEY,
               "Content-Type": "application/json", "Accept": "audio/mpeg"}
    print(f"  Eleven v4 narration: {len(chunks)} chunks, voice {voice_id}.")
    # Temporary files never become uploadable output until all chunks succeed.
    with tempfile.TemporaryDirectory(prefix="eleven_v4_", dir=output_path.parent) as directory:
        paths = []
        for index, chunk in enumerate(chunks):
            payload = {"model_id": "eleven_v4", "inputs": [{"text": chunk, "voice_id": voice_id}],
                       "settings": settings}
            if index:
                payload["previous_text"] = chunks[index - 1][-100:]
            if index + 1 < len(chunks):
                payload["future_text"] = chunks[index + 1][:100]

            def request_chunk():
                response = legacy.requests.post(
                    DIALOGUE_URL, json=payload, headers=headers,
                    params={"output_format": "mp3_44100_128"}, timeout=(10, 180),
                )
                try:
                    if legacy.is_elevenlabs_credit_quota_error(
                            response.text if response.status_code != 200 else "", response.status_code):
                        raise ValueError("ElevenLabs credit/quota error: using the configured Google fallback.")
                    response.raise_for_status()
                    if not response.content:
                        raise RuntimeError("Eleven v4 returned empty audio.")
                    return response.content
                finally:
                    response.close()

            audio = legacy.retry_transient(request_chunk, label="Eleven v4 audio")
            path = Path(directory) / f"chunk_{index}.mp3"
            path.write_bytes(audio)
            paths.append(path)
        if len(paths) == 1:
            shutil.copyfile(paths[0], output_path)
        else:
            if not legacy.merge_multiple_audio_files(paths, output_path):
                output_path.unlink(missing_ok=True)
                output_path.with_suffix(".wav").unlink(missing_ok=True)
                raise RuntimeError("Eleven v4 narration chunks could not be merged.")
    return output_path
