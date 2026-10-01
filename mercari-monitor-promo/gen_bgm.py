import math
import struct
import subprocess
import os

SR = 44100
BPM = 120
BEAT_SEC = 60.0 / BPM
DURATION = 22.0
N = int(SR * DURATION)
PI = math.pi

CHORDS = [
    [130.81, 164.81, 196.00],
    [110.00, 138.59, 164.81],
    [146.83, 185.00, 220.00],
    [130.81, 164.81, 196.00],
]

def chord_at(beat):
    idx = int(beat / 4) % len(CHORDS)
    return CHORDS[idx]

def kick(i, freq=55, decay=10):
    t = i / SR
    phase = t % BEAT_SEC
    if phase > 0.25:
        return 0.0
    pitch = freq * math.exp(-phase * 20) + freq * 0.5
    env = math.exp(-phase * decay)
    return math.sin(2 * PI * pitch * phase) * env * 0.8

def snare(i, freq=220, decay=15):
    t = i / SR
    beat_pos = (t % BEAT_SEC) / BEAT_SEC
    if abs(beat_pos - 0.5) > 0.08:
        return 0.0
    phase = t % BEAT_SEC - BEAT_SEC * 0.42
    if phase < 0:
        return 0.0
    env = math.exp(-phase * decay)
    tone = math.sin(2 * PI * freq * phase) * 0.5
    noise = math.sin(2 * PI * freq * 2.37 * phase + i * 0.1) * 0.5
    return (tone + noise) * env * 0.4

def hihat_closed(i, freq=8000, decay=50):
    t = i / SR
    eighth = BEAT_SEC / 2
    phase = t % eighth
    if phase > 0.03:
        return 0.0
    env = math.exp(-phase * decay)
    return math.sin(2 * PI * freq * phase + i * 0.3) * env * 0.15

def hihat_open(i, freq=6000, decay=8):
    t = i / SR
    beat_pos = (t % BEAT_SEC) / BEAT_SEC
    if abs(beat_pos - 0.75) > 0.05:
        return 0.0
    phase = t % BEAT_SEC - BEAT_SEC * 0.70
    if phase < 0:
        return 0.0
    env = math.exp(-phase * decay)
    return math.sin(2 * PI * freq * phase + i * 0.2) * env * 0.2

def sub_bass(i, decay=3):
    t = i / SR
    beat = t / BEAT_SEC
    chord = chord_at(beat)
    root = chord[0] / 2
    phase = t % BEAT_SEC
    env = math.exp(-phase * decay) * 0.6 + 0.4
    return math.sin(2 * PI * root * t) * env * 0.3

def chord_pad(i):
    t = i / SR
    beat = t / BEAT_SEC
    chord = chord_at(beat)
    lfo = 0.8 + 0.2 * math.sin(2 * PI * 0.5 * t)
    val = 0.0
    for f in chord:
        val += math.sin(2 * PI * f * t) * 0.15
        val += math.sin(2 * PI * f * 2 * t) * 0.05
    return val * lfo * 0.25

def arpeggio(i):
    t = i / SR
    beat = t / BEAT_SEC
    chord = chord_at(beat)
    sixteenth = BEAT_SEC / 4
    note_idx = int((t % (sixteenth * 4)) / sixteenth) % 3
    freq = chord[note_idx] * 2
    phase = t % sixteenth
    env = math.exp(-phase * 12)
    return math.sin(2 * PI * freq * t) * env * 0.2

def melody(i):
    t = i / SR
    beat = t / BEAT_SEC
    chord = chord_at(beat)
    measure_pos = beat % 4
    if measure_pos < 1:
        freq = chord[2] * 2
    elif measure_pos < 2.5:
        freq = chord[1] * 2
    else:
        freq = chord[0] * 2
    phase = t % (BEAT_SEC * 0.5)
    attack = min(phase * 20, 1.0)
    decay_env = math.exp(-phase * 4)
    return math.sin(2 * PI * freq * t) * attack * decay_env * 0.15

def riser(i):
    t = i / SR
    beat = t / BEAT_SEC
    measure_pos = beat % 4
    if measure_pos < 3.0:
        return 0.0
    progress = (measure_pos - 3.0) / 1.0
    sweep_freq = 200 + progress * 2000
    noise = math.sin(2 * PI * sweep_freq * t + i * 0.5)
    return noise * progress * 0.1

print(f"Generating BGM: {DURATION}s at {SR}Hz, {BPM}BPM...")
samples = []
for i in range(N):
    s = 0.0
    s += kick(i)
    s += kick(i, freq=82, decay=12)
    s += snare(i)
    s += hihat_closed(i)
    s += hihat_open(i)
    s += sub_bass(i)
    s += chord_pad(i)
    s += arpeggio(i)
    s += melody(i)
    s += riser(i)
    s = max(-1.0, min(1.0, s))
    samples.append(int(s * 32767))

wav_path = "public/bgm_gen.wav"
with open(wav_path, "wb") as f:
    data_size = N * 2
    f.write(b"RIFF")
    f.write(struct.pack("<I", 36 + data_size))
    f.write(b"WAVE")
    f.write(b"fmt ")
    f.write(struct.pack("<I", 16))
    f.write(struct.pack("<HHIIHH", 1, 1, SR, SR * 2, 2, 16))
    f.write(b"data")
    f.write(struct.pack("<I", data_size))
    for s in samples:
        f.write(struct.pack("<h", s))

print(f"WAV written: {wav_path}")

mp3_path = "public/bgm.mp3"
subprocess.run([
    "ffmpeg", "-y", "-i", wav_path,
    "-codec:a", "libmp3lame", "-b:a", "192k",
    mp3_path
], check=True)
print(f"MP3 written: {mp3_path}")