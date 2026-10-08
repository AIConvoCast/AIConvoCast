import contextlib
import ast
import copy
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from podcast_v2 import eleven_v4, run_podcast, sync_from_sheet, update_models

_SUMMARY_ENV = mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": ""})


def setUpModule():
    # These tests run inside the real V2 Action; keep their fake episodes off its run page.
    _SUMMARY_ENV.start()


def tearDownModule():
    _SUMMARY_ENV.stop()

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
        self.ELEVENLABS_API_KEY = "test-key"
        self.split_text_into_chunks = mock.Mock(side_effect=lambda text, **kwargs: [text])
        self.retry_transient = lambda operation, **kwargs: operation()
        self.requests = SimpleNamespace(post=mock.Mock(return_value=SimpleNamespace(
            status_code=402, text="quota_exceeded", content=b"", close=lambda: None,
            raise_for_status=lambda: None,
        )))

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
            research_calls = []

            def fake_research(client, prompt, **options):
                research_calls.append((prompt, options))
                return "gpt-6.1-sol output"

            legacy.client = object()
            legacy.LOCAL_ARTIFACTS.directory = Path(directory)
            runner = run_podcast.Runner(workflow, legacy, prompts_dir=prompts, audio=audio, research=fake_research)
            with mock.patch("requests.get") as get:
                get.return_value = SimpleNamespace(content=RSS, raise_for_status=lambda: None)
                runner.run()

        (research_prompt, options), = research_calls
        self.assertEqual((options["search_model"], options["use_astra"]), ("gpt-6.1-sol", False))
        self.assertIsNone(options["instructions"])  # daily research keeps the default instructions
        self.assertTrue(research_prompt.startswith("P10 text\n\nP8 text\n\nTitle: Newest & best"))
        script, title = legacy.calls
        self.assertEqual(script[1:], ("claude-opus-5-5", 0.7, True))
        self.assertTrue(script[0].startswith("P4 text\n\nAdditional script requirements for this run:\n"
                                             "- keep it tight\n\ngpt-6.1-sol output\n\nRecent episodes"))
        # The script writer sees prior coverage so follow-ups add only new details.
        self.assertTrue(script[0].endswith("Title: Oldest\nDescription Short: Short three."))
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


class OpenAIKeyTypeTests(unittest.TestCase):
    def test_key_types_come_from_the_prefix_only(self):
        from podcast_v2.update_models import openai_key_type

        self.assertTrue(openai_key_type("sk-proj-abc").startswith("project key"))
        self.assertTrue(openai_key_type("sk-svcacct-abc").startswith("service account key"))
        self.assertTrue(openai_key_type("sk-abc123").startswith("legacy user key"))
        self.assertEqual(openai_key_type(""), "missing or unrecognized")
        self.assertNotIn("abc", openai_key_type("sk-proj-abc"))


