"""Run AI Podcast V2: the episode workflow from podcast_v2/, with no Google Sheet.

Prompts, models and steps live in this folder (workflow.json, prompts/,
models.json). Model calls, voice generation, GCS storage and email reuse the
existing pipeline's helpers, so audio and text handling match V1.
"""

import argparse
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

V2_DIR = Path(__file__).resolve().parent
REPO_ROOT = V2_DIR.parent
WORKFLOW_PATH = V2_DIR / "workflow.json"
MODELS_PATH = V2_DIR / "models.json"
PROMPTS_DIR = V2_DIR / "prompts"

STEP_TYPES = {"recent_episodes", "model", "save_text", "voice", "merge_audio"}
PART_PATTERN = re.compile(r"^(prompt|step|gcs_file|gcs_latest_text|gcs_latest_mp3):(.+)$")
TITLE_LINE = re.compile(r"(?im)^#*\s*Title\s*:")
DESCRIPTION_LINE = re.compile(r"(?im)^#*\s*Description\s*:")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_prompt(prompt_id, prompts_dir=PROMPTS_DIR):
    return (Path(prompts_dir) / f"P{prompt_id}.txt").read_text(encoding="utf-8").rstrip("\n")


def validate_workflow(workflow, models, prompts_dir=PROMPTS_DIR):
    """Return a list of configuration problems; empty means the workflow can run."""
    problems = []
    known = {m["name"]: m for m in models.get("models", [])}
    seen = set()
    for index, step in enumerate(workflow.get("steps", []), start=1):
        step_id = step.get("id") or f"#{index}"
        kind = step.get("type")
        if kind not in STEP_TYPES:
            problems.append(f"Step {step_id}: unknown type {kind!r}.")
            continue
        refs = list(step.get("parts", []))
        if "source" in step:
            refs.append(step["source"])
        for ref in refs:
            if ref == "script_tuning":
                continue
            match = PART_PATTERN.match(ref)
            if not match:
                problems.append(f"Step {step_id}: cannot read part {ref!r}.")
            elif match.group(1) == "prompt" and not (Path(prompts_dir) / f"P{match.group(2)}.txt").is_file():
                problems.append(f"Step {step_id}: prompts/P{match.group(2)}.txt does not exist.")
            elif match.group(1) == "step" and match.group(2) not in seen:
                problems.append(f"Step {step_id}: refers to step {match.group(2)!r} before it has run.")
        title_from = step.get("title_from")
        if title_from and title_from not in seen:
            problems.append(f"Step {step_id}: title_from {title_from!r} has not run yet.")
        if kind == "model":
            model = known.get(step.get("model"))
            if model is None:
                problems.append(
                    f"Step {step_id}: model {step.get('model')!r} is not in models.json. "
                    "Run the Update Models V2 action or fix the name."
                )
            elif not model.get("available", True):
                problems.append(f"Step {step_id}: model {model['name']!r} is no longer offered by its provider.")
            elif step.get("web_search") and not model.get("web_search"):
                problems.append(f"Step {step_id}: model {model['name']!r} does not support web search.")
        seen.add(step.get("id"))
    return problems


def format_recent_episodes(rss_xml, count):
    """Match V1's PPU + PPL# output: newest first, title and short description."""
    channel = ET.fromstring(rss_xml).find("channel")
    items = channel.findall("item") if channel is not None else []
    lines = []
    for item in items[:count]:
        title = html.unescape(item.findtext("title", default=""))
        description = re.sub(r"<.*?>", "", html.unescape(item.findtext("description", default="")))
        short = description.split("Help support")[0].strip()
        lines.append(f"Title: {title}\nDescription Short: {short}")
    return "\n\n".join(lines)


def extract_title(text):
    match = re.search(r"#?\s*Title:\s*(.+?)(?=\s*#?\s*Description:|$)", text or "", re.DOTALL | re.IGNORECASE)
    return re.sub(r"^#+\s*", "", match.group(1)).strip() if match else None


