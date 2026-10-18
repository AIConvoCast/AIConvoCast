"""Check a finished V2 episode and, if it is sound, email it again.

Takes the newest episode in podcasts/ (or the one named with --episode) and the
description in descriptions/ with the same title, then checks that:
- the MP3 decodes from start to end without errors, and its decoded length
  matches the length its header reports;
- the episode email built from it the way the daily run builds it carries the
  file intact, under Gmail's message size limit.

It reports the format, length, size and loudness. Unless --check-only is given,
it then sends the usual episode email again (same attachment names), but only
if every check passes. Nothing is regenerated or uploaded.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from email import policy
from email.parser import BytesParser
from pathlib import Path

V2_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(V2_DIR.parent))

from podcast_v2 import run_podcast  # noqa: E402
from podcast_v2.audio_polish import measure_loudness  # noqa: E402

STAMP = re.compile(r"^\d{8}_\d{6}_")
GMAIL_LIMIT_MB = 25  # for the whole message, after base64 grows the attachment by a third


def title_part(name):
    """The title in a Cloud Storage name such as podcasts/20261018_200653_Title.mp3."""
    return STAMP.sub("", Path(name).stem)


def pick_episode(legacy, episode=None):
    """(episode blob, description blob or None): the named or newest episode and its description."""
    if not episode:
        names = sorted(n for n in legacy.list_files_in_gcs_folder("podcasts/")
                       if n.endswith(".mp3") and STAMP.match(Path(n).name))
        if not names:
            raise RuntimeError("No episodes found in podcasts/.")
        episode = names[-1]
    descriptions = sorted(n for n in legacy.list_files_in_gcs_folder("descriptions/") if n.endswith(".txt"))
    matching = [n for n in descriptions if title_part(n) == title_part(episode)]
    return episode, (matching[-1] if matching else None)


def check_audio(path):
    """(problems, lines) for an MP3: format, a full decode, and decoded against reported length."""
    problems, lines = [], []
    data = Path(path).read_bytes()
    start = ("an ID3 tag" if data[:3] == b"ID3"
             else "an MPEG audio frame" if len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0
             else f"unexpected bytes {data[:4]!r}")
    lines.append(f"- File: {len(data) / 1e6:.1f} MB, starts with {start}.")
    if start.startswith("unexpected"):
        problems.append("the file does not start like an MP3")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                           capture_output=True, text=True)
    info = json.loads(probe.stdout or "{}")
    streams = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if not streams:
        problems.append("ffprobe finds no audio stream" + (f" ({probe.stderr.strip()[:200]})" if probe.stderr else ""))
        return problems, lines
    stream, form = streams[0], info.get("format", {})
    reported = float(form.get("duration", 0) or 0)
    lines.append(f"- Format: {form.get('format_name')}, codec {stream.get('codec_name')}, "
                 f"{stream.get('sample_rate')} Hz, {stream.get('channels')} channel(s), "
                 f"{int(form.get('bit_rate', 0) or 0) // 1000} kbps, {reported:.1f} s reported.")
    if stream.get("codec_name") != "mp3":
        problems.append(f"the audio is {stream.get('codec_name')}, not MP3")
    decode = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-v", "error", "-nostats", "-progress", "pipe:1",
                             "-i", str(path), "-f", "null", "-"], capture_output=True, text=True)
    errors = [line for line in decode.stderr.splitlines() if line.strip()]
    times = re.findall(r"out_time_us=(\d+)", decode.stdout)
    decoded = int(times[-1]) / 1e6 if times else 0.0
    lines.append(f"- Full decode: {decoded:.1f} s of audio, {len(errors)} decoder error(s).")
    if errors:
        problems.append(f"{len(errors)} decoder error(s), first: {errors[0][:160]}")
    if decode.returncode != 0:
        problems.append(f"ffmpeg could not decode the file (exit {decode.returncode})")
    if reported < 60 or abs(decoded - reported) > 1.0:
        problems.append(f"the decoded length ({decoded:.1f} s) does not match the reported {reported:.1f} s")
    try:
        stats = measure_loudness(path)
        lines.append(f"- Loudness: {float(stats['input_i']):.1f} LUFS, true peak {float(stats['input_tp']):.1f} dBTP.")
    except Exception as error:  # informational
        lines.append(f"- Loudness: unavailable ({error}).")
    return problems, lines


def check_email(path, description, audio_filename, description_filename):
    """(problems, lines): build the episode email as the daily run does and read it back."""
    import podcast_email

    problems = []
    message = podcast_email.build_podcast_email(
        path, description, workflow_id="V2 resend",
        sender=os.getenv("PODCAST_EMAIL_FROM", podcast_email.DEFAULT_SENDER),
        recipient=os.getenv("PODCAST_EMAIL_TO", podcast_email.DEFAULT_RECIPIENT),
        audio_filename=audio_filename, description_filename=description_filename)
    raw = message.as_bytes()
    parsed = BytesParser(policy=policy.default).parsebytes(raw)
    parts = [part for part in parsed.iter_attachments() if part.get_content_maintype() == "audio"]
    size = len(raw) / 1e6
    lines = [f"- Email: {size:.1f} MB in all (Gmail allows {GMAIL_LIMIT_MB} MB), subject {parsed['Subject']!r}."]
    if size >= GMAIL_LIMIT_MB:
        problems.append(f"the email is {size:.1f} MB, over Gmail's {GMAIL_LIMIT_MB} MB limit")
    if len(parts) != 1:
        problems.append(f"the email has {len(parts)} audio attachments, not one")
        return problems, lines
    part = parts[0]
    intact = part.get_content() == Path(path).read_bytes()
    lines.append(f"- Attachment: {part.get_content_type()}, {part.get('Content-Transfer-Encoding')}, "
                 f"named {part.get_filename()!r}; {'identical to' if intact else 'DIFFERENT from'} the episode file.")
    if not intact:
        problems.append("the attachment read back from the email differs from the episode file")
    if not (part.get_filename() or "").lower().endswith(".mp3"):
        problems.append("the attachment name does not end in .mp3")
    return problems, lines


def report(lines):
    print("\n".join(lines))
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")


def resend(legacy, episode=None, check_only=False):
    """Check the episode and email it again if sound. Returns (lines, problems)."""
    episode, description_blob = pick_episode(legacy, episode)
    lines = ["## Episode check", "", f"Episode: {episode}"]
    problems = []
    path = legacy.download_mp3_file_from_gcs(episode)
    if not path or not Path(path).is_file():
        return lines + ["", f"Could not download {episode}."], [f"could not download {episode}"]
    if description_blob:
        description_path = Path(legacy.MP3_OUTPUT_DIR) / f"resend_{Path(description_blob).name}"
        downloaded = legacy.download_file_from_gcs(description_blob, description_path)
        description = Path(downloaded).read_text(encoding="utf-8") if downloaded else ""
        lines.append(f"Description: {description_blob}")
    else:
        description = ""
        lines.append("Description: none found with the same title in descriptions/.")
    if not description.strip():
        problems.append("no description text for this episode")
    lines.append("")
    found, audio_lines = check_audio(path)
    problems += found
    lines += audio_lines
    if description.strip():
        found, email_lines = check_email(path, description, Path(episode).name,
                                         Path(description_blob).name if description_blob else None)
        problems += found
        lines += email_lines
    lines.append("")
    if problems:
        lines.append("Problems: " + "; ".join(problems) + ". The episode was not emailed again.")
    elif check_only:
        lines.append("All checks passed. Check only, so nothing was emailed.")
    else:
        legacy.send_podcast_email(path, description, workflow_id="V2 resend", audio_filename=Path(episode).name,
                                  description_filename=Path(description_blob).name)
        lines.append("All checks passed, and the episode email was sent again.")
    return lines, problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--episode", default=os.getenv("EPISODE", "").strip() or None,
                        help="Cloud Storage name of the episode, e.g. podcasts/20261018_200653_Title.mp3")
    parser.add_argument("--check-only", action="store_true", help="Check the episode but do not email it.")
    args = parser.parse_args(argv)
    lines, problems = resend(run_podcast.load_legacy(), args.episode, args.check_only)
    report(lines)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
