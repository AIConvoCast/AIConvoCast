import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from podcast_v2 import run_podcast, update_models

RSS = b"""<rss><channel>
<item><title>Newest &amp; best</title><description>&lt;p&gt;Short one.&lt;/p&gt; Help support us</description></item>
<item><title>Older</title><description>Short two.</description></item>
<item><title>Oldest</title><description>Short three.</description></item>
</channel></rss>"""


class FakeLegacy:
    OPUS47_SCRIPT_TUNING_APPENDIX = "Additional script requirements for this run:\n- keep it tight\n"

    def __init__(self, directory):
        self.MP3_OUTPUT_DIR = Path(directory)
        self.LOCAL_ARTIFACTS = SimpleNamespace(write_json=mock.Mock())
        self.calls = []
        self.uploads = []
        self.saved_text = {}

    def anthropic_model_uses_opus_adaptive_effort(self, model):
        return model.startswith("claude-opus-5")

    def call_model(self, prompt, model, temperature, web_search):
        self.calls.append((prompt, model, temperature, web_search))
        if "P12 text" in prompt:
            return "Title: Opus 5.5 Arrives\n\nDescription: In this episode, we discuss Opus."
        return f"{model} output"

    def fix_text_encoding(self, text):
        return text

    def force_clean_mojibake(self, text):
        return text

    def upload_text_to_gcs(self, text, blob):
        self.saved_text[blob.split("/")[0] + "/"] = text
        self.uploads.append(blob)
        return f"https://storage/{blob}"

    def download_latest_text_file_from_gcs(self, folder):
        return self.saved_text.get(folder)

    def generate_voice_audio(self, text, voice_id, output, config):
        raise RuntimeError("ElevenLabs credit/quota error: quota_exceeded")

    def is_elevenlabs_credit_quota_error(self, message, status):
        return "quota" in message

    def get_google_chirp3_voice_name_by_id(self, voice_id):
        return "Alnilam"

    def generate_google_voice_audio(self, text, voice, output):
        Path(output).write_bytes(b"audio")
        return output

    def upload_audio_to_gcs(self, path, blob):
        self.uploads.append(blob)
        return f"https://storage/{blob}"

    def download_mp3_file_from_gcs(self, blob):
        return self.MP3_OUTPUT_DIR / blob

    def download_latest_mp3_from_gcs(self, folder):
        return self.MP3_OUTPUT_DIR / "latest.wav"

    def merge_multiple_audio_files(self, paths, output):
        self.merged = list(paths)
        return output


class PodcastV2ConfigTests(unittest.TestCase):
    def test_repo_workflow_is_valid_and_uses_opus_5_5(self):
        workflow = run_podcast.load_json(run_podcast.WORKFLOW_PATH)
        models = run_podcast.load_json(run_podcast.MODELS_PATH)
        self.assertEqual(run_podcast.validate_workflow(workflow, models), [])
        claude_steps = {s["id"]: s for s in workflow["steps"] if s.get("model", "").startswith("claude-")}
        self.assertEqual(claude_steps["script"]["model"], "claude-opus-5-5")
        self.assertTrue(claude_steps["script"]["web_search"])
        self.assertEqual(claude_steps["title"]["model"], "claude-opus-5-5")
        self.assertFalse(claude_steps["title"]["web_search"])

    def test_validation_reports_unknown_model_and_bad_references(self):
        workflow = {"steps": [
            {"id": "a", "type": "model", "model": "claude-opus-9", "parts": ["prompt:999", "step:later"]},
        ]}
        problems = run_podcast.validate_workflow(workflow, {"models": []})
        self.assertEqual(len(problems), 3)

    def test_validation_rejects_web_search_on_unsupported_model(self):
        workflow = {"steps": [{"id": "a", "type": "model", "model": "m", "web_search": True, "parts": []}]}
        models = {"models": [{"name": "m", "web_search": False, "available": True}]}
        self.assertIn("does not support web search", run_podcast.validate_workflow(workflow, models)[0])

    def test_recent_episodes_match_v1_format(self):
        text = run_podcast.format_recent_episodes(RSS, 2)
        self.assertEqual(text, "Title: Newest & best\nDescription Short: Short one.\n\n"
                               "Title: Older\nDescription Short: Short two.")


class PodcastV2RunnerTests(unittest.TestCase):
    def test_full_workflow_without_google_sheet(self):
        workflow = copy.deepcopy(run_podcast.load_json(run_podcast.WORKFLOW_PATH))
        with tempfile.TemporaryDirectory() as directory:
            prompts = Path(directory) / "prompts"
            prompts.mkdir()
            for pid in ("4", "8", "10", "12"):
                (prompts / f"P{pid}.txt").write_text(f"P{pid} text\n")
            legacy = FakeLegacy(directory)
            runner = run_podcast.Runner(workflow, legacy, prompts_dir=prompts)
            with mock.patch("requests.get") as get:
                get.return_value = SimpleNamespace(content=RSS, raise_for_status=lambda: None)
                runner.run()

        research, script, title = legacy.calls
        self.assertEqual(research[1:], ("gpt-6-astra", 0.8, True))
        self.assertTrue(research[0].startswith("P10 text\n\nP8 text\n\nTitle: Newest & best"))
        self.assertEqual(script[1:], ("claude-opus-5-5", 0.7, True))
        self.assertEqual(script[0], "P4 text\n\nAdditional script requirements for this run:\n"
                                    "- keep it tight\n\ngpt-6-astra output")
        self.assertEqual(title[1:], ("claude-opus-5-5", 0.7, False))
        self.assertTrue(title[0].startswith("P12 text\n\nclaude-opus-5-5 output\n\nAdditional"))

        folders = [blob.split("/")[0] for blob in legacy.uploads]
        self.assertEqual(folders, ["descriptions", "scripts", "eleven-labs", "podcasts"])
        self.assertTrue(all("Opus_55_Arrives" in blob for blob in legacy.uploads))
        self.assertEqual([Path(p).name for p in legacy.merged], ["Intro.mp3", "latest.wav", "Outro.mp3"])
        self.assertIn("Description:", runner.final_description_text)
        self.assertTrue(runner.final_audio_filename.endswith("_Opus_55_Arrives.mp3"))


class UpdateModelsV2Tests(unittest.TestCase):
    def test_merge_adds_new_models_and_marks_missing_ones(self):
        existing = {"models": [
            {"name": "claude-opus-5", "provider": "anthropic", "web_search": True, "available": True},
            {"name": "gpt-old", "provider": "openai", "web_search": False, "available": True},
            {"name": "gemini-x", "provider": "google", "web_search": False, "available": True},
        ]}
        fetched = [
            {"id": "claude-opus-5", "provider": "anthropic", "web_search": True},
            {"id": "claude-opus-5-5", "provider": "anthropic", "web_search": True},
            {"id": "gpt-new", "provider": "openai", "web_search": True},
        ]
        registry, added, removed = update_models.merge_models(existing, fetched, "now")
        self.assertEqual(added, ["claude-opus-5-5", "gpt-new"])
        self.assertEqual(removed, ["gpt-old"])
        by_name = {m["name"]: m for m in registry["models"]}
        self.assertTrue(by_name["claude-opus-5-5"]["web_search"])
        self.assertFalse(by_name["gpt-old"]["available"])
        # Google returned nothing, so its models are left alone.
        self.assertTrue(by_name["gemini-x"]["available"])


if __name__ == "__main__":
    unittest.main()