def clean_filename(title):
    if not title:
        return None
    title = re.sub(r"(?i)\bpodcast\b[_\-:\s]*", "", str(title))
    cleaned = re.sub(r"\s+", " ", re.sub(r"[^\w\s\-]", "", title)).replace(" ", "_").strip("_")
    return cleaned[:100] or None


class Runner:
    def __init__(self, workflow, legacy, prompts_dir=PROMPTS_DIR):
        self.workflow = workflow
        self.legacy = legacy
        self.prompts_dir = prompts_dir
        self.outputs = {}
        self.records = []
        self.final_audio_path = None
        self.final_audio_filename = None
        self.final_description_text = None
        self.final_description_filename = None

    def filename(self, step, extension, fallback):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        title = clean_filename(extract_title(self.outputs.get(step.get("title_from"), "")))
        return f"{timestamp}_{title or fallback}.{extension}"

    def resolve(self, ref):
        if ref == "script_tuning":
            return self.legacy.OPUS47_SCRIPT_TUNING_APPENDIX.strip()
        kind, value = PART_PATTERN.match(ref).groups()
        if kind == "prompt":
            return load_prompt(value, self.prompts_dir)
        if kind == "step":
            return self.outputs.get(value) or ""
        if kind == "gcs_latest_text":
            return self.legacy.download_latest_text_file_from_gcs(value)
        if kind == "gcs_file":
            return self.legacy.download_mp3_file_from_gcs(value)
        return self.legacy.download_latest_mp3_from_gcs(value)

    def run_recent_episodes(self, step):
        import requests

        response = requests.get(step["feed_url"], timeout=30)
        response.raise_for_status()
        return format_recent_episodes(response.content, int(step["count"]))

    def run_model(self, step):
        prompt = "\n\n".join(self.resolve(part) for part in step["parts"])
        model, web_search = step["model"], bool(step.get("web_search"))
        print(f"  Model: {model}, Web Search: {web_search}")
        # Same sampling choice as V1; adaptive-thinking Claude models ignore it.
        temperature = 0.8 if web_search else 0.85
        if self.legacy.anthropic_model_uses_opus_adaptive_effort(model):
            temperature = 0.7
        response = self.legacy.call_model(prompt, model, temperature=temperature, web_search=web_search)
        if isinstance(response, bytes):
            response = response.decode("utf-8")
        self.records.append({"step": step["id"], "model": model, "web_search": web_search,
                             "input": prompt, "output": str(response)})
        return str(response)

    def run_save_text(self, step):
        text = self.resolve(step["source"])
        text = self.legacy.force_clean_mojibake(self.legacy.fix_text_encoding(text))
        filename = self.filename(step, "txt", f"v2_{step['id']}")
        link = self.legacy.upload_text_to_gcs(text, f"{step['folder'].rstrip('/')}/{filename}")
        if not link:
            raise RuntimeError(f"Could not save {step['id']} to {step['folder']}.")
        print(f"  Saved: {link}")
        if TITLE_LINE.search(text) and DESCRIPTION_LINE.search(text):
            self.final_description_text = text
            self.final_description_filename = filename
        return text

    def run_voice(self, step):
        legacy = self.legacy
        text = self.resolve(step["source"])
        if not text:
            raise RuntimeError(f"No script text found for {step['id']}.")
        eleven = step["elevenlabs"]
        output = legacy.MP3_OUTPUT_DIR / f"v2_{step['id']}.mp3"
        voice_name = eleven.get("Voice", "ElevenLabs")
        try:
            audio_path = legacy.generate_voice_audio(text, eleven["voice_id"], output, eleven)
        except Exception as error:
            if not legacy.is_elevenlabs_credit_quota_error(str(error), None) and "credit/quota" not in str(error).lower():
                raise
            voice_name = legacy.get_google_chirp3_voice_name_by_id(step.get("google_fallback_voice_id", "1"))
            print(f"  ElevenLabs credit/quota error; using Google voice {voice_name}.")
            output = legacy.MP3_OUTPUT_DIR / f"v2_{step['id']}_google.mp3"
            audio_path = legacy.generate_google_voice_audio(text, voice_name, output)
        if not audio_path:
            raise RuntimeError(f"Voice generation failed for {step['id']}.")
        filename = self.filename(step, "mp3", f"v2_{step['id']}_{voice_name}")
        link = legacy.upload_audio_to_gcs(audio_path, f"{step['folder'].rstrip('/')}/{filename}")
        print(f"  Audio saved: {link}")
        return str(audio_path)

    def run_merge_audio(self, step):
        paths = [self.resolve(part) for part in step["parts"]]
        if not all(paths):
            raise RuntimeError(f"Missing audio for {step['id']}: {paths}")
        merged = self.legacy.merge_multiple_audio_files(
            paths, self.legacy.MP3_OUTPUT_DIR / f"v2_{step['id']}.mp3")
        if not merged:
            raise RuntimeError(f"Audio merge failed for {step['id']}.")
        filename = self.filename(step, "mp3", f"v2_{step['id']}")
        link = self.legacy.upload_audio_to_gcs(merged, f"{step['folder'].rstrip('/')}/{filename}")
        print(f"  Episode saved: {link}")
        self.final_audio_path = merged
        self.final_audio_filename = filename
        title_text = self.outputs.get(step.get("title_from"))
        if not self.final_description_text and title_text and TITLE_LINE.search(title_text):
            self.final_description_text = title_text
        return str(merged)

    def run(self):
        steps = self.workflow["steps"]
        for index, step in enumerate(steps, start=1):
            print(f"[V2] Step {index}/{len(steps)}: {step['id']} ({step['type']})")
            self.outputs[step["id"]] = getattr(self, f"run_{step['type']}")(step)
            preview = str(self.outputs[step["id"]])[:100]
            print(f"  Output (first 100): {preview}")
        self.legacy.LOCAL_ARTIFACTS.write_json("v2_steps.json", self.records)


