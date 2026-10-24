"""Forced alignment of the user's lyrics to the vocals (CTC, MMS aligner).

Every lyric word is placed where the audio fits it best, in order, over the whole song. Unlike
`alignment_whisper`, timing does not depend on what Whisper heard: words Whisper missed still get a
position, and nothing is guessed. See docs/decisions/0002-forced-alignment-of-user-lyrics.md.

Two parts:
- `compute_emissions()`: runs the aligner model over the audio (slow, needs torch + transformers)
  and returns per-frame letter log-probabilities.
- `align_lyrics_to_emissions()`: pure numpy, text + emissions → syllable timings. Unit-tested
  with synthetic emissions.

Output format is the same as `align_whisper()`, so pitch, BPM, GAP and the writer are unchanged.
"""

import hashlib
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from services.alignment_whisper import _build_word_groups, parse_lyrics
from utils.logger import log_step

# Default aligner: Tune Studio's singing fine-tune of Meta's MMS-300m forced aligner (ONNX, CC-BY-NC-4.0,
# see ADR 0002). Pinned revision. Runs on onnxruntime; no torch needed.
SUNG_MODEL_ID = "tuneperfect/tunestudio-aligner"
SUNG_MODEL_REVISION = "4c6edce202fae335e6239c09ea17ecddcf29b42e"
SUNG_MODEL_FILE = "aligner.onnx"
SUNG_MODEL_BYTES = 1262284621

# The stock speech model it was fine-tuned from (torch + transformers). Kept for evaluation (`model_name="mms"`).
MODEL_ID = "MahmoudAshraf/mms-300m-1130-forced-aligner"
MODEL_REVISION = "49402e9577b1158620820667c218cd494cc44486"

SAMPLE_RATE = 16_000
FRAME_SEC = 0.02            # one emission frame per 320 samples
SAMPLES_PER_FRAME = 320
WINDOW_SEC = 30             # model runs on 30 s windows ...
CONTEXT_SEC = 2             # ... with 2 s of context on each side

# The model's vocabulary (vocab.json of the pinned revision).
VOCAB = {
    "<blank>": 0, "<pad>": 1, "</s>": 2, "<unk>": 3,
    "a": 4, "i": 5, "e": 6, "n": 7, "o": 8, "u": 9, "t": 10, "s": 11, "r": 12, "m": 13,
    "k": 14, "l": 15, "d": 16, "g": 17, "h": 18, "y": 19, "b": 20, "p": 21, "w": 22, "c": 23,
    "v": 24, "j": 25, "z": 26, "f": 27, "'": 28, "q": 29, "x": 30,
}
BLANK = 0
NUM_CLASSES = len(VOCAB)
# Extra target before every word with log-probability 0 in every frame: it absorbs what is sung
# but not in the lyrics (ad-libs, breaths, backing vocals), so it doesn't pull words out of place.
STAR = NUM_CLASSES

# A word whose mean log-probability is below this is flagged for review in the editor.
LOW_CONFIDENCE_SCORE = -2.0

# Silence gate: frames this far below the song's loud singing (95th percentile) count as silent,
# and no letter may be placed there. Separated vocals are near silent between lines.
SILENCE_BELOW_LOUD_DB = 30.0
SILENCE_FLOOR_DB = -50.0
# Sounding regions are widened by this many frames on each side (soft consonants at word edges).
SOUNDING_PAD_FRAMES = 3
# Letters are made this unlikely in silent frames (log-probability).
SILENT_LETTER_LOG_PROB = -1e4


class AlignmentError(Exception):
    """The lyrics can't be aligned to this audio (e.g. more letters than frames)."""


class UnsupportedText(AlignmentError):
    """The lyrics contain a script the aligner can't read yet (only Latin script so far)."""


# ────────────────────────────────────────────────────────────
# Text
# ────────────────────────────────────────────────────────────
_APOSTROPHES = "’‘ʼ`´"
_SPECIAL = {"ß": "ss", "æ": "ae", "œ": "oe", "ø": "o", "đ": "d", "ł": "l", "þ": "th", "ð": "d"}


