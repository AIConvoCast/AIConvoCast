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

Each model is read through the Cloud Text-to-Speech API. A model that API does
not offer (the Gemini 3.8 TTS models, for one) is read through Google Cloud's
Agent Platform (formerly Vertex AI) instead, with the same service account,
voice and style prompt.
"""

import base64
import io
import re
import tempfile
from pathlib import Path

DEFAULTS = {
    # Newest first. A model Google rejects is skipped; Chirp 3 HD reads the script if none works.
    # Gemini 3.8 Flash TTS (September 2026) is read through Agent Platform. The 3.1 preview,
    # read through Cloud Text-to-Speech, backs it up until Google retires it.
    "models": ["gemini-3.8-flash-tts", "gemini-3.1-flash-tts-preview"],
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
# Agent Platform (formerly Vertex AI) serves Gemini TTS models through generateContent.
AGENT_PLATFORM_URL = ("https://aiplatform.googleapis.com/{version}/projects/{project}/locations/global/"
                      "publishers/google/models/{model}:generateContent")
CREDENTIALS_FILE = "jmio-google-api.json"


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


def cloud_tts_reader(legacy, google, model):
    """A function that reads one part with `model` through Cloud Text-to-Speech and returns a WAV."""
    client = getattr(legacy, "google_tts_client", None)
    if client is None:
        raise RuntimeError("The Google Text-to-Speech client is not configured.")
    tts = legacy.texttospeech
    voice = tts.VoiceSelectionParams(language_code="en-US", name=google["voice"], model_name=model)
    config = tts.AudioConfig(audio_encoding=tts.AudioEncoding.LINEAR16, sample_rate_hertz=24000)

    def read_part(chunk):
        response = client.synthesize_speech(
            input=tts.SynthesisInput(text=chunk, prompt=google["prompt"]),
            voice=voice, audio_config=config, timeout=TIMEOUT_SECONDS)
        return response.audio_content  # LINEAR16 arrives as a complete WAV file

    return read_part


def agent_platform_requests(chunk, google):
    """(API version, request body) pairs to try in order: the Gemini 3.8 TTS form (a voice name and a
    style note on the text), then the earlier generateContent voice form."""
    contents = [{"role": "user", "parts": [{"text": chunk, "speechMetadata": {"style": google["prompt"]}}]}]
    voice_forms = ({"voice": google["voice"]}, {"prebuiltVoiceConfig": {"voiceName": google["voice"]}})
    for version, voice in (("v1", voice_forms[0]), ("v1", voice_forms[1]), ("v1beta1", voice_forms[0])):
        yield version, {"contents": contents, "generationConfig": {
            "responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": voice}}}


def api_error(response):
    """Google's status and message from a failed call, e.g. "403 PERMISSION_DENIED: ..."."""
    try:
        error = response.json().get("error") or {}
        return f"{response.status_code} {error.get('status', '')}: {error.get('message', '')}"
    except ValueError:
        return f"{response.status_code}: {response.text[:300]}"


def wav_from_response(data):
    """The audio in a generateContent response, as a WAV file."""
    candidates = data.get("candidates") or []
    parts = (candidates[0].get("content") or {}).get("parts", []) if candidates else []
    audio = next((part.get("inlineData") or part.get("inline_data") for part in parts
                  if part.get("inlineData") or part.get("inline_data")), None)
    if not audio:
        reason = candidates[0].get("finishReason") if candidates else data.get("promptFeedback")
        raise RuntimeError(f"The response held no audio ({reason}).")
    sound = base64.b64decode(audio["data"])
    kind = audio.get("mimeType") or audio.get("mime_type") or ""
    if "wav" in kind:
        return sound
    rate = re.search(r"rate=(\d+)", kind)
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:  # 16-bit mono PCM
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(int(rate.group(1)) if rate else 24000)
        out.writeframes(sound)
    return buffer.getvalue()


