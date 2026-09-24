import copy
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from podcast_v2 import run_podcast, sync_from_sheet, update_models

RSS = b"""<rss><channel>
<item><title>Newest &amp; best</title><description>&lt;p&gt;Short one.&lt;/p&gt; Help support us</description></item>
<item><title>Older</title><description>Short two.</description></item>
<item><title>Oldest</title><description>Short three.</description></item>
</channel></rss>"""


TUNING = "Additional script requirements for this run:\n- keep it tight\n"


class FakeLegacy:

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


class FakeAudio:
    def __init__(self):
        self.polished = []
        self.merged = None

    def polish_speech(self, audio_path, master_path=None):
        self.polished.append(Path(audio_path).name)
        return audio_path

    def merge(self, paths, output):
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
            (prompts / "script_tuning.txt").write_text(TUNING)
            legacy = FakeLegacy(directory)
            audio = FakeAudio()
            runner = run_podcast.Runner(workflow, legacy, prompts_dir=prompts, audio=audio)
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
        self.assertEqual([Path(p).name for p in audio.merged], ["Intro.mp3", "latest.wav", "Outro.mp3"])
        # Only the Google fallback narration is loudness-normalized.
        self.assertEqual(audio.polished, ["v2_narration_google.mp3"])
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


class PodcastV2GuardTests(unittest.TestCase):
    def test_empty_feed_stops_the_run(self):
        runner = run_podcast.Runner({"steps": []}, FakeLegacy(tempfile.gettempdir()))
        step = {"id": "recent_episodes", "count": 15, "feed_url": "https://feed"}
        with mock.patch("requests.get") as get:
            get.return_value = SimpleNamespace(content=b"<rss><channel></channel></rss>",
                                               raise_for_status=lambda: None)
            with self.assertRaises(RuntimeError):
                runner.run_recent_episodes(step)

    def test_script_tuning_is_not_added_twice(self):
        legacy = FakeLegacy(tempfile.gettempdir())
        runner = run_podcast.Runner({"steps": []}, legacy)
        runner.outputs["research"] = "brief"
        with tempfile.TemporaryDirectory() as directory:
            appendix = TUNING.strip()
            Path(directory, "P4.txt").write_text(f"P4 text\n\n{appendix}\n")
            Path(directory, "script_tuning.txt").write_text(TUNING)
            runner.prompts_dir = Path(directory)
            runner.run_model({"id": "script", "model": "claude-opus-5-5", "web_search": True,
                              "parts": ["prompt:4", "script_tuning", "step:research"]})
        self.assertEqual(legacy.calls[0][0].count("Additional script requirements"), 1)


