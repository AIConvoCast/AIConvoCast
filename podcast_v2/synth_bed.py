"""Light synth music beds for the intro and outro, synthesized with numpy.

Two pieces (styles):
- calm: warm detuned pads on a Cmaj9 - Am9 - Fmaj9 - G6/9 progression, a soft
  plucked arpeggio with a ping-pong echo, a gentle sub bass and a dark reverb,
  at 100 BPM.
- upbeat: a relaxed but driving synth groove in D major at 112 BPM: syncopated
  electric-piano-like FM bells, a pulsing eighth-note bass, soft kick, clap and
  off-beat hats, and warm pads that breathe with the kick, over a
  Dmaj9 - Aadd9 - Bm7 - Gmaj7 progression.

Deterministic for a given seed and needs no music service. Band-limited
synthesis keeps it free of aliasing, and every sound has smooth envelopes so
there are no clicks.
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


STYLES = {
    "calm": "soft pads, a gentle arpeggio and a low bass at 100 BPM",
    "upbeat": "an upbeat but relaxed groove at 112 BPM: electric-piano-like bells, a pulsing bass, "
              "soft drums and warm pads",
}
UPBEAT_TEMPO = 112
# (bass root, pad voicing, bell notes) as MIDI note numbers, one chord per bar, in D major.
UPBEAT_PROGRESSION = [
    (38, [57, 61, 64, 66], [74, 78, 81, 85, 76]),  # Dmaj9
    (33, [57, 61, 64, 71], [73, 76, 81, 83, 85]),  # Aadd9
    (35, [57, 59, 62, 66], [71, 74, 78, 81, 83]),  # Bm7
    (31, [55, 59, 62, 66], [71, 74, 78, 79, 83]),  # Gmaj7
]
# Sixteenth-note bell pattern: index into the chord's bell notes, None for a rest.
BELL_PATTERN = [0, None, 2, 1, None, 3, 2, None, 0, None, 4, 2, None, 3, 1, None]


def add(mix, start, audio, pan=0.5):
    """Mix mono `audio` into the stereo buffer at sample `start`, equal-power panned."""
    end = min(start + len(audio), len(mix))
    if start < 0 or start >= end:
        return
    chunk = audio[: end - start]
    mix[start:end, 0] += chunk * np.sqrt(1 - pan)
    mix[start:end, 1] += chunk * np.sqrt(pan)


def band_noise(rng, seconds, low, high):
    """White noise limited to low..high Hz, normalized to a peak of 1."""
    n = int(seconds * RATE)
    spectrum = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n, 1 / RATE)
    spectrum[(freqs < low) | (freqs > high)] = 0
    out = np.fft.irfft(spectrum, n)
    return out / np.max(np.abs(out))


def kick():
    """Soft kick: a sine sweeping 120 Hz to 45 Hz with a short decay."""
    t = np.arange(int(0.35 * RATE)) / RATE
    sweep = 45 + 75 * np.exp(-t / 0.04)
    return np.sin(2 * np.pi * np.cumsum(sweep) / RATE) * np.exp(-t / 0.11) * envelope(len(t), 0.002, 0.05)


def clap(rng):
    t = np.arange(int(0.25 * RATE)) / RATE
    body = 0.3 * np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.05)
    return (band_noise(rng, 0.25, 900, 5000) * np.exp(-t / 0.09) + body) * envelope(len(t), 0.002, 0.05)


def hat(rng):
    t = np.arange(int(0.08 * RATE)) / RATE
    return band_noise(rng, 0.08, 7000, 15000) * np.exp(-t / 0.022) * envelope(len(t), 0.001, 0.02)


def bell(note, seconds=0.9):
    """Electric-piano-like FM bell: 2:1 modulator with a decaying index."""
    f = frequency(note)
    t = np.arange(int(seconds * RATE)) / RATE
    index = 1.6 * np.exp(-t / 0.12)
    tone = np.sin(2 * np.pi * f * t + index * np.sin(2 * np.pi * 2 * f * t))
    return tone * np.exp(-t / 0.35) * envelope(len(t), 0.003, 0.06)


def bass_note(note, seconds):
    f = frequency(note)
    t = np.arange(int(seconds * RATE)) / RATE
    tone = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) + 0.12 * np.sin(6 * np.pi * f * t)
    return tone * envelope(len(t), 0.006, 0.04) * (0.65 + 0.35 * np.exp(-t / 0.08))


def upbeat_bed(seconds, rng, tempo=UPBEAT_TEMPO):
    total = int(seconds * RATE)
    beat = 60.0 / tempo
    bar = 4 * beat
    step = beat / 4
    size = total + int(4 * RATE)
    music = np.zeros((size, 2))   # pads and bells, sent to the reverb
    dry = np.zeros((size, 2))     # drums and bass stay dry
    kick_sound, clap_sound, hat_sound = kick(), clap(rng), hat(rng)
    kick_times = []

    bars = int(np.ceil(seconds / bar)) + 1
    for index in range(bars):
        root, pad, bells = UPBEAT_PROGRESSION[index % len(UPBEAT_PROGRESSION)]
        start = int(index * bar * RATE)
        if start >= total:
            break
        length = bar + 0.8
        env = envelope(int(length * RATE), 0.25, 0.9)
        for note in pad:
            for cents, pan in ((-6, 0.3), (6, 0.7)):
                add(music, start, pad_voice(note, length, rng, cents, cutoff=1800.0) * env * 0.04, pan)
        for position, pick in enumerate(BELL_PATTERN):
            if pick is None:
                continue
            accent = 1.0 if position % 4 == 0 else 0.75
            add(music, start + int(position * step * RATE), bell(bells[pick]) * 0.085 * accent,
                0.35 if position % 2 else 0.65)
        for eighth in range(8):
            at = start + int(eighth * 2 * step * RATE)
            note = root + 12 if eighth == 7 else root
            add(dry, at, bass_note(note, 2 * step * 0.9) * (0.11 if eighth % 2 == 0 else 0.085))
            add(dry, at, hat_sound * (0.045 if eighth % 2 else 0.022) * rng.uniform(0.85, 1.0),
                0.6 if eighth % 2 else 0.45)
        for count in range(4):
            at = start + int(count * beat * RATE)
            if count in (0, 2):
                add(dry, at, kick_sound * 0.32)
                kick_times.append(at)
            else:
                add(dry, at, clap_sound * 0.09, 0.5)

    # Pads and bells breathe with the kick (a gentle pump), then share a short room.
    pump = np.ones(size)
    t = np.arange(int(0.45 * RATE)) / RATE
    dip = 1 - 0.3 * np.exp(-t / 0.13) * envelope(len(t), 0.004, 0.0)
    for at in kick_times:
        end = min(at + len(dip), size)
        pump[at:end] *= dip[: end - at]
    music *= pump[:, None]
    mix = reverb(music, rng, seconds=1.6, wet=0.22) + reverb(dry, rng, seconds=0.6, wet=0.08)
    mix = mix[:total] * envelope(total, 0.6, 2.0)[:, None]
    peak = np.max(np.abs(mix))
    return mix / peak * 0.5 if peak else mix


def light_synth_bed(seconds, seed=7, tempo=TEMPO, style="calm"):
    """Return a (samples, 2) float array in [-1, 1] of the bed, `seconds` long."""
    rng = np.random.default_rng(seed)
    if style == "upbeat":
        return upbeat_bed(seconds, rng)
    if style != "calm":
        raise ValueError(f"Unknown synth style {style!r}; use one of {sorted(STYLES)}.")
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


def compose(seconds, path, seed=7, style="calm"):
    """Write a bed of at least `seconds` to `path` (WAV)."""
    return write_wav(light_synth_bed(seconds, seed=seed, style=style), path)