def agent_platform_reader(google, model, credentials_file=CREDENTIALS_FILE, session=None, project=None):
    """A function that reads one part with `model` through Agent Platform and returns a WAV.

    The first request form Google accepts is kept for the remaining parts; a refusal other than
    a malformed request (no access, the API not enabled, an unknown model) is raised at once.
    """
    if session is None:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2.service_account import Credentials

        credentials = Credentials.from_service_account_file(
            credentials_file, scopes=["https://www.googleapis.com/auth/cloud-platform"])
        session, project = AuthorizedSession(credentials), project or credentials.project_id
    accepted = []

    def read_part(chunk):
        errors = []
        for version, body in agent_platform_requests(chunk, google):
            if accepted and (version, body["generationConfig"]["speechConfig"]) != accepted[0]:
                continue
            url = AGENT_PLATFORM_URL.format(version=version, project=project, model=model)
            response = session.post(url, json=body, timeout=TIMEOUT_SECONDS)
            if response.status_code == 200:
                if not accepted:
                    accepted.append((version, body["generationConfig"]["speechConfig"]))
                    print(f"  Agent Platform {version} accepted voiceConfig {body['generationConfig']['speechConfig']['voiceConfig']}.")
                return wav_from_response(response.json())
            errors.append(f"{version}: {api_error(response)}")
            if response.status_code != 400:
                break
        raise RuntimeError("Agent Platform: " + " | ".join(errors))

    return read_part


def gemini(legacy, text, google, output_path, model=None, report=None, reader=None):
    """Read text with one Gemini-TTS model, part by part, into one MP3.

    `reader` reads one part and returns a WAV (Cloud Text-to-Speech by default). `report`,
    when given, collects each part's loudness before leveling.
    """
    model = model or google["models"][0]
    read_part = reader or cloud_tts_reader(legacy, google, model)
    chunks = legacy.split_text_into_chunks(text, max_length=CHUNK_CHARS, preserve_words=True)
    if not chunks or any(not chunk.strip() for chunk in chunks):
        raise ValueError("There is no text to read.")
    output_path = Path(output_path)
    # Nothing becomes the episode's audio until every part has been read.
    with tempfile.TemporaryDirectory(prefix="gemini_tts_", dir=output_path.parent) as folder:
        parts = []
        for index, chunk in enumerate(chunks, start=1):
            audio = read_part(chunk)
            if not audio:
                raise RuntimeError(f"{model} returned no audio for part {index} of {len(chunks)}.")
            length = seconds(audio)
            pace = len(chunk) / length if length else float("inf")
            if not PACE_RANGE[0] <= pace <= PACE_RANGE[1]:
                raise RuntimeError(f"{model} part {index} read {len(chunk)} characters in {length:.1f} "
                                   f"seconds ({pace:.1f} a second), outside normal speech.")
            part = Path(folder) / f"part_{index}.wav"
            part.write_bytes(audio)
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


def read(legacy, text, google, output_path, model, report=None):
    """(audio path, service): `model` read through Cloud Text-to-Speech, or through Agent Platform
    when Cloud Text-to-Speech does not offer it."""
    try:
        return gemini(legacy, text, google, output_path, model=model, report=report), "Cloud Text-to-Speech"
    except Exception as error:
        if "is not supported" not in str(error):
            raise
        print(f"  Cloud Text-to-Speech does not offer {model}; reading it through Agent Platform.")
    if report is not None:
        report.clear()
    reader = agent_platform_reader(google, model, getattr(legacy, "GOOGLE_TTS_SERVICE_ACCOUNT_FILE", CREDENTIALS_FILE))
    return gemini(legacy, text, google, output_path, model=model, report=report, reader=reader), "Agent Platform"


def narrate(legacy, text, step, output_path):
    """(audio path or None, label): the first Gemini model that works, else Chirp 3 HD."""
    google = settings(step)
    for model in google["models"]:
        try:
            return read(legacy, text, google, output_path, model)[0], f"Google {google['voice']} ({model})"
        except Exception as error:
            print(f"  ⚠️ Gemini-TTS {model} failed ({type(error).__name__}: {str(error)[:300]}).")
    if google["models"]:
        print("  Reading the script with Chirp 3 HD instead.")
    voice = legacy.get_google_chirp3_voice_name_by_id(step.get("google_fallback_voice_id", "1"))
    return legacy.generate_google_voice_audio(text, voice, output_path), f"Google {voice} (Chirp 3 HD)"