class SyncFromSheetTests(unittest.TestCase):
    def test_sync_copies_active_workflow_prompts_and_eleven_settings(self):
        tabs = {
            "Workflows": [
                {"Workflow ID": 47, "Workflow Code": "PPU,PPL15,P10&P8&R2M221,P4&R3M223,P12&R4M220,"
                                                     "R5SL10T5,R4SL7T5,L8E1SL4T5,L1&L9&L2SL3T5", "Active": "Y"},
                {"Workflow ID": 23, "Workflow Code": "P1M1", "Active": "N"},
            ],
            "Prompts": [
                {"Prompt ID": 1, "Prompt Name": "Old", "Prompt Description": "unused"},
                {"Prompt ID": 4, "Prompt Name": "Script", "Prompt Description":
                    "Script prompt\n\nAdditional script requirements for this run:\n- a\n- b"},
                {"Prompt ID": 8, "Prompt Name": "Prior", "Prompt Description": "Prior coverage"},
                {"Prompt ID": 10, "Prompt Name": "Search", "Prompt Description": "Search"},
                {"Prompt ID": 12, "Prompt Name": "Title", "Prompt Description": "Title prompt"},
            ],
            "Models": [{"Model ID": 223, "Model Name": "claude-opus-5"}, {"Model ID": 1, "Model Name": "x"}],
            "Locations": [{"Location ID": 8, "Location": "scripts/"}, {"Location ID": 5, "Location": "p/"}],
            "Eleven": [{"Eleven ID": 1, "Voice": "Liam", "Model": "eleven_v3", "Stability": 0.4,
                        "Similarity Boost": 0.7, "Style": 0, "Speed": 1.1}],
        }
        workflow = run_podcast.load_json(run_podcast.WORKFLOW_PATH)
        prompts, updated, snapshot = sync_from_sheet.build_sync(tabs, workflow)
        self.assertEqual(sorted(prompts, key=int), ["4", "8", "10", "12"])
        self.assertEqual(prompts["4"], "Script prompt\n")
        voice = next(s for s in updated["steps"] if s["type"] == "voice")
        self.assertEqual(voice["elevenlabs"]["Stability"], 0.4)
        self.assertEqual(voice["elevenlabs"]["voice_id"], "TX3LPaxmHKxFdv7VOQHJ")
        self.assertEqual([m["Model ID"] for m in snapshot["models"]], [223])
        self.assertEqual([l["Location ID"] for l in snapshot["locations"]], [8])
        # Model choices in workflow.json are never taken from the sheet.
        self.assertEqual(updated["steps"][2]["model"], "claude-opus-5-5")

    def test_sync_requires_an_active_workflow(self):
        with self.assertRaises(RuntimeError):
            sync_from_sheet.build_sync({"Workflows": [], "Prompts": []}, {"steps": []})



class AudioFallbackTests(unittest.TestCase):
    def test_merge_falls_back_to_standard_merge(self):
        legacy = FakeLegacy(tempfile.gettempdir())
        broken = SimpleNamespace(merge=mock.Mock(side_effect=RuntimeError("no ffmpeg")))
        runner = run_podcast.Runner({"steps": []}, legacy, audio=broken)
        runner.run_merge_audio({"id": "episode", "parts": ["gcs_file:Intro.mp3"], "folder": "podcasts/"})
        self.assertEqual([Path(p).name for p in legacy.merged], ["Intro.mp3"])


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg is not installed")
class AudioPolishTests(unittest.TestCase):
    def setUp(self):
        from pydub.generators import Sine
        from podcast_v2 import audio_polish
        self.polish = audio_polish
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        # Google-style 24 kHz mono tone, quiet, and a 44.1 kHz stereo intro.
        Sine(9000, sample_rate=24000).to_audio_segment(duration=1500).apply_gain(-30).export(
            self.dir / "speech.wav", format="wav")
        Sine(440, sample_rate=44100).to_audio_segment(duration=300).set_channels(2).export(
            self.dir / "intro.wav", format="wav")

    def test_join_uses_clean_resampling(self):
        import numpy as np
        combined = self.polish.join([self.dir / "intro.wav", self.dir / "speech.wav"], self.dir)
        self.assertEqual((combined.frame_rate, combined.channels), (44100, 2))
        samples = np.array(combined.get_array_of_samples(), dtype=float)[::2][int(0.5 * 44100):]
        spectrum = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
        freqs = np.fft.rfftfreq(len(samples), 1 / 44100)
        tone = spectrum[np.abs(freqs - 9000) < 50].max()
        image = spectrum[np.abs(freqs - 15000) < 50].max()
        # Linear interpolation leaves an image about 9 dB down; soxr removes it.
        self.assertLess(20 * np.log10(image / tone), -60)

    def test_speech_is_normalized_to_podcast_loudness(self):
        out = self.polish.normalize_loudness(self.dir / "speech.wav", self.dir / "loud.wav")
        self.assertEqual(self.polish.probe(out), (24000, 1))
        report = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostdin", "-i", str(out), "-af", "loudnorm=print_format=json",
             "-f", "null", "-"], capture_output=True, text=True, check=True).stderr
        measured = float(json.loads(re.findall(r"\{[^{}]*\}", report)[-1])["input_i"])
        self.assertAlmostEqual(measured, self.polish.TARGET_LUFS, delta=1.5)


if __name__ == "__main__":
    unittest.main()