# App language (ISO 639-1, as Whisper names them) → ISO 639-3, for uroman's language-specific rules.
ISO_639_3 = {
    "af": "afr", "sq": "sqi", "am": "amh", "ar": "ara", "hy": "hye", "az": "aze", "ba": "bak", "eu": "eus",
    "be": "bel", "bn": "ben", "bs": "bos", "br": "bre", "bg": "bul", "ca": "cat", "zh": "zho", "yue": "yue",
    "hr": "hrv", "cs": "ces", "da": "dan", "nl": "nld", "en": "eng", "et": "est", "fo": "fao", "fi": "fin",
    "fr": "fra", "gl": "glg", "ka": "kat", "de": "deu", "el": "ell", "gu": "guj", "ht": "hat", "ha": "hau",
    "haw": "haw", "he": "heb", "hi": "hin", "hu": "hun", "is": "isl", "id": "ind", "it": "ita", "ja": "jpn",
    "jw": "jav", "kn": "kan", "kk": "kaz", "km": "khm", "ko": "kor", "lo": "lao", "la": "lat", "lv": "lav",
    "ln": "lin", "lt": "lit", "lb": "ltz", "mk": "mkd", "mg": "mlg", "ms": "msa", "ml": "mal", "mt": "mlt",
    "mi": "mri", "mr": "mar", "mn": "mon", "my": "mya", "ne": "nep", "no": "nor", "nn": "nno", "oc": "oci",
    "ps": "pus", "fa": "fas", "pl": "pol", "pt": "por", "pa": "pan", "ro": "ron", "ru": "rus", "sa": "san",
    "sr": "srp", "sn": "sna", "sd": "snd", "si": "sin", "sk": "slk", "sl": "slv", "so": "som", "es": "spa",
    "su": "sun", "sw": "swa", "sv": "swe", "tl": "tgl", "tg": "tgk", "ta": "tam", "tt": "tat", "te": "tel",
    "th": "tha", "bo": "bod", "tr": "tur", "tk": "tuk", "uk": "ukr", "ur": "urd", "uz": "uzb", "vi": "vie",
    "cy": "cym", "yi": "yid", "yo": "yor",
}

_uroman_cache: dict = {}


def _uroman():
    """The universal romanizer (uroman, by Ulf Hermjakob, USC ISI), or None if it isn't installed.

    MMS was trained on uroman's romanization, so every script works through it ("Привет" → "privet").
    """
    if "instance" not in _uroman_cache:
        try:
            import uroman
            _uroman_cache["instance"] = uroman.Uroman()
        except Exception as error:  # ImportError, or its data files missing in a broken install
            log_step("CTC_ALIGN", f"uroman unavailable ({error}): only Latin script can be aligned")
            _uroman_cache["instance"] = None
    return _uroman_cache["instance"]


# "&" as it is sung
_AND = {"en": "and", "de": "und", "it": "e", "fr": "et", "es": "y", "pt": "e", "nl": "en", "sv": "och",
        "da": "og", "no": "og", "pl": "i", "cs": "a", "ru": "i", "fi": "ja", "tr": "ve"}


def spell_numbers(text: str, language: str = "en") -> str:
    """Digits as the words that are sung ("12" → "twelve", in Italian "dodici"), so the aligner can hear them.
    Years (1100–2099) are read as years ("1977" → "nineteen seventy-seven"). Languages num2words doesn't know
    are spelled in English; without num2words, digits stay (and get no letters)."""
    if not any(ch.isdigit() for ch in text):
        return text
    try:
        from num2words import num2words
    except ImportError:
        return text

    def spell(match) -> str:
        number = int(match.group())
        kind = "year" if 1100 <= number <= 2099 and len(match.group()) == 4 else "cardinal"
        for lang in (language, "en"):
            try:
                return f" {num2words(number, lang=lang, to=kind)} "
            except (NotImplementedError, OverflowError, ValueError, KeyError):
                continue
        return match.group()
    return re.sub(r"\d+", spell, text)