def load_legacy():
    """Import the V1 module for its helpers; its Google Sheet code only runs as __main__."""
    sys.path.insert(0, str(REPO_ROOT))
    import ai_podcast_pipeline_for_cursor as legacy

    # V1 defines log_error inside its __main__ block; its API helpers call it.
    legacy.log_error = lambda message: print(f"[LOGGED ERROR] {message}")
    return legacy


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate the configuration and exit.")
    parser.add_argument("--no-email", action="store_true", help="Skip the final email.")
    args = parser.parse_args(argv)

    workflow = load_json(WORKFLOW_PATH)
    problems = validate_workflow(workflow, load_json(MODELS_PATH))
    for problem in problems:
        print(f"❌ {problem}")
    if problems:
        return 1
    print(f"✅ Workflow '{workflow['name']}' is valid ({len(workflow['steps'])} steps).")
    for step in workflow["steps"]:
        if step["type"] == "model":
            print(f"   {step['id']}: {step['model']} (web search {'on' if step.get('web_search') else 'off'})")
    if args.check:
        return 0

    legacy = load_legacy()
    runner = Runner(workflow, legacy)
    runner.run()
    if not runner.final_audio_path:
        print("No final episode audio was produced; nothing to email.")
        return 0
    if not runner.final_description_text:
        raise RuntimeError("Episode audio was produced but no title/description text is available.")
    if args.no_email:
        print("Skipping email (--no-email).")
        return 0
    legacy.send_podcast_email(
        runner.final_audio_path,
        runner.final_description_text,
        workflow_id="V2",
        audio_filename=runner.final_audio_filename,
        description_filename=runner.final_description_filename,
    )
    print("Final audio and description sent in one email.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
