"""Alignment evaluation on real songs against verified reference charts.

    cd backend
    ../.venv/bin/python -m eval.run_eval                     # all engines, all songs
    ../.venv/bin/python -m eval.run_eval --engines ctc --songs "Beautiful Day"

The lyrics come from the reference chart, so every engine aligns exactly the reference syllables and
errors compare one to one. Expensive steps (vocal separation, Whisper, pitch, emissions) are cached
in eval/cache/, so re-runs after an alignment change take seconds. Writes a Markdown report to
eval/reports/.

Engines:
  legacy        WhisperX words + chars → align_whisper → onset snapping (the app today)
  ctc           forced alignment of the lyrics, snapped to voiced pitch
  ctc-raw       forced alignment without any snapping
  ctc-onsets    forced alignment + the app's onset snapping instead of voice snapping
"""

import argparse
import glob
import json
import os
import shutil
import sys
import time
from datetime import datetime

import numpy as np
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from eval.metrics import summarize, timing_errors  # noqa: E402
from eval.reference import audio_file, lyrics_text, parse_reference  # noqa: E402

CACHE = os.path.join(HERE, "cache")
REPORTS = os.path.join(HERE, "reports")
ENGINES = ["legacy", "ctc", "ctc-raw", "ctc-onsets"]


def slug(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name).strip("_")


def log(message: str) -> None:
    print(f"[eval {datetime.now():%H:%M:%S}] {message}", flush=True)


# ── cached expensive steps ──────────────────────────────────
def vocals_for(song: dict, mix_path: str) -> str:
    if song.get("vocals"):
        return os.path.expanduser(song["vocals"])
    out_dir = os.path.join(CACHE, slug(song["name"]))
    target = os.path.join(out_dir, "vocals.wav")
    if not os.path.isfile(target):
        from services.vocal_separation import separate_vocals
        os.makedirs(out_dir, exist_ok=True)
        log(f"  separating vocals (Demucs) ...")
        vocals, _ = separate_vocals(mix_path, out_dir)
        import soundfile as sf
        data, sr = sf.read(vocals)
        sf.write(target, data, sr)
        if os.path.abspath(vocals) != target:
            os.remove(vocals)
    return target


def whisper_for(song: dict, vocals: str, model_name: str) -> tuple:
    """WhisperX words + chars, exactly as the app's transcription step makes them."""
    path = os.path.join(CACHE, slug(song["name"]), f"whisperx_{model_name}.json")
    if os.path.isfile(path):
        with open(path) as f:
            data = json.load(f)
        return data["words"], data["chars"]
    import whisperx
    log(f"  transcribing with WhisperX {model_name} ...")
    model = whisperx.load_model(model_name, "cpu", compute_type="int8")
    audio = whisperx.load_audio(vocals)
    result = model.transcribe(audio, batch_size=4, language=song.get("language", "en"))
    align_model, metadata = whisperx.load_align_model(language_code=result.get("language", "en"), device="cpu")
    aligned = whisperx.align(result["segments"], align_model, metadata, audio, "cpu", return_char_alignments=True)
    words = [{"word": w.get("word", "").strip(), "start": round(w["start"], 4), "end": round(w["end"], 4),
              "score": round(w.get("score", 0), 4)}
             for w in aligned.get("word_segments", []) if w.get("start") is not None and w.get("end") is not None]
    chars = [{"char": c["char"], "start": round(c["start"], 4), "end": round(c["end"], 4)}
             for seg in aligned.get("segments", []) for c in seg.get("chars", [])
             if c.get("char", "").strip() and c.get("start") is not None and c.get("end") is not None]
    with open(path, "w") as f:
        json.dump({"words": words, "chars": chars, "text": [s["text"] for s in result["segments"]]}, f)
    return words, chars


def pitch_for(song: dict, vocals: str) -> dict:
    path = os.path.join(CACHE, slug(song["name"]), "pitch.npz")
    if os.path.isfile(path):
        data = np.load(path)
        return {k: data[k] for k in data.files}
    from services.pitch_detection import detect_pitches
    log("  pitch (PYIN) ...")
    pitch = detect_pitches(vocals)
    np.savez(path, **{k: v for k, v in pitch.items() if isinstance(v, np.ndarray)})
    return pitch


# ── engines ─────────────────────────────────────────────────
def run_engine(engine: str, song: dict, lyrics: str, vocals: str, whisper_model: str) -> list:
    if engine == "legacy":
        from services.alignment_whisper import align_whisper
        from services.onset_snapping import snap_to_onsets
        words, chars = whisper_for(song, vocals, whisper_model)
        results = align_whisper(lyrics, words, song.get("language", "en"), char_timestamps=chars, audio_path=vocals)
        return snap_to_onsets(vocals, results)

    from services.forced_alignment import align_lyrics_to_emissions, compute_emissions
    emissions = compute_emissions(vocals, cache_dir=os.path.join(CACHE, slug(song["name"])))
    if engine == "ctc":
        return align_lyrics_to_emissions(lyrics, emissions, pitch_data=pitch_for(song, vocals))
    if engine == "ctc-raw":
        return align_lyrics_to_emissions(lyrics, emissions, snap_voice=False)
    if engine == "ctc-onsets":
        from services.onset_snapping import snap_to_onsets
        return snap_to_onsets(vocals, align_lyrics_to_emissions(lyrics, emissions, snap_voice=False))
    raise ValueError(f"Unknown engine {engine}")


