"""Keep local WAV masters while delivering the same MP3 files as before."""

from pathlib import Path
import shutil

from pydub import AudioSegment


# Only reuse masters created and uploaded by this process, never an old sidecar.
_masters_by_file = {}
_masters_by_blob = {}


def export_audio(audio, output_path, bitrate="192k"):
    """Export WAV losslessly, or an MP3 plus a WAV master for later assembly."""
    output_path = Path(output_path)
    if output_path.suffix.lower() == ".wav":
        with audio.export(output_path, format="wav"):
            pass
        return output_path
    if output_path.suffix.lower() != ".mp3":
        raise ValueError("Audio output must be .mp3 or .wav")

    key = output_path.resolve()
    _masters_by_file.pop(key, None)
    master_path = output_path.with_suffix(".wav")
    # Reusing an output filename must not attach new audio to an older upload.
    for blob_name, old_master in list(_masters_by_blob.items()):
        if old_master == master_path.resolve():
            del _masters_by_blob[blob_name]
    with audio.export(master_path, format="wav"):
        pass
    with audio.export(output_path, format="mp3", bitrate=bitrate):
        pass
    _masters_by_file[key] = master_path.resolve()
    return output_path


def load_audio_for_merge(audio_path):
    """Prefer the original PCM when this MP3 was created during this run."""
    master = _masters_by_file.get(Path(audio_path).resolve())
    source = master if master and master.is_file() else Path(audio_path)
    with source.open("rb") as stream:
        return AudioSegment.from_file(stream, format=source.suffix.lstrip(".").lower())


def register_uploaded_audio_master(audio_path, blob_name):
    """Associate a successful upload with its local master, if available."""
    _masters_by_blob.pop(blob_name, None)
    master = _masters_by_file.get(Path(audio_path).resolve())
    if master and master.is_file():
        _masters_by_blob[blob_name] = master


def copy_uploaded_audio_master(blob_name, download_path):
    """Return a disposable WAV copy for assembly, or None for normal download."""
    master = _masters_by_blob.get(blob_name)
    if not master or not master.is_file():
        return None
    destination = Path(download_path).with_suffix(".wav")
    # A separate copy lets the existing merge cleanup remove its inputs safely.
    if destination.resolve() == master.resolve():
        destination = destination.with_name(destination.stem + "_merge.wav")
    shutil.copyfile(master, destination)
    return destination