class PodcastV2GuardTests(unittest.TestCase):
    def test_empty_feed_stops_the_run(self):
        runner = run_podcast.Runner({"steps": []}, FakeLegacy(tempfile.gettempdir()))
        step = {"id": "recent_episodes", "count": 15, "feed_url": "https://feed"}
        with mock.patch("requests.get") as get:
            get.return_value = SimpleNamespace(content=b"<rss><channel></channel></rss>",
                                               raise_for_status=lambda: None)
            with self.assertRaises(RuntimeError):
                runner.run_recent_episodes(step)

    def test_feed_is_sorted_by_publish_date_and_cache_busted(self):
        feed = b"""<rss><channel>
<item><title>Older</title><description>Two.</description><pubDate>Tue, 29 Sep 2026 09:00:00 GMT</pubDate></item>
<item><title>Newest</title><description>One.</description><pubDate>Thu, 01 Oct 2026 09:00:00 GMT</pubDate></item>
</channel></rss>"""
        stale = b"""<rss><channel>
<item><title>Older</title><description>Two.</description><pubDate>Tue, 29 Sep 2026 09:00:00 GMT</pubDate></item>
</channel></rss>"""
        runner = run_podcast.Runner({"steps": []}, FakeLegacy(tempfile.gettempdir()))
        with mock.patch("requests.get") as get:
            get.side_effect = [SimpleNamespace(content=stale, raise_for_status=lambda: None),
                               SimpleNamespace(content=feed, raise_for_status=lambda: None)]
            text = runner.run_recent_episodes({"count": 15, "feed_url": "https://feed"})
        self.assertTrue(text.startswith("Title: Newest\n"))
        self.assertIn("nocache=", get.call_args.args[0])
        self.assertEqual(get.call_args.kwargs["headers"]["Cache-Control"], "no-cache")

    def test_generated_episode_missing_from_feed_counts_as_covered(self):
        with tempfile.TemporaryDirectory() as directory:
            legacy = FakeLegacy(directory)
            files = {
                "descriptions/20260930_200500_FTC_Probes_OpenAI.txt":
                    "Title:\nFTC Probes OpenAI\n\nDescription:\nThe FTC story. Help support us",
                "descriptions/20260929_200500_Already_In_Feed.txt":
                    "Title:\nAlready In Feed\n\nDescription:\nOld.",
                "descriptions/20261001_150000_Made_An_Hour_Ago.txt":
                    "Title:\nMade An Hour Ago\n\nDescription:\nToo new.",
            }
            legacy.list_files_in_gcs_folder = lambda folder: list(files)

            def download(name, local):
                Path(local).write_text(files[name], encoding="utf-8")
                return local
            legacy.download_file_from_gcs = download
            runner = run_podcast.Runner({"steps": []}, legacy)
            feed = [{"title": "Already in feed", "short": "", "published": None}]
            now = run_podcast.datetime(2026, 10, 1, 16, tzinfo=run_podcast.timezone.utc)
            missing = runner.generated_missing_from_feed(feed, now=now)
        self.assertEqual([(e["title"], e["short"]) for e in missing], [("FTC Probes OpenAI", "The FTC story.")])

    def test_gcs_failure_does_not_stop_the_run(self):
        legacy = FakeLegacy(tempfile.gettempdir())
        legacy.list_files_in_gcs_folder = mock.Mock(side_effect=RuntimeError("no creds"))
        runner = run_podcast.Runner({"steps": []}, legacy)
        self.assertEqual(runner.generated_missing_from_feed([]), [])

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