# ── report ──────────────────────────────────────────────────
COLUMNS = [("median_ms", "median ms", "{:.0f}"), ("median_ms_unbiased", "median ms (no bias)", "{:.0f}"),
           ("within_100ms", "≤100 ms %", "{:.0f}"), ("within_250ms", "≤250 ms %", "{:.0f}"),
           ("gross", "gross >500 ms", "{}"), ("gross_pct", "gross %", "{:.1f}"), ("bias_ms", "bias ms", "{:+.0f}")]


def table(rows: list) -> str:
    head = "| song | engine | syllables | " + " | ".join(c[1] for c in COLUMNS) + " | time s |"
    sep = "|" + "---|" * (len(COLUMNS) + 4)
    lines = [head, sep]
    for row in rows:
        if "error" in row:
            lines.append(f"| {row['song']} | {row['engine']} | – | " + " | ".join("–" for _ in COLUMNS) + f" | {row['error']} |")
            continue
        s = row["summary"]
        lines.append(f"| {row['song']} | {row['engine']} | {s['syllables']} | "
                     + " | ".join(fmt.format(s[key]) for key, _, fmt in COLUMNS) + f" | {row['seconds']:.1f} |")
    return "\n".join(lines)


def worst(results: list, ref, errors: np.ndarray, count: int = 8) -> str:
    order = np.argsort(-np.abs(errors))[:count]
    lines = ["| # | syllable | line | reference s | aligned s | error ms |", "|---|---|---|---|---|---|"]
    for i in sorted(order):
        lines.append(f"| {i} | {ref[i].text} | {ref[i].line + 1} | {ref[i].start:.2f} | {results[i]['start']:.2f} | {errors[i] * 1000:+.0f} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--songs-file", default=os.path.join(HERE, "songs.yaml"))
    parser.add_argument("--songs", nargs="*", help="only these song names")
    parser.add_argument("--engines", nargs="*", default=ENGINES, choices=ENGINES)
    parser.add_argument("--whisper-model", default="medium", help="model for the legacy engine (app default: medium)")
    args = parser.parse_args()

    if not os.path.isfile(args.songs_file):
        print(f"No {args.songs_file}: copy eval/songs.example.yaml to eval/songs.yaml and edit it.")
        return 1
    with open(args.songs_file) as f:
        songs = yaml.safe_load(f)["songs"]
    if args.songs:
        songs = [s for s in songs if s["name"] in args.songs]

    rows, details = [], []
    for song in songs:
        folder = os.path.expanduser(song["folder"])
        txt = os.path.join(folder, song["txt"]) if song.get("txt") else glob.glob(os.path.join(glob.escape(folder), "*.txt"))[0]
        with open(txt, encoding="utf-8", errors="replace") as f:
            content = f.read()
        ref = parse_reference(content)
        lyrics = lyrics_text(ref)
        log(f"{song['name']}: {len(ref)} syllables")
        vocals = vocals_for(song, os.path.join(folder, audio_file(content)))
        details.append(f"## {song['name']}\n")
        for engine in args.engines:
            started = time.time()
            try:
                results = run_engine(engine, song, lyrics, vocals, args.whisper_model)
                errors = timing_errors(results, [s.start for s in ref])
            except Exception as error:  # report and continue with the next engine
                log(f"  {engine}: FAILED {type(error).__name__}: {error}")
                rows.append({"song": song["name"], "engine": engine, "error": f"{type(error).__name__}: {error}"})
                continue
            summary = summarize(errors)
            rows.append({"song": song["name"], "engine": engine, "summary": summary, "seconds": time.time() - started})
            log(f"  {engine}: median {summary['median_ms']:.0f} ms, gross {summary['gross']} "
                f"({summary['gross_pct']:.1f} %), bias {summary['bias_ms']:+.0f} ms")
            details.append(f"### {engine}: worst syllables\n\n{worst(results, ref, errors)}\n")

    os.makedirs(REPORTS, exist_ok=True)
    path = os.path.join(REPORTS, f"eval_{datetime.now():%Y%m%d_%H%M%S}.md")
    totals = []
    for engine in args.engines:
        ok = [r for r in rows if r["engine"] == engine and "summary" in r]
        if ok:
            syllables = sum(r["summary"]["syllables"] for r in ok)
            gross = sum(r["summary"]["gross"] for r in ok)
            totals.append(f"| {engine} | {len(ok)} | {syllables} | {gross} | {gross / syllables * 100:.1f} | "
                          f"{np.median([r['summary']['median_ms'] for r in ok]):.0f} |")
    report = "\n".join([
        f"# Alignment evaluation {datetime.now():%Y-%m-%d %H:%M}",
        "",
        "Start-time error per syllable against the reference chart. **gross** = off by more than 500 ms "
        "(the misplaced notes). **bias** = median signed error (a constant offset of the chart or engine).",
        "",
        "## Totals",
        "",
        "| engine | songs | syllables | gross | gross % | median of song medians ms |",
        "|---|---|---|---|---|---|",
        *totals,
        "",
        "## Per song",
        "",
        table(rows),
        "",
        *details,
    ])
    with open(path, "w") as f:
        f.write(report)
    log(f"report: {path}")
    print("\n" + table(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