def romanize(text: str, language: str = "en") -> str:
    """The aligner's letters for `text`: lowercase a–z and `'`, everything else dropped.

    Numbers are spelled out first (spell_numbers). Any script goes through uroman (as in MMS training).
    Without uroman, accents are removed and other scripts raise UnsupportedText.
    """
    text = spell_numbers(text, language).replace("&", f" {_AND.get(language, 'and')} ")
    romanizer = _uroman()
    if romanizer is not None and text:
        text = romanizer.romanize_string(text, lcode=ISO_639_3.get(language))
    out = []
    for char in unicodedata.normalize("NFKC", text).lower():
        if char in _APOSTROPHES:
            char = "'"
        char = _SPECIAL.get(char, char)
        for base in unicodedata.normalize("NFKD", char):
            if base in VOCAB and VOCAB[base] >= 4:
                out.append(base)
            elif unicodedata.category(base).startswith("L"):
                raise UnsupportedText(f"Can't align '{text}': this script needs uroman (pip install uroman).")
    return "".join(out)


@dataclass
class Word:
    """A lyric word: its syllables and how many aligner letters each one has."""
    text: str
    syllables: list           # parse_lyrics syllable dicts
    letters: List[str]        # romanized letters per syllable
    line_index: int
    is_rap: bool

    @property
    def flat_letters(self) -> str:
        return "".join(self.letters)


def lyric_words(lyrics_text: str, language: str = "en") -> List[Word]:
    """The lyrics as words with their syllables (same parsing as the rest of the pipeline)."""
    flat = [s for line in parse_lyrics(lyrics_text) for s in line]
    words = []
    for group in _build_word_groups(flat):
        letters = [romanize(s["text"].strip().lstrip("~"), language) for s in group["syllables"]]
        words.append(Word(group["word"], group["syllables"], letters, group["line_index"], group["is_rap"]))
    return words


def build_targets(words: List[Word]) -> tuple:
    """Target ids for the CTC search: <star> before each word's letters and after the last word.

    The trailing <star> matters: without it, anything sung after the lyrics (an outro, ad-libs)
    would have to be blank, and the last words would be pulled onto it.

    Returns (targets, owners): owners[k] = (word index, letter index) for letter targets, None for stars.
    Words without letters (e.g. "&") get no targets and are placed between their neighbours later.
    """
    targets, owners = [], []
    for w_idx, word in enumerate(words):
        letters = word.flat_letters
        if not letters:
            continue
        targets.append(STAR)
        owners.append(None)
        for l_idx, letter in enumerate(letters):
            targets.append(VOCAB[letter])
            owners.append((w_idx, l_idx))
    if targets:
        targets.append(STAR)
        owners.append(None)
    return targets, owners


# ────────────────────────────────────────────────────────────
# CTC forced alignment (Viterbi)
# ────────────────────────────────────────────────────────────
def with_star_column(log_probs: np.ndarray) -> np.ndarray:
    """Append the <star> column (log-probability 0) to (frames × classes) log-probabilities."""
    return np.concatenate([log_probs, np.zeros((log_probs.shape[0], 1), dtype=log_probs.dtype)], axis=1)


def sounding_frames(loudness_db: np.ndarray) -> np.ndarray:
    """Which frames have something sung in them: not far below the loud parts, widened a little."""
    loudness_db = np.asarray(loudness_db, dtype=np.float32)
    if loudness_db.size == 0:
        return np.zeros(0, dtype=bool)
    loud = np.percentile(loudness_db, 95)
    sounding = loudness_db >= max(SILENCE_FLOOR_DB, loud - SILENCE_BELOW_LOUD_DB)
    if SOUNDING_PAD_FRAMES:
        kernel = np.ones(2 * SOUNDING_PAD_FRAMES + 1)
        sounding = np.convolve(sounding.astype(float), kernel, mode="same") > 0
    return sounding


def gate_silence(log_probs: np.ndarray, loudness_db: np.ndarray) -> np.ndarray:
    """No letters in silent frames: only blank (and <star>) remain possible there."""
    gated = log_probs.copy()
    sounding = sounding_frames(loudness_db)
    frames = min(len(sounding), len(gated))
    silent = np.zeros(len(gated), dtype=bool)
    silent[:frames] = ~sounding[:frames]
    letters = [i for i in range(NUM_CLASSES) if i != BLANK]
    gated[np.ix_(silent, letters)] = SILENT_LETTER_LOG_PROB
    return gated