class TopicEpisodeTests(unittest.TestCase):
    def test_repo_topic_workflow_is_valid(self):
        workflow = run_podcast.load_json(run_podcast.TOPIC_WORKFLOW_PATH)
        models = run_podcast.load_json(run_podcast.MODELS_PATH)
        self.assertEqual(run_podcast.validate_workflow(workflow, models), [])
        by_id = {s["id"]: s for s in workflow["steps"]}
        self.assertEqual(by_id["script"]["model"], "claude-opus-5-5")
        self.assertIn("topic", by_id["research"]["parts"])
        self.assertNotIn("prompt:10", by_id["research"]["parts"])

    def test_topic_episode_uses_topic_research_and_single_topic_script(self):
        workflow = copy.deepcopy(run_podcast.load_json(run_podcast.TOPIC_WORKFLOW_PATH))
        research_calls = []

        def fake_research(client, prompt, *, use_astra, output_directory, instructions,
                          editor_instructions, search_model):
            research_calls.append((prompt, use_astra, instructions, editor_instructions, search_model))
            return "topic brief"

        with tempfile.TemporaryDirectory() as directory:
            prompts = Path(directory) / "prompts"
            prompts.mkdir()
            for name in ("P12", "P20", "P21"):
                (prompts / f"{name}.txt").write_text(f"{name} text\n")
            (prompts / "topic_research_system.txt").write_text("TOPIC RESEARCH")
            (prompts / "topic_editor_system.txt").write_text("TOPIC EDITOR")
            legacy = FakeLegacy(directory)
            legacy.client = object()
            legacy.LOCAL_ARTIFACTS.directory = Path(directory)
            audio = FakeAudio()
            runner = run_podcast.Runner(workflow, legacy, prompts_dir=prompts, audio=audio,
                                        topic="Meta Muse new AI tool and adoption", research=fake_research)
            with mock.patch("requests.get") as get:
                get.return_value = SimpleNamespace(content=RSS, raise_for_status=lambda: None)
                runner.run()

        (prompt, use_astra, instructions, editor, search_model), = research_calls
        self.assertEqual((use_astra, search_model), (False, "gpt-6.1-sol"))
        self.assertEqual((instructions, editor), ("TOPIC RESEARCH", "TOPIC EDITOR"))
        self.assertIn("Topic for this episode:\n\nMeta Muse new AI tool and adoption", prompt)
        self.assertIn("Title: Newest & best", prompt)  # prior episodes still inform the research
        (script, *script_settings), (title, *_) = legacy.calls
        self.assertEqual(script_settings, ["claude-opus-5-5", 0.7, True])
        self.assertTrue(script.startswith("P21 text\n\nTopic for this episode:\n\nMeta Muse"))
        self.assertTrue(script.endswith("topic brief"))
        self.assertNotIn("Additional script requirements", script + title)
        self.assertEqual([b.split("/")[0] for b in legacy.uploads],
                         ["descriptions", "scripts", "eleven-labs", "podcasts"])
        self.assertIn("Description:", runner.final_description_text)

    def test_topic_workflow_without_topic_stops(self):
        runner = run_podcast.Runner({"steps": []}, FakeLegacy(tempfile.gettempdir()))
        with self.assertRaises(RuntimeError):
            runner.resolve("topic")

    def test_run_summary_lists_description_and_model_outputs(self):
        workflow = {"steps": [{"id": "script", "type": "model", "model": "claude-opus-5-5"},
                              {"id": "save", "type": "save_text"}]}
        runner = run_podcast.Runner(workflow, FakeLegacy(tempfile.gettempdir()), topic="Meta Muse")
        runner.outputs = {"script": "Today we will be...", "save": "ignored"}
        runner.final_description_text = "Title:\nMuse\n\nDescription:\nAbout Muse"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.md"
            with contextlib.redirect_stdout(io.StringIO()) as log:
                runner.write_summary(path)
            summary = path.read_text()
        self.assertIn("::group::Episode text", log.getvalue())
        self.assertIn("**Custom topic:** Meta Muse", summary)
        self.assertIn("Description:\nAbout Muse", summary)
        self.assertIn("script (claude-opus-5-5): 19 characters", summary)
        self.assertNotIn("ignored", summary)

    def test_research_only_run_stops_after_research(self):
        workflow = copy.deepcopy(run_podcast.load_json(run_podcast.WORKFLOW_PATH))
        with tempfile.TemporaryDirectory() as directory:
            prompts = Path(directory) / "prompts"
            prompts.mkdir()
            for pid in ("4", "8", "10", "12"):
                (prompts / f"P{pid}.txt").write_text(f"P{pid} text\n")
            legacy = FakeLegacy(directory)
            legacy.client = object()
            legacy.LOCAL_ARTIFACTS.directory = Path(directory)
            audio = FakeAudio()
            runner = run_podcast.Runner(workflow, legacy, prompts_dir=prompts, audio=audio,
                                        research=lambda client, prompt, **options: "brief")
            with mock.patch("requests.get") as get:
                get.return_value = SimpleNamespace(content=RSS, raise_for_status=lambda: None)
                runner.run(stop_after="research")
        self.assertEqual(list(runner.outputs), ["recent_episodes", "research"])
        self.assertEqual((legacy.calls, legacy.uploads, audio.merged), ([], [], None))

    def test_script_preview_stops_before_uploads_and_audio(self):
        for path in (run_podcast.WORKFLOW_PATH, run_podcast.TOPIC_WORKFLOW_PATH):
            workflow = copy.deepcopy(run_podcast.load_json(path))
            ids = [step["id"] for step in workflow["steps"]]
            # Everything after the title step saves, voices or merges, so a preview must stop there.
            after = {step["type"] for step in workflow["steps"][ids.index("title") + 1:]}
            self.assertEqual(after, {"save_text", "voice", "merge_audio"})
            self.assertTrue(all(step["type"] in ("recent_episodes", "model")
                                for step in workflow["steps"][:ids.index("title") + 1]))

    def test_text_parts_are_literal(self):
        runner = run_podcast.Runner({"steps": []}, FakeLegacy(tempfile.gettempdir()))
        self.assertEqual(runner.resolve("text:Topic for this episode:"), "Topic for this episode:")


