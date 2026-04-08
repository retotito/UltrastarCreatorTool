#!/usr/bin/env python3
"""Analyze a mic trail JSON export."""
import json, sys, os
from collections import Counter

# Find the latest mic trail file
downloads = os.path.join(os.path.dirname(__file__), "downloads")
files = sorted(
    [f for f in os.listdir(downloads) if f.startswith("mic_trail_") and f.endswith(".json")],
    key=lambda f: os.path.getmtime(os.path.join(downloads, f)),
    reverse=True
)

if not files:
    print("No mic trail files found")
    sys.exit(1)

path = os.path.join(downloads, files[0])
print(f"Analyzing: {files[0]}")
print(f"File size: {os.path.getsize(path) / 1024:.1f} KB\n")

with open(path) as f:
    d = json.load(f)

print("=== META ===")
print(f"Exported: {d['exported']}")
print(f"Settings: {d['settings']}")
print(f"Song: {d['song']}")
samples = d["samples"]
print(f"Total samples: {len(samples)}")

# Basic stats
pitches = [s["smoothed"] for s in samples if s["smoothed"] is not None]
raw = [s["rawMidi"] for s in samples if s["rawMidi"] is not None]
freqs = [s["freq"] for s in samples if s["freq"] is not None]
clarities = [s["clarity"] for s in samples]

print("\n=== PITCH STATS ===")
if pitches:
    print(f"Smoothed: {len(pitches)} non-null, range {min(pitches)}-{max(pitches)}")
else:
    print("No smoothed pitches")
if raw:
    print(f"Raw MIDI: {len(raw)} non-null, range {min(raw)}-{max(raw)}")
else:
    print("No raw pitches")
if freqs:
    print(f"Frequencies: {min(freqs):.1f}-{max(freqs):.1f} Hz")
print(f"Clarity: min={min(clarities):.3f}, max={max(clarities):.3f}, avg={sum(clarities)/len(clarities):.3f}")

# Time range
times = [s["time"] for s in samples]
print(f"\n=== TIME ===")
print(f"Range: {min(times):.2f}s - {max(times):.2f}s (duration: {max(times)-min(times):.2f}s)")
avg_interval = (max(times) - min(times)) / (len(times) - 1) if len(times) > 1 else 0
print(f"Avg sample interval: {avg_interval*1000:.1f}ms (~{1/avg_interval:.0f} Hz)" if avg_interval > 0 else "")

# First 10 and last 10
print("\n=== FIRST 10 SAMPLES ===")
for s in samples[:10]:
    print(f"  t={s['time']:7.3f}  raw={str(s['rawMidi']):>4s}  med={str(s['median']):>4s}  sm={str(s['smoothed']):>4s}  tgt={str(s['target']):>4s}  cl={s['clarity']:.3f}  conf={s['confidence']}")

print("\n=== LAST 10 SAMPLES ===")
for s in samples[-10:]:
    print(f"  t={s['time']:7.3f}  raw={str(s['rawMidi']):>4s}  med={str(s['median']):>4s}  sm={str(s['smoothed']):>4s}  tgt={str(s['target']):>4s}  cl={s['clarity']:.3f}  conf={s['confidence']}")

# Pitch distribution
if pitches:
    c = Counter(pitches)
    note_names = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
    print("\n=== PITCH DISTRIBUTION (top 15) ===")
    for pitch, count in c.most_common(15):
        name = note_names[pitch % 12] + str(pitch // 12 - 1)
        bar = "█" * min(count // 5, 40)
        print(f"  MIDI {pitch:3d} ({name:>3s}): {count:4d} ({100*count/len(pitches):5.1f}%) {bar}")

# Octave jumps
if len(pitches) > 1:
    jumps = []
    for i in range(1, len(pitches)):
        diff = abs(pitches[i] - pitches[i-1])
        if diff >= 12:
            jumps.append((i, pitches[i-1], pitches[i], diff))
    print(f"\n=== OCTAVE JUMPS (>= 12 semitones) ===")
    print(f"Total: {len(jumps)} ({100*len(jumps)/len(pitches):.1f}%)")
    if jumps:
        print("First 10:")
        for idx, prev, curr, diff in jumps[:10]:
            s = samples[idx]
            print(f"  sample {idx}, t={s['time']:.3f}s: {prev} -> {curr} (jump={diff})")

# Null analysis
null_raw = sum(1 for s in samples if s["rawMidi"] is None)
null_smooth = sum(1 for s in samples if s["smoothed"] is None)
print(f"\n=== NULL SAMPLES ===")
print(f"Raw null: {null_raw}/{len(samples)} ({100*null_raw/len(samples):.1f}%)")
print(f"Smoothed null: {null_smooth}/{len(samples)} ({100*null_smooth/len(samples):.1f}%)")

# Compare raw vs smoothed where both exist
diffs = []
for s in samples:
    if s["rawMidi"] is not None and s["smoothed"] is not None:
        diffs.append(abs(s["rawMidi"] - s["smoothed"]))
if diffs:
    print(f"\n=== RAW vs SMOOTHED DIFF ===")
    print(f"Avg diff: {sum(diffs)/len(diffs):.2f} semitones")
    print(f"Max diff: {max(diffs)} semitones")
    big_diffs = sum(1 for d in diffs if d >= 12)
    print(f"Diffs >= 12: {big_diffs} ({100*big_diffs/len(diffs):.1f}%)")

# Compare smoothed vs target (how well mic matches notes)
hit_diffs = []
for s in samples:
    if s["smoothed"] is not None and s["target"] is not None:
        hit_diffs.append(abs(s["smoothed"] - s["target"]))
if hit_diffs:
    print(f"\n=== SMOOTHED vs TARGET (note accuracy) ===")
    print(f"Avg diff: {sum(hit_diffs)/len(hit_diffs):.2f} semitones")
    exact = sum(1 for d in hit_diffs if d == 0)
    within1 = sum(1 for d in hit_diffs if d <= 1)
    within2 = sum(1 for d in hit_diffs if d <= 2)
    print(f"Exact match: {exact}/{len(hit_diffs)} ({100*exact/len(hit_diffs):.1f}%)")
    print(f"Within ±1: {within1}/{len(hit_diffs)} ({100*within1/len(hit_diffs):.1f}%)")
    print(f"Within ±2: {within2}/{len(hit_diffs)} ({100*within2/len(hit_diffs):.1f}%)")