def forced_align(log_probs: np.ndarray, targets: List[int]) -> np.ndarray:
    """The most likely CTC path of `targets` through `log_probs` (frames × classes).

    Returns the state per frame in the extended sequence (blank, t0, blank, t1, ..., blank):
    odd state 2k+1 = target k, even states = blank.
    """
    num_frames = log_probs.shape[0]
    num_targets = len(targets)
    if num_targets == 0:
        raise AlignmentError("There is no text to align.")
    repeats = sum(1 for i in range(1, num_targets) if targets[i] == targets[i - 1])
    if num_frames < num_targets + repeats:
        raise AlignmentError("The lyrics are too long for this audio.")

    num_states = 2 * num_targets + 1
    labels = np.full(num_states, BLANK, dtype=np.int64)
    labels[1::2] = targets
    # A blank may be skipped only between two different labels.
    can_skip = np.zeros(num_states, dtype=bool)
    can_skip[3::2] = labels[3::2] != labels[1:-2:2]

    neg_inf = np.float32(-np.inf)
    alpha = np.full(num_states, neg_inf, dtype=np.float32)
    alpha[0] = log_probs[0, BLANK]
    alpha[1] = log_probs[0, labels[1]]
    back = np.zeros((num_frames, num_states), dtype=np.int8)

    for t in range(1, num_frames):
        stay = alpha
        step = np.concatenate(([neg_inf], alpha[:-1]))
        skip = np.where(can_skip, np.concatenate(([neg_inf, neg_inf], alpha[:-2])), neg_inf)
        choices = np.stack([stay, step, skip])
        best = np.argmax(choices, axis=0)
        back[t] = best
        alpha = choices[best, np.arange(num_states)] + log_probs[t, labels]

    state = num_states - 1 if alpha[-1] >= alpha[-2] else num_states - 2
    if not np.isfinite(alpha[state]):
        raise AlignmentError("No alignment path through the audio.")
    path = np.empty(num_frames, dtype=np.int64)
    for t in range(num_frames - 1, -1, -1):
        path[t] = state
        state -= int(back[t, state])  # int(): numpy 2 won't mix int8 with large Python ints
    return path


# ────────────────────────────────────────────────────────────
# From the path to word and syllable timings
# ────────────────────────────────────────────────────────────
@dataclass
class WordTiming:
    start: float
    end: float
    score: float                                     # mean log-probability, 0 = certain
    letters: List[tuple] = field(default_factory=list)  # (start, end) per letter, empty if moved


