"""Preserve generated files before cloud upload, scoped to a single run."""

import hashlib
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path


class ReusableAudioCache:
    """Fallback for explicitly named intro/outro assets, never latest narration."""
    def __init__(self, directory):
        self.directory = Path(directory)

    def _path(self, blob_name):
        return self.directory / (hashlib.sha256(blob_name.encode()).hexdigest() + ".mp3")

    def save(self, blob_name, source):
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self._path(blob_name)
        temporary = destination.with_suffix(".tmp")
        shutil.copy2(source, temporary)
        temporary.replace(destination)

    def restore(self, blob_name, destination):
        cached = self._path(blob_name)
        if not cached.is_file():
            return None
        shutil.copy2(cached, destination)
        print(f"Using a cached copy of reusable audio: {Path(blob_name).name}")
        return Path(destination)


class LocalArtifacts:
    def __init__(self, root="generated_mp3/runs"):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.directory = Path(root) / f"{stamp}-{uuid.uuid4().hex[:8]}"
        self.files = {}
        self.cloud_logging_failed = False

    def preserve(self, source, blob_name):
        source = Path(source)
        # Hash the full remote name so paths cannot escape the run directory.
        filename = hashlib.sha256(blob_name.encode()).hexdigest()[:16] + "_" + source.name
        self.directory.mkdir(parents=True, exist_ok=True)
        saved = self.directory / filename
        shutil.copy2(source, saved)
        self.files.pop(blob_name, None)
        self.files[blob_name] = saved
        self.write_json("artifacts.json", {key: value.name for key, value in self.files.items()})
        return saved

    def latest(self, prefix):
        prefix = prefix.rstrip("/") + "/"
        return next((name for name in reversed(self.files) if name.startswith(prefix)), None)

    def restore(self, blob_name, destination):
        source = self.files.get(blob_name)
        if source is None or not source.is_file():
            return None
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return destination

    def write_json(self, filename, value):
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self.directory / filename
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        temporary.replace(destination)
        return destination

    def log_to_sheet(self, operation):
        """Cloud audit logging must never prevent local generation/delivery."""
        if self.cloud_logging_failed:
            return False
        try:
            operation()
            return True
        except Exception as exc:
            self.cloud_logging_failed = True
            print(f"Google Sheets logging unavailable ({type(exc).__name__}); continuing with local run records.")
            return False
