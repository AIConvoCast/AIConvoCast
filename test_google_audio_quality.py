"""Offline regression tests; never initialize the full publishing workflow."""

import ast
import contextlib
import io
import os
from pathlib import Path
import tempfile
import time
import traceback
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from google.cloud import texttospeech
from pydub import AudioSegment
from pydub.generators import Sine

import audio_mastering
from google_pronunciations import build_google_synthesis_input
from local_artifacts import LocalArtifacts, ReusableAudioCache


def load_pipeline_audio(output_dir):
    # The legacy pipeline initializes unrelated clients and cleans output files
    # on import. Compile its actual audio functions without those side effects.
    source = Path(__file__).with_name("ai_podcast_pipeline_for_cursor.py")
    tree = ast.parse(source.read_text(encoding="utf-8-sig"))
    function_names = {
        "generate_google_voice_audio", "_generate_single_google_chunk",
        "get_google_chirp3_voice_name_by_id", "build_google_chirp3_audio_config",
        "write_google_tts_audio_content", "merge_multiple_audio_files",
        "download_latest_mp3_from_gcs", "download_mp3_file_from_gcs",
        "upload_file_to_gcs", "split_text_into_chunks",
    }
    selected = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in function_names:
            selected.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and (
                target.id.startswith("GOOGLE_CHIRP3_")
                or target.id == "DEFAULT_MP3_EXPORT_BITRATE"
            ) for target in node.targets
        ):
            selected.append(node)
    namespace = dict(
        os=os, io=io, Path=Path, time=time, tempfile=tempfile,
        traceback=traceback, AudioSegment=AudioSegment, texttospeech=texttospeech,
        MP3_OUTPUT_DIR=Path(output_dir), ELEVENLABS_CHUNK_MAX_CHARS=2500,
        GCS_BUCKET_NAME="test-bucket",
        LOCAL_ARTIFACTS=LocalArtifacts(Path(output_dir) / "runs"), GCS_RETRY=None,
        ReusableAudioCache=ReusableAudioCache,
        build_google_synthesis_input=build_google_synthesis_input,
        export_audio=audio_mastering.export_audio,
        load_audio_for_merge=audio_mastering.load_audio_for_merge,
        register_uploaded_audio_master=audio_mastering.register_uploaded_audio_master,
        copy_uploaded_audio_master=audio_mastering.copy_uploaded_audio_master,
    )
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), "exec"), namespace)
    return namespace


class GoogleAudioQualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output_dir = Path(self.temp.name)
        audio_mastering._masters_by_file.clear()
        audio_mastering._masters_by_blob.clear()
        self.api = load_pipeline_audio(self.output_dir)
        self.chunks = [
            Sine(440, sample_rate=24000).to_audio_segment(duration=200).apply_gain(-15),
            Sine(660, sample_rate=24000).to_audio_segment(duration=300).apply_gain(-15),
        ]
        self.api["split_text_into_chunks"] = Mock(return_value=["First sentence.", "Second sentence."])
        responses = []
        for chunk in self.chunks:
            with chunk.export(format="wav") as stream:
                responses.append(SimpleNamespace(audio_content=stream.read()))
        self.client = Mock()
        self.client.synthesize_speech.side_effect = responses
        self.api["google_tts_client"] = self.client
        self.output = self.output_dir / "narration.mp3"
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)

    def generate(self):
        return self.api["generate_google_voice_audio"]("Test narration.", "Alnilam", self.output)

    def read_wav(self, path):
        with path.open("rb") as stream:
            return AudioSegment.from_wav(stream)

    def test_chunks_keep_pcm_and_encode_mp3_once_at_requested_path(self):
        original_export = AudioSegment.export
        formats = []

        def track_export(audio, *args, **kwargs):
            formats.append(kwargs.get("format"))
            return original_export(audio, *args, **kwargs)

        with patch.object(AudioSegment, "export", track_export):
            self.assertEqual(self.generate(), self.output)
        self.assertEqual(formats.count("mp3"), 1)
        expected = self.chunks[0] + self.chunks[1]
        actual = self.read_wav(self.output.with_suffix(".wav"))
        self.assertEqual(actual.raw_data, expected.raw_data)
        self.assertFalse(list(self.output_dir.glob("google_tts_*")))
        for call in self.client.synthesize_speech.call_args_list:
            self.assertEqual(call.kwargs["voice"].name, "en-US-Chirp3-HD-Alnilam")
            self.assertAlmostEqual(call.kwargs["audio_config"].speaking_rate, 1.08)
            self.assertEqual(call.kwargs["audio_config"].audio_encoding, texttospeech.AudioEncoding.LINEAR16)

    def test_single_chunk_keeps_master(self):
        self.api["split_text_into_chunks"].return_value = ["One sentence."]
        self.assertEqual(self.generate(), self.output)
        self.assertEqual(self.read_wav(self.output.with_suffix(".wav")).raw_data, self.chunks[0].raw_data)

    def test_business_pronunciations_apply_to_every_chunk_and_voice(self):
        chunks = ["NVIDIA announced a chip. Nvidia shared more.", "nvidia’s partners use OpenAI and xAI."]
        self.api["split_text_into_chunks"].return_value = chunks
        self.assertEqual(self.api["generate_google_voice_audio"](
            " ".join(chunks), "Achernar", self.output,
        ), self.output)
        calls = self.client.synthesize_speech.call_args_list
        self.assertEqual(len(calls), 2)
        for chunk, call in zip(chunks, calls):
            self.assertEqual(call.kwargs["input"], build_google_synthesis_input(chunk))
            self.assertTrue(call.kwargs["input"].custom_pronunciations.pronunciations)
            self.assertEqual(call.kwargs["voice"].name, "en-US-Chirp3-HD-Achernar")

    def test_audio_config_retry_keeps_business_pronunciations(self):
        self.api["split_text_into_chunks"].return_value = ["NVIDIA’s chips power OpenAI."]
        self.client.synthesize_speech.side_effect = [
            ValueError("invalid argument: volume_gain_db"),
            SimpleNamespace(audio_content=b"test audio"),
        ]
        self.api["write_google_tts_audio_content"] = Mock()
        self.assertEqual(self.generate(), self.output)
        calls = self.client.synthesize_speech.call_args_list
        self.assertEqual(len(calls), 2)
        first_input = calls[0].kwargs["input"]
        self.assertEqual(first_input.custom_pronunciations.pronunciations[0].phrase, "NVIDIA's")
        self.assertEqual(first_input, calls[1].kwargs["input"])
        for call in calls:
            self.assertAlmostEqual(call.kwargs["audio_config"].speaking_rate, 1.08)

    def test_long_sentence_keeps_company_name_whole_at_chunk_boundary(self):
        self.api["split_text_into_chunks"] = load_pipeline_audio(self.output_dir)["split_text_into_chunks"]
        text = "word " * 799 + "NVIDIA's chips power the platform."
        self.assertEqual(self.api["generate_google_voice_audio"](text, "Alnilam", self.output), self.output)
        inputs = [call.kwargs["input"] for call in self.client.synthesize_speech.call_args_list]
        self.assertEqual(len(inputs), 2)
        self.assertEqual(" ".join(item.text for item in inputs), text)
        self.assertTrue(all(len(item.text) <= 4000 for item in inputs))
        self.assertTrue(inputs[1].text.startswith("NVIDIA's"))
        self.assertEqual(inputs[1].custom_pronunciations.pronunciations[0].pronunciation, "ɛnˈvɪdiəz")

    def test_google_word_splitting_handles_whitespace_and_oversized_tokens(self):
        split = load_pipeline_audio(self.output_dir)["split_text_into_chunks"]
        for separator in (" ", "\n", "\t"):
            with self.subTest(separator=separator):
                self.assertEqual(split(f"abc{separator}NVIDIA", max_length=7, preserve_words=True),
                                 ["abc", "NVIDIA"])
        self.assertEqual(split("abcdefghij", max_length=4, preserve_words=True), ["abcd", "efgh", "ij"])
        self.assertEqual(split("abc NVIDIA", max_length=7), ["abc NVI", "DIA"])

    def test_episode_merge_uses_master_after_uploaded_mp3_is_deleted(self):
        self.generate()
        blob_name = "narration/episode.mp3"
        bucket = Mock()
        self.api["get_gcs_client"] = Mock(return_value=SimpleNamespace(bucket=Mock(return_value=bucket)))
        self.api["upload_file_to_gcs"](self.output, blob_name)
        self.output.unlink()
        self.api["get_latest_file_in_gcs_folder"] = Mock(return_value=blob_name)
        self.api["download_file_from_gcs"] = Mock(side_effect=AssertionError("Should use local master"))
        local = self.api["download_latest_mp3_from_gcs"]("narration/")
        self.assertEqual(local.suffix, ".wav")
        intro = self.output_dir / "intro.wav"
        audio_mastering.export_audio(self.chunks[1], intro)
        final = self.output_dir / "episode.mp3"
        self.assertEqual(self.api["merge_multiple_audio_files"]([intro, local], final), final)
        expected = self.chunks[1] + self.chunks[0] + self.chunks[1]
        self.assertEqual(self.read_wav(final.with_suffix(".wav")).raw_data, expected.raw_data)
        local.unlink()
        self.assertTrue(self.output.with_suffix(".wav").is_file())

    def test_uncached_mp3_still_downloads(self):
        self.api["get_latest_file_in_gcs_folder"] = Mock(return_value="older/file.mp3")
        def downloaded(blob_name, destination):
            Path(destination).write_bytes(b"downloaded audio")
            return destination
        self.api["download_file_from_gcs"] = Mock(side_effect=downloaded)
        result = self.api["download_latest_mp3_from_gcs"]("older/")
        self.assertEqual(result.suffix, ".mp3")
        self.api["download_file_from_gcs"].assert_called_once()

    def test_existing_stereo_mp3_intro_merges_with_google_mono_wav(self):
        self.generate()
        intro = self.output_dir / "existing_intro.mp3"
        source = self.chunks[1].set_frame_rate(44100).set_channels(2)
        # Simulate a pre-existing intro downloaded on a fresh GitHub runner.
        with source.export(intro, format="mp3", bitrate="192k"):
            pass
        final = self.output_dir / "mixed_episode.mp3"
        self.assertEqual(self.api["merge_multiple_audio_files"]([intro, self.output], final), final)
        with final.open("rb") as stream:
            decoded = AudioSegment.from_mp3(stream)
        self.assertEqual(decoded.channels, 2)
        self.assertEqual(decoded.frame_rate, 44100)
        self.assertAlmostEqual(len(decoded), sum(map(len, self.chunks)) + len(source), delta=5)

    def test_explicit_blob_uses_matching_master_only(self):
        self.generate()
        audio_mastering.register_uploaded_audio_master(self.output, "exact.mp3")
        def downloaded(blob_name, destination):
            Path(destination).write_bytes(b"downloaded audio")
            return destination
        self.api["download_file_from_gcs"] = Mock(side_effect=downloaded)
        self.assertEqual(self.api["download_mp3_file_from_gcs"]("exact.mp3").suffix, ".wav")
        self.assertEqual(self.api["download_mp3_file_from_gcs"]("other.mp3").suffix, ".mp3")

    def test_reused_output_invalidates_old_upload_master(self):
        self.generate()
        audio_mastering.register_uploaded_audio_master(self.output, "old.mp3")
        audio_mastering.export_audio(self.chunks[1], self.output)
        self.assertIsNone(audio_mastering.copy_uploaded_audio_master("old.mp3", self.output_dir / "copy.mp3"))

    def test_failure_cleans_chunks_and_never_retries_at_slower_speed(self):
        self.client.synthesize_speech.side_effect = ValueError("invalid argument")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertIsNone(self.generate())
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.output_dir.glob("google_tts_*")))
        self.assertEqual(self.client.synthesize_speech.call_count, 2)
        for call in self.client.synthesize_speech.call_args_list:
            self.assertAlmostEqual(call.kwargs["audio_config"].speaking_rate, 1.08)

    def test_merge_failure_returns_none_and_cleans_chunks(self):
        self.api["merge_multiple_audio_files"] = Mock(return_value=None)
        self.assertIsNone(self.generate())
        self.assertFalse(list(self.output_dir.glob("google_tts_*")))


if __name__ == "__main__":
    unittest.main()