class AudioFallbackTests(unittest.TestCase):
    def test_merge_falls_back_to_standard_merge(self):
        legacy = FakeLegacy(tempfile.gettempdir())
        broken = SimpleNamespace(merge=mock.Mock(side_effect=RuntimeError("no ffmpeg")))
        runner = run_podcast.Runner({"steps": []}, legacy, audio=broken)
        runner.run_merge_audio({"id": "episode", "parts": ["gcs_file:Intro.mp3"], "folder": "podcasts/"})
        self.assertEqual([Path(p).name for p in legacy.merged], ["Intro.mp3"])


class ElevenV4Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.legacy = FakeLegacy(self.temp.name)
        # Exercise the real sentence/word-aware splitter without initializing
        # the legacy publishing clients or reading credentials.
        source = Path(__file__).with_name("ai_podcast_pipeline_for_cursor.py")
        node = next(n for n in ast.parse(source.read_text()).body
                    if isinstance(n, ast.FunctionDef) and n.name == "split_text_into_chunks")
        namespace = {"ELEVENLABS_CHUNK_MAX_CHARS": 2900}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
        self.legacy.split_text_into_chunks = namespace["split_text_into_chunks"]
        self.config = next(s["elevenlabs"] for s in run_podcast.load_json(run_podcast.WORKFLOW_PATH)["steps"]
                           if s["type"] == "voice")
        self.output = Path(self.temp.name) / "narration.mp3"
        self.responses = []

        def respond(*args, **kwargs):
            response = mock.Mock(status_code=200, text="", content=b"audio")
            self.responses.append(response)
            return response

        self.legacy.requests.post.side_effect = respond
        self.legacy.merge_multiple_audio_files = mock.Mock(side_effect=self.merge)
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)

    def merge(self, paths, output):
        Path(output).write_bytes(b"".join(Path(p).read_bytes() for p in paths))
        return output

    def generate(self, text="A short script.", config=None):
        return eleven_v4.generate_voice_audio(text, self.config["voice_id"], self.output,
                                              config or self.config, self.legacy)

    def test_both_workflows_use_v4_and_the_existing_voice(self):
        for path in (run_podcast.WORKFLOW_PATH, run_podcast.TOPIC_WORKFLOW_PATH):
            config = next(s["elevenlabs"] for s in run_podcast.load_json(path)["steps"] if s["type"] == "voice")
            self.assertEqual(config["Model"], "eleven_v4")
            self.assertEqual(config["voice_id"], "TX3LPaxmHKxFdv7VOQHJ")
            self.assertNotIn("Speed", config)
            self.assertNotIn("Style", config)

    def test_dialogue_request_keeps_voice_and_supported_settings_only(self):
        config = dict(self.config, Speed=1.06, Style=0.5)
        self.assertEqual(self.generate(config=config), self.output)
        call = self.legacy.requests.post.call_args
        self.assertEqual(call.args, ("https://api.elevenlabs.io/v1/text-to-dialogue",))
        self.assertEqual(call.kwargs["json"], {
            "model_id": "eleven_v4", "inputs": [{"text": "A short script.", "voice_id": self.config["voice_id"]}],
            "settings": {"stability": 0.39, "similarity": 0.7},
        })
        self.assertEqual(call.kwargs["params"], {"output_format": "mp3_44100_128"})
        self.assertEqual(call.kwargs["headers"]["xi-api-key"], "test-key")
        self.assertEqual(self.output.read_bytes(), b"audio")
        self.legacy.merge_multiple_audio_files.assert_not_called()
        self.responses[0].close.assert_called_once()

    def test_long_script_keeps_words_order_and_bounded_continuity(self):
        text = " ".join(f"Story {i} brings a new development." for i in range(230))
        self.generate(text)
        payloads = [c.kwargs["json"] for c in self.legacy.requests.post.call_args_list]
        chunks = [p["inputs"][0]["text"] for p in payloads]
        self.assertGreater(len(chunks), 3)
        self.assertEqual(" ".join(chunks), text)
        self.assertTrue(all(len(c) <= 2000 for c in chunks))
        for index, payload in enumerate(payloads):
            if index:
                self.assertEqual(payload["previous_text"], chunks[index - 1][-100:])
            else:
                self.assertNotIn("previous_text", payload)
            if index + 1 < len(chunks):
                self.assertEqual(payload["future_text"], chunks[index + 1][:100])
            else:
                self.assertNotIn("future_text", payload)
            self.assertEqual(payload["inputs"][0]["voice_id"], self.config["voice_id"])
        self.assertEqual(self.output.read_bytes(), b"audio" * len(chunks))
        self.assertFalse(list(Path(self.temp.name).glob("eleven_v4_*")))

    def test_sentence_longer_than_limit_splits_at_words(self):
        text = "word " * 1000
        self.generate(text)
        chunks = [c.kwargs["json"]["inputs"][0]["text"] for c in self.legacy.requests.post.call_args_list]
        self.assertEqual(" ".join(chunks).split(), text.split())
        self.assertTrue(all(len(c) <= 2000 for c in chunks))

    def test_failed_later_chunk_leaves_no_partial_output(self):
        ok = mock.Mock(status_code=200, text="", content=b"audio")
        failed = mock.Mock(status_code=422, text="voice unavailable", content=b"")
        failed.raise_for_status.side_effect = RuntimeError("voice unavailable")
        self.legacy.requests.post.side_effect = [ok, failed]
        with self.assertRaisesRegex(RuntimeError, "voice unavailable"):
            self.generate("A full sentence. " * 400)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(Path(self.temp.name).glob("eleven_v4_*")))
        self.legacy.merge_multiple_audio_files.assert_not_called()
        failed.close.assert_called_once()

    def test_empty_audio_is_rejected_before_upload(self):
        self.legacy.requests.post.side_effect = None
        self.legacy.requests.post.return_value = mock.Mock(status_code=200, content=b"")
        with self.assertRaisesRegex(RuntimeError, "empty audio"):
            self.generate()
        self.assertFalse(self.output.exists())

    def test_invalid_setting_stops_before_paid_request(self):
        with self.assertRaises(ValueError):
            self.generate(config=dict(self.config, Stability=float("nan")))
        self.legacy.requests.post.assert_not_called()

    def test_v4_quota_error_still_uses_google_fallback(self):
        self.legacy.requests.post.side_effect = None
        self.legacy.requests.post.return_value = mock.Mock(status_code=402, text="quota_exceeded")
        audio = FakeAudio()
        runner = run_podcast.Runner({"steps": []}, self.legacy, audio=audio)
        step = next(s for s in run_podcast.load_json(run_podcast.WORKFLOW_PATH)["steps"] if s["type"] == "voice")
        with mock.patch.object(runner, "resolve", return_value="A short script."):
            result = runner.run_voice(step)
        self.assertTrue(result.endswith("v2_narration_google.mp3"))
        self.assertEqual(audio.polished, ["v2_narration_google.mp3"])
        self.assertEqual(len(self.legacy.uploads), 1)

    def test_v4_success_is_uploaded_without_changing_voice(self):
        runner = run_podcast.Runner({"steps": []}, self.legacy, audio=FakeAudio())
        step = next(s for s in run_podcast.load_json(run_podcast.WORKFLOW_PATH)["steps"] if s["type"] == "voice")
        with mock.patch.object(runner, "resolve", return_value="A short script."), \
                mock.patch.object(self.legacy, "generate_voice_audio") as old_tts:
            result = runner.run_voice(step)
        old_tts.assert_not_called()
        self.assertTrue(result.endswith("v2_narration.mp3"))
        self.assertEqual(len(self.legacy.uploads), 1)

    def test_explicit_v3_keeps_existing_tts_path(self):
        runner = run_podcast.Runner({"steps": []}, self.legacy, audio=FakeAudio())
        step = copy.deepcopy(next(s for s in run_podcast.load_json(run_podcast.WORKFLOW_PATH)["steps"]
                                  if s["type"] == "voice"))
        step["elevenlabs"]["Model"] = "eleven_v3"
        with mock.patch.object(runner, "resolve", return_value="A short script."), \
                mock.patch.object(self.legacy, "generate_voice_audio", return_value=self.output) as old_tts:
            runner.run_voice(step)
        old_tts.assert_called_once()
        self.legacy.requests.post.assert_not_called()

    def test_v4_api_error_retries_the_same_voice_on_v3(self):
        failed = mock.Mock(status_code=422, text="unsupported parameter", content=b"")
        failed.raise_for_status.side_effect = RuntimeError("422 unsupported parameter")
        self.legacy.requests.post.side_effect = None
        self.legacy.requests.post.return_value = failed
        runner = run_podcast.Runner({"steps": []}, self.legacy, audio=FakeAudio())
        step = next(s for s in run_podcast.load_json(run_podcast.WORKFLOW_PATH)["steps"] if s["type"] == "voice")
        with mock.patch.object(runner, "resolve", return_value="A short script."), \
                mock.patch.object(self.legacy, "generate_voice_audio", return_value=self.output, create=True) as v3:
            result = runner.run_voice(step)
        self.assertEqual(result, str(self.output))
        config = v3.call_args.args[3]
        self.assertEqual((config["Model"], config["voice_id"], config["Stability"]),
                         ("eleven_v3", "TX3LPaxmHKxFdv7VOQHJ", 0.39))
        self.assertIn("eleven_v3 (fallback", runner.narration)
        self.assertEqual(len(self.legacy.uploads), 1)

    def test_v4_quota_error_skips_v3_and_uses_google(self):
        self.legacy.requests.post.side_effect = None
        self.legacy.requests.post.return_value = mock.Mock(status_code=402, text="quota_exceeded")
        runner = run_podcast.Runner({"steps": []}, self.legacy, audio=FakeAudio())
        step = next(s for s in run_podcast.load_json(run_podcast.WORKFLOW_PATH)["steps"] if s["type"] == "voice")
        with mock.patch.object(runner, "resolve", return_value="A short script."), \
                mock.patch.object(self.legacy, "generate_voice_audio", create=True) as v3:
            runner.run_voice(step)
        v3.assert_not_called()
        self.assertTrue(runner.narration.startswith("Google Alnilam"))

    def test_voice_sample_uses_v4_without_fallback_or_upload(self):
        sample = Path(self.temp.name) / "sample.txt"
        sample.write_text("A short sample.")
        workflow = run_podcast.load_json(run_podcast.WORKFLOW_PATH)
        path = run_podcast.voice_sample(workflow, self.legacy, text_path=sample)
        self.assertEqual(Path(path).name, "voice_sample_eleven_v4.mp3")
        self.assertEqual(self.legacy.requests.post.call_args.kwargs["json"]["model_id"], "eleven_v4")
        self.assertEqual(self.legacy.uploads, [])
        failed = mock.Mock(status_code=500, text="boom", content=b"")
        failed.raise_for_status.side_effect = RuntimeError("500 boom")
        self.legacy.requests.post.side_effect = None
        self.legacy.requests.post.return_value = failed
        with mock.patch.object(self.legacy, "generate_voice_audio", create=True) as v3:
            with self.assertRaisesRegex(RuntimeError, "boom"):
                run_podcast.voice_sample(workflow, self.legacy, text_path=sample)
        v3.assert_not_called()

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is not installed")
    def test_measure_loudness_reports_lufs_and_peak(self):
        from podcast_v2 import audio_polish

        tone = Path(self.temp.name) / "tone.wav"
        subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=2", "-af", "volume=-20dB", str(tone)],
                       check=True, capture_output=True)
        stats = audio_polish.measure_loudness(tone)
        self.assertLess(float(stats["input_i"]), -20)
        self.assertLess(float(stats["input_tp"]), -15)

    def test_shipped_voice_sample_needs_two_requests(self):
        text = run_podcast.VOICE_SAMPLE_PATH.read_text(encoding="utf-8").strip()
        self.assertGreater(len(text), eleven_v4.CHUNK_MAX_CHARS)
        self.assertLess(len(text), 2 * eleven_v4.CHUNK_MAX_CHARS)


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