def word_timings(path: np.ndarray, log_probs: np.ndarray, targets: List[int], owners: list,
                 words: List[Word], offset: float = 0.0) -> List[Optional[WordTiming]]:
    """Per word: letter spans from the path, start/end and score. None for words without letters."""
    num_targets = len(targets)
    letter_frames: dict = {}
    for t, state in enumerate(path):
        if state % 2 == 1:
            k = (state - 1) // 2
            first_last = letter_frames.get(k)
            letter_frames[k] = (t, t) if first_last is None else (first_last[0], t)

    target_ids = np.asarray(targets)
    labels = np.where(path % 2 == 1, target_ids[np.clip((path - 1) // 2, 0, num_targets - 1)], BLANK)
    frame_scores = log_probs[np.arange(len(path)), labels]

    by_word: dict = {}
    for k, owner in enumerate(owners):
        if owner is None:
            continue
        w_idx, _ = owner
        a, b = letter_frames[k]
        by_word.setdefault(w_idx, []).append((offset + a * FRAME_SEC, offset + (b + 1) * FRAME_SEC, a, b))

    out: List[Optional[WordTiming]] = [None] * len(words)
    for w_idx, spans in by_word.items():
        first_frame, last_frame = spans[0][2], spans[-1][3]
        out[w_idx] = WordTiming(
            start=spans[0][0],
            end=spans[-1][1],
            score=float(np.mean(frame_scores[first_frame:last_frame + 1])),
            letters=[(s, e) for s, e, _, _ in spans],
        )
    return out


def pull_in_edges(timings: List[WordTiming], max_gap: float = 0.8, length: float = 0.3) -> None:
    """Move a line's first or last word back next to the line when it sits far away (in place).

    The aligner sometimes parks an edge word on unrelated sound seconds away (a breath, an ad-lib).
    """
    if len(timings) < 2:
        return
    first, second = timings[0], timings[1]
    if second.start - first.end > max_gap:
        first.start = max(first.end, second.start - length)
        first.end = second.start
        first.letters = []
    last, before = timings[-1], timings[-2]
    if last.start - before.end > max_gap:
        last.start = before.end
        last.end = max(last.start + length, min(last.end, last.start + 2.0))
        last.letters = []


def snap_to_voice(timing: WordTiming, voiced_times: np.ndarray) -> None:
    """Move a word's start to its first voiced pitch frame, if there is one inside the word (in place)."""
    inside = voiced_times[(voiced_times >= timing.start) & (voiced_times < timing.end)]
    if len(inside) and inside[0] > timing.start:
        shift = inside[0] - timing.start
        timing.start = float(inside[0])
        if timing.letters:
            first_start, first_end = timing.letters[0]
            timing.letters[0] = (min(first_start + shift, first_end), first_end)


def _syllable_spans(word: Word, timing: WordTiming) -> List[tuple]:
    """(start, end) per syllable: each starts at its first letter and ends where the next starts."""
    count = len(word.syllables)
    if count == 1:
        return [(timing.start, timing.end)]
    starts = []
    letter_idx = 0
    for s_idx, letters in enumerate(word.letters):
        if s_idx == 0:
            starts.append(timing.start)
        elif timing.letters and letters and letter_idx < len(timing.letters):
            starts.append(max(timing.letters[letter_idx][0], starts[-1]))
        else:
            # No letter times (word was moved) or a syllable without letters: share by letter count.
            done = sum(len(x) for x in word.letters[:s_idx])
            total = max(1, len(word.flat_letters))
            starts.append(max(timing.start + (timing.end - timing.start) * done / total, starts[-1]))
        letter_idx += len(letters)
    ends = starts[1:] + [timing.end]
    return [(s, max(e, s + 0.02)) for s, e in zip(starts, ends)]


def align_lyrics_to_emissions(lyrics_text: str, log_probs: np.ndarray, offset: float = 0.0,
                              pitch_data: Optional[dict] = None, snap_voice: bool = True,
                              loudness_db: Optional[np.ndarray] = None, language: str = "en") -> List[dict]:
    """Syllable timings for `lyrics_text` from the aligner's (frames × 31) log-probabilities.

    `offset` is the time of frame 0 in seconds. With `pitch_data` (from detect_pitches) and
    `snap_voice`, word starts move to where singing begins. With `loudness_db` (per frame, see
    `frame_loudness`), no syllable is placed where the vocals are silent.
    """
    words = lyric_words(lyrics_text, language)
    if not words:
        return []
    targets, owners = build_targets(words)
    if not targets:
        raise AlignmentError("The lyrics have no letters to align.")
    log_probs = np.asarray(log_probs, dtype=np.float32)
    if loudness_db is not None:
        log_probs = gate_silence(log_probs, loudness_db)
    log_probs = with_star_column(log_probs)
    path = forced_align(log_probs, targets)
    timings = word_timings(path, log_probs, targets, owners, words, offset)

    # Words without letters: right after the previous word.
    for i, timing in enumerate(timings):
        if timing is None:
            prev_end = next((t.end for t in reversed(timings[:i]) if t is not None), offset)
            next_start = next((t.start for t in timings[i + 1:] if t is not None), prev_end + 0.1)
            timings[i] = WordTiming(prev_end, max(prev_end + 0.02, min(prev_end + 0.1, next_start)), 0.0)

    for line_index in sorted({w.line_index for w in words}):
        pull_in_edges([t for w, t in zip(words, timings) if w.line_index == line_index])

    if snap_voice and pitch_data is not None:
        from services.pitch_detection import CONFIDENCE_THRESHOLD
        voiced = (np.asarray(pitch_data["midi_notes"]) > 0) & (np.asarray(pitch_data["confidences"]) >= CONFIDENCE_THRESHOLD)
        voiced_times = np.asarray(pitch_data["times"])[voiced]
        for timing in timings:
            snap_to_voice(timing, voiced_times)

    results = []
    for word, timing in zip(words, timings):
        confidence = float(np.exp(timing.score))
        low = timing.score < LOW_CONFIDENCE_SCORE
        for syllable, (start, end) in zip(word.syllables, _syllable_spans(word, timing)):
            results.append({
                "syllable": syllable["text"],
                "start": start,
                "end": end,
                "confidence": confidence,
                "is_rap": syllable.get("is_rap", False),
                "method": "ctc",
                "line_index": word.line_index,
                "split_method": "char" if timing.letters else "proportional",
                "low_confidence": low,
            })
    # Keep notes in order and without overlap.
    for prev, cur in zip(results, results[1:]):
        if cur["start"] < prev["start"]:
            cur["start"] = prev["start"]
        if prev["end"] > cur["start"]:
            prev["end"] = max(prev["start"] + 0.01, cur["start"])
        if cur["end"] <= cur["start"]:
            cur["end"] = cur["start"] + 0.02
    return results


# ────────────────────────────────────────────────────────────
# Models (slow part)
# ────────────────────────────────────────────────────────────
_model_cache: dict = {}


def _load_model(device: str):
    if device not in _model_cache:
        import torch
        from transformers import Wav2Vec2ForCTC
        log_step("CTC_ALIGN", f"Loading aligner {MODEL_ID}@{MODEL_REVISION[:8]} on {device}")
        model = Wav2Vec2ForCTC.from_pretrained(MODEL_ID, revision=MODEL_REVISION, torch_dtype=torch.float32)
        _model_cache[device] = model.to(device).eval()
    return _model_cache[device]


def is_model_downloaded() -> bool:
    """Whether the default (sung) aligner is in the Hugging Face cache (no network access)."""
    try:
        from huggingface_hub import try_to_load_from_cache
        path = try_to_load_from_cache(SUNG_MODEL_ID, SUNG_MODEL_FILE, revision=SUNG_MODEL_REVISION)
        # Size check: on Windows a failed hardlink can leave an empty snapshot file.
        return isinstance(path, str) and os.path.isfile(path) and os.path.getsize(path) == SUNG_MODEL_BYTES
    except Exception:
        return False


def download_model() -> None:
    """Download the pinned default aligner into the Hugging Face cache."""
    from huggingface_hub import hf_hub_download
    hf_hub_download(SUNG_MODEL_ID, SUNG_MODEL_FILE, revision=SUNG_MODEL_REVISION)


def _cache_key(audio_path: str, revision: str) -> str:
    stat = os.stat(audio_path)
    raw = f"{os.path.abspath(audio_path)}|{stat.st_size}|{stat.st_mtime_ns}|{revision}"
    return hashlib.sha1(raw.encode()).hexdigest()


def _sung_session():
    if "sung" not in _model_cache:
        import onnxruntime
        from huggingface_hub import hf_hub_download
        path = hf_hub_download(SUNG_MODEL_ID, SUNG_MODEL_FILE, revision=SUNG_MODEL_REVISION)
        log_step("CTC_ALIGN", f"Loading sung aligner {SUNG_MODEL_ID}@{SUNG_MODEL_REVISION[:8]}")
        _model_cache["sung"] = onnxruntime.InferenceSession(path, providers=["CPUExecutionProvider"])
    return _model_cache["sung"]


def compute_emissions(audio_path: str, device: str = "cpu", cache_dir: Optional[str] = None,
                      model_name: str = "sung") -> np.ndarray:
    """The aligner's (frames × 31) log-probabilities for the audio, one frame per 20 ms.

    Runs in 30 s windows with 2 s of context on each side. With `cache_dir`, results are cached
    per file (path, size, modification time) so re-generating a song is fast. `model_name`: "sung"
    (default, the singing fine-tune) or "mms" (the stock speech model, for comparison).
    """
    revision = SUNG_MODEL_REVISION if model_name == "sung" else MODEL_REVISION
    cache_path = None
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, f"emissions_{_cache_key(audio_path, revision)}.npy")
        if os.path.isfile(cache_path):
            return np.load(cache_path)

    import librosa

    audio, _ = librosa.load(audio_path, sr=SAMPLE_RATE, mono=True)
    window = WINDOW_SEC * SAMPLE_RATE
    context = CONTEXT_SEC * SAMPLE_RATE
    total_frames = max(1, int(np.ceil(len(audio) / SAMPLES_PER_FRAME)))
    padded_len = int(np.ceil(len(audio) / window)) * window
    padded = np.concatenate([np.zeros(context, np.float32), audio.astype(np.float32),
                             np.zeros(padded_len - len(audio) + context, np.float32)])
    keep = window // SAMPLES_PER_FRAME
    skip = context // SAMPLES_PER_FRAME

    chunks = []
    windows = padded_len // window
    log_step("CTC_ALIGN", f"Emissions ({model_name}) for {len(audio) / SAMPLE_RATE:.1f}s in {windows} windows")
    if model_name == "sung":
        session = _sung_session()
        for k in range(windows):
            # Raw audio, no normalisation (as the model card says).
            chunk = padded[k * window:k * window + window + 2 * context]
            logits = session.run(["logits"], {"audio": chunk[None]})[0][0]
            shifted = logits - logits.max(axis=-1, keepdims=True)
            log_probs = shifted - np.log(np.exp(shifted).sum(axis=-1, keepdims=True))
            chunks.append(log_probs[skip:skip + keep].astype(np.float32))
    else:
        import torch
        model = _load_model(device)
        with torch.inference_mode():
            for k in range(windows):
                chunk = padded[k * window:k * window + window + 2 * context]
                # Same normalisation as Wav2Vec2FeatureExtractor(do_normalize=True).
                chunk = (chunk - chunk.mean()) / np.sqrt(chunk.var() + 1e-7)
                logits = model(torch.from_numpy(chunk)[None].to(device)).logits[0]
                log_probs = torch.log_softmax(logits.float(), dim=-1).cpu().numpy()
                chunks.append(log_probs[skip:skip + keep])
    emissions = np.concatenate(chunks)[:total_frames]
    if emissions.shape[0] < total_frames:
        pad = np.full((total_frames - emissions.shape[0], emissions.shape[1]), -1e4, np.float32)
        pad[:, BLANK] = 0.0
        emissions = np.concatenate([emissions, pad])
    if cache_path:
        np.save(cache_path, emissions)
    return emissions


def frame_loudness(audio_path: str) -> np.ndarray:
    """Loudness of the audio in dBFS per emission frame (20 ms)."""
    import librosa
    audio, _ = librosa.load(audio_path, sr=SAMPLE_RATE, mono=True)
    rms = librosa.feature.rms(y=audio, frame_length=2 * SAMPLES_PER_FRAME, hop_length=SAMPLES_PER_FRAME, center=True)[0]
    return 20 * np.log10(rms + 1e-9)


def align_lyrics(audio_path: str, lyrics_text: str, pitch_data: Optional[dict] = None,
                 device: str = "cpu", cache_dir: Optional[str] = None, snap_voice: bool = False,
                 language: str = "en") -> List[dict]:
    """Syllable timings for the user's lyrics in `audio_path`. Same format as `align_whisper()`.

    `snap_voice` is off by default: on the evaluation songs it made starts later than the charts
    (bias +40 ms) without fixing any misplaced notes. See eval/run_eval.py.
    """
    emissions = compute_emissions(audio_path, device=device, cache_dir=cache_dir)
    results = align_lyrics_to_emissions(lyrics_text, emissions, pitch_data=pitch_data, snap_voice=snap_voice,
                                        loudness_db=frame_loudness(audio_path), language=language)
    low = sum(1 for r in results if r["low_confidence"])
    log_step("CTC_ALIGN", f"Aligned {len(results)} syllables, {low} low confidence")
    return results
