"""Business-name pronunciation rules for the pipeline's en-US Google voices."""

import re

from google.cloud import texttospeech


# IPA, not English respellings. Add explicit possessives because the suffix
# pronunciation depends on the name. Matching also accepts curly apostrophes.
BUSINESS_NAME_PRONUNCIATIONS = {
    "NVIDIA": "ɛnˈvɪdiə",          # en-VID-ee-uh
    "NVIDIA's": "ɛnˈvɪdiəz",
    "OpenAI": "ˈoʊpən eɪ aɪ",    # Open A I
    "OpenAI's": "ˈoʊpən eɪ aɪz",
    "xAI": "ɛks eɪ aɪ",          # X A I
    "xAI's": "ɛks eɪ aɪz",
}


def build_google_synthesis_input(text):
    """Attach IPA rules and normalize name spelling only in the speech input.

    Google rejects rules that differ only in case. Normalize matched names to
    the dictionary spelling so every occurrence exactly matches one rule.
    The caller's script is unchanged; unrelated text is passed through intact.
    Longer entries win so a name never masks its possessive or a longer name.
    """
    pronunciations = {
        phrase.replace("’", "'").casefold(): (phrase, ipa)
        for phrase, ipa in BUSINESS_NAME_PRONUNCIATIONS.items()
    }
    if not pronunciations:
        return texttospeech.SynthesisInput(text=text)

    alternatives = "|".join(
        re.escape(phrase).replace("'", "['’]")
        for phrase in sorted(pronunciations, key=len, reverse=True)
    )
    overrides = []
    seen = set()

    def normalize_name(match):
        phrase, ipa = pronunciations[match.group().replace("’", "'").casefold()]
        if phrase in seen:
            return phrase
        seen.add(phrase)
        overrides.append(texttospeech.CustomPronunciationParams(
            phrase=phrase,
            phonetic_encoding=(
                texttospeech.CustomPronunciationParams.PhoneticEncoding.PHONETIC_ENCODING_IPA
            ),
            pronunciation=ipa,
        ))
        return phrase

    speech_text = re.sub(
        rf"(?<!\w)(?:{alternatives})(?!\w)", normalize_name, text, flags=re.IGNORECASE,
    )
    if not overrides:
        return texttospeech.SynthesisInput(text=text)
    # Google applies rules in order: a base name first can consume part of a
    # later possessive and make the API reject that phrase as invalid.
    overrides.sort(key=lambda rule: len(rule.phrase), reverse=True)
    return texttospeech.SynthesisInput(
        text=speech_text,
        custom_pronunciations=texttospeech.CustomPronunciations(pronunciations=overrides),
    )
