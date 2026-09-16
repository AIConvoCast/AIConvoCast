"""Offline tests for business-name pronunciation requests; no credentials used."""

import unittest
from unittest.mock import patch

from google.cloud import texttospeech

import google_pronunciations
from google_pronunciations import build_google_synthesis_input


class GooglePronunciationTests(unittest.TestCase):
    def rules(self, text):
        return {
            rule.phrase: rule.pronunciation
            for rule in build_google_synthesis_input(text).custom_pronunciations.pronunciations
        }

    def test_nvidia_uses_same_pronunciation_for_every_case(self):
        text = "NVIDIA, Nvidia, nvidia and NvIdIa. NVIDIA again."
        self.assertEqual(self.rules(text), {"NVIDIA": "ɛnˈvɪdiə"})
        self.assertEqual(build_google_synthesis_input(text).text,
                         "NVIDIA, NVIDIA, NVIDIA and NVIDIA. NVIDIA again.")

    def test_possessives_keep_their_ending_without_duplicate_rules(self):
        text = "NVIDIA's chips, Nvidia’s partners, nvidia'S plans."
        self.assertEqual(self.rules(text), {"NVIDIA's": "ɛnˈvɪdiəz"})
        self.assertEqual(build_google_synthesis_input(text).text,
                         "NVIDIA's chips, NVIDIA's partners, NVIDIA's plans.")

    def test_known_ai_businesses_keep_spoken_initials(self):
        self.assertEqual(self.rules("OpenAI and xAI, OpenAI’s and XAI's models."), {
            "OpenAI": "ˈoʊpən eɪ aɪ", "xAI": "ɛks eɪ aɪ",
            "OpenAI's": "ˈoʊpən eɪ aɪz", "xAI's": "ɛks eɪ aɪz",
        })

    def test_longer_phrases_are_sent_first_even_when_base_name_occurs_first(self):
        request = build_google_synthesis_input("NVIDIA and OpenAI. NVIDIA's and OpenAI's work.")
        self.assertEqual([rule.phrase for rule in request.custom_pronunciations.pronunciations],
                         ["NVIDIA's", "OpenAI's", "NVIDIA", "OpenAI"])

    def test_unknown_names_acronyms_and_embedded_names_are_untouched(self):
        text = "AMD, IBM, AWS, NVDA, NVIDIAfoo, myNVIDIA, NVIDIA_123, OpenAIish, xAI2."
        request = build_google_synthesis_input(text)
        self.assertEqual(request, texttospeech.SynthesisInput(text=text))

    def test_only_speech_name_spelling_changes_and_request_uses_ipa(self):
        text = '“NVIDIA’s R&D” <chips> & OpenAI\nNvidia-powered systems.'
        request = build_google_synthesis_input(text)
        self.assertEqual(text, '“NVIDIA’s R&D” <chips> & OpenAI\nNvidia-powered systems.')
        self.assertEqual(request.text, '“NVIDIA\'s R&D” <chips> & OpenAI\nNVIDIA-powered systems.')
        self.assertFalse(request.ssml)
        self.assertEqual(len(request.custom_pronunciations.pronunciations), 3)
        for rule in request.custom_pronunciations.pronunciations:
            self.assertEqual(rule.phonetic_encoding,
                             texttospeech.CustomPronunciationParams.PhoneticEncoding.PHONETIC_ENCODING_IPA)
        self.assertEqual(texttospeech.SynthesisInput.deserialize(
            texttospeech.SynthesisInput.serialize(request)), request)

    def test_dictionary_can_add_longer_names_and_literal_punctuation(self):
        with patch.dict(google_pronunciations.BUSINESS_NAME_PRONUNCIATIONS, {
            "Acme Labs": "ˈækmi læbz", "Acme": "ˈækmi", "A+B": "eɪ plʌs biː",
        }):
            self.assertEqual(self.rules("ACME LABS and Acme use A+B; AxB is unrelated."), {
                "Acme Labs": "ˈækmi læbz", "Acme": "ˈækmi", "A+B": "eɪ plʌs biː",
            })

    def test_empty_dictionary_adds_no_customizations(self):
        with patch.dict(google_pronunciations.BUSINESS_NAME_PRONUNCIATIONS, {}, clear=True):
            self.assertEqual(build_google_synthesis_input("NVIDIA"), texttospeech.SynthesisInput(text="NVIDIA"))


if __name__ == "__main__":
    unittest.main()
