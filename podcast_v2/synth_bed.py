"""A light synth music bed for the intro and outro, synthesized with numpy.

Warm detuned pads on a Cmaj9 - Am9 - Fmaj9 - G6/9 progression, a soft plucked
arpeggio with a ping-pong echo, a gentle sub bass, and a dark reverb, at about
100 BPM. Deterministic for a given seed and needs no music service. Band-limited
additive synthesis keeps it free of aliasing, and every note has smooth
envelopes so there are no clicks.
"""

import wave
from pathlib import Path

import numpy as np

RATE = 48000
TEMPO = 100
# (bass root, pad voicing, arpeggio notes) as MIDI note numbers, one chord per bar.
PROGRESSION = [
    (36, [55, 59, 62, 64], [72, 76, 79, 83, 86, 83, 79, 76]),  # Cmaj9
    (33, [52, 55, 59, 60], [69, 72, 76, 79, 83, 79, 76, 72]),  # Am9
    (29, [48, 52, 55, 57], [65, 69, 72, 76, 79, 76, 72, 69]),  # Fmaj9
    (31, [50, 55, 57, 59], [67, 71, 74, 76, 81, 76, 74, 71]),  # G6/9
]


def frequency(note):
    return 440.0 * 2 ** ((note - 69) / 12)


def envelope(length, attack, release, rate=RATE):
    """Linear-in-dB-ish smooth envelope: raised-cosine attack and release."""
    env = np.ones(length)
    a, r = min(int(attack * rate), length), min(int(release * rate), length)
    if a:
        env[:a] = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, a))
    if r:
        env[-r:] *= 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, r))
    return env


def pad_voice(note, seconds, rng, detune_cents, cutoff=1400.0):
    """Band-limited, gently low-passed sawtooth (additive)."""
    f = frequency(note) * 2 ** (detune_cents / 1200)
    t = np.arange(int(seconds * RATE)) / RATE
    out = np.zeros_like(t)
    harmonics = max(1, min(24, int(5000 / f)))
    for n in range(1, harmonics + 1):
        amp = (1.0 / n) / (1.0 + (n * f / cutoff) ** 2)
        out += amp * np.sin(2 * np.pi * n * f * t + rng.uniform(0, 2 * np.pi))
    return out


def pluck(note, seconds, decay=0.22):
    """Soft triangle-like pluck with an exponential decay."""
    f = frequency(note)
    t = np.arange(int(seconds * RATE)) / RATE
    tone = sum((1.0 / n ** 2) * np.sin(2 * np.pi * n * f * t) for n in (1, 3, 5))
    tone += 0.3 * np.sin(2 * np.pi * 2 * f * t)
    env = np.exp(-t / decay) * envelope(len(t), 0.004, 0.05)
    return tone * env


def reverb(stereo, rng, seconds=2.2, wet=0.28):
    """Convolution with decaying, darkened noise; decorrelated left and right."""
    length = int(seconds * RATE)
    t = np.arange(length) / RATE
    decay = np.exp(-6.9 * t / seconds)  # -60 dB at `seconds`
    kernel = np.ones(24) / 24  # darken: simple moving-average low-pass
    out = np.empty_like(stereo)
    for channel in range(2):
        ir = np.convolve(rng.standard_normal(length) * decay, kernel, mode="same")
        ir[: int(0.015 * RATE)] = 0  # short pre-delay
        ir /= np.sqrt(np.sum(ir ** 2))
        size = 1 << int(np.ceil(np.log2(len(stereo) + length)))
        wet_signal = np.fft.irfft(np.fft.rfft(stereo[:, channel], size) * np.fft.rfft(ir, size), size)
        out[:, channel] = (1 - wet) * stereo[:, channel] + wet * wet_signal[: len(stereo)]
    return out


def light_synth_bed(seconds, seed=7, tempo=TEMPO):
    """Return a (samples, 2) float array in [-1, 1] of the bed, `seconds` long."""
    rng = np.random.default_rng(seed)
    total = int(seconds * RATE)
    beat = 60.0 / tempo
    bar = 4 * beat
    tail = 1.2
    mix = np.zeros((total + int(4 * RATE), 2))

    for index in range(int(np.ceil(seconds / bar)) + 1):
        root, pad, arp = PROGRESSION[index % len(PROGRESSION)]
        start = int(index * bar * RATE)
        if start >= total:
            break
        # Pads: three detuned voices per note, spread across the stereo field.
        length = bar + tail
        env = envelope(int(length * RATE), 0.7, tail + 0.3)
        for note in pad:
            for cents, pan in ((-7, 0.25), (0, 0.5), (7, 0.75)):
                voice = pad_voice(note, length, rng, cents) * env * 0.055
                end = start + len(voice)
                mix[start:end, 0] += voice * np.sqrt(1 - pan)
                mix[start:end, 1] += voice * np.sqrt(pan)
        # Sub bass: a soft sine on the root, swelling with the bar.
        t = np.arange(int(length * RATE)) / RATE
        bass = np.sin(2 * np.pi * frequency(root) * t) * envelope(len(t), 0.4, tail + 0.2) * 0.12
        mix[start:start + len(bass)] += bass[:, None] * 0.7071
        # Arpeggio: eighth notes with a ping-pong echo.
        for step, note in enumerate(arp):
            onset = start + int(step * beat / 2 * RATE)
            note_audio = pluck(note, 0.9) * 0.09
            for echo in range(4):
                at = onset + int(echo * 0.75 * beat * RATE)
                gain = 0.38 ** echo
                pan = 0.5 if echo == 0 else (0.2 if echo % 2 else 0.8)
                end = min(at + len(note_audio), len(mix))
                if at >= end:
                    continue
                chunk = note_audio[: end - at] * gain
                mix[at:end, 0] += chunk * np.sqrt(1 - pan)
                mix[at:end, 1] += chunk * np.sqrt(pan)

    # Gentle movement: a slow swell so the bed never feels static.
    t = np.arange(len(mix)) / RATE
    mix *= (0.92 + 0.08 * np.sin(2 * np.pi * 0.11 * t))[:, None]
    mix = reverb(mix, rng)[:total]
    mix *= envelope(total, 1.0, 2.0)[:, None]
    peak = np.max(np.abs(mix))
    return mix / peak * 0.5 if peak else mix


def write_wav(samples, path, rate=RATE):
    """16-bit stereo WAV."""
    pcm = np.clip(samples, -1.0, 1.0)
    pcm = (pcm * 32767).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())
    return Path(path)


def compose(seconds, path, seed=7):
    """Write a bed of at least `seconds` to `path` (WAV)."""
    return write_wav(light_synth_bed(seconds, seed=seed), path)
