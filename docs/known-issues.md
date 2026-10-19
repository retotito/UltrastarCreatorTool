# Known Issues & Future Improvements

> **Status:** Current · **Last updated:** 2026-04-07

## Alignment Issues

> **Since forced alignment (2026-10-19)** issues 1 and 2 below are much reduced: the aligner times the typed lyrics
> against the vocals instead of matching Whisper's transcript, so missed words no longer get guessed positions.
> Gypsy Woman: 75 % → 8 % misplaced syllables. What remains: long repetitive vocalise ("la la dee", "ooh") can
> drift by a few seconds until the next clearly sung words, especially when the typed syllables differ from what is
> sung, and backing vocals that repeat the lead can pull words by about a second. Lines the aligner is unsure about
> are counted as "to check" in the processing summary.

### 1. Repetitive nonsense syllables (La-da-dee, Ah!, etc.)
**Status**: Known limitation
**Songs affected**: Crystal Waters - Gypsy Woman
**Symptom**: WhisperX either skips these sections entirely or merges them into compound words like "Ladadee". The gap-fill algorithm redistributes them by energy detection, but timing can be off by several seconds.
**Possible fixes**:
- [ ] Compound word splitting in `_match_words()` — detect when WhisperX returns "Ladadee" and split to match individual lyrics syllables "La", "da", "dee"
- [ ] Phoneme-based duration estimation for unmatched sections
- [ ] Lower WhisperX confidence threshold to capture low-confidence detections

### 2. Time-shifted sections after large gaps
**Status**: Known limitation
**Songs affected**: Crystal Waters - Gypsy Woman (35s-48s gap, 48s-53s compressed to 2s)
**Symptom**: When WhisperX misses a large section, subsequent matched words get their correct WhisperX timestamps, but the unmatched lyrics in between get compressed or misplaced.
**Possible fixes**:
- [ ] Global alignment pass that considers audio energy across the full track
- [ ] Allow the gap-fill algorithm to "steal" time from adjacent matched sections when gaps are unreasonably small

### 3. WhisperX limitations with singing
**Status**: By design (WhisperX trained on speech, not singing)
**Symptom**: Vocal melisma, sustained notes, and non-word vocalizations are poorly transcribed.
**Notes**: Not fixable without fine-tuning Whisper on singing data (major effort). Current workaround: manual correction in piano roll editor.

---

## Detailed Test Cases

### Case 1: Crystal Waters - Gypsy Woman (She's Homeless)

**WhisperX transcription** (what it actually detected):
```
She still wakes up early every morning just to do her hair now because she cares y'all.
Her day I wouldn't be right without her makeup.
She's never had her makeup.
She's just like you and me but she's homeless.
She's homeless.
As she stands there, singing for money In my sleep I see her begging, reaching police
Although the fault is not mine, I ask not why, not why She's just like you and me, but she's homeless, she's homeless
And she said they're singing for money La-da-dee, la-da-da-dow
She's just like you and me As she stands there singing for money La la dee la do da La la dee la do da La la dee la do da La la dee la do da La la dee la do da
Ah!
Ah!
Ah!
Ah!
uh uh uh
Ah!
Ah!
Ah!
```

**Correct lyrics** (user-corrected, with hyphenation):
```
She still wakes up ear-ly ev-er-y morn-ing
just to do her hair now
be-cause she cares y'all

Her day I would-n't be right
with-out her make-up.
She's nev-er had her make-up.

She's just like you and me
but she's home-less.
She's home-less.

As she stands there, sing-ing for mon-ey

La-da-dee, la-da-da-dow  (x6 lines)

In my sleep I see her beg-ging, reach-ing po-lice
Al-though the fault is not mine,
I ask not why, not why
She's just like you and me,
but she's home-less, she's home-less

And she said they're sing-ing for mon-ey

La-da-dee, la-da-da-dow  (x10 lines)

She's just like you and me
As she stands there sing-ing for mon-ey

La-da-dee, la-da-da-dow  (x12 lines)

Ah!  (x16 lines)

La-da-dee, la-da-da-dow  (x8 lines)

Ah!  (x12 lines)
```

**Specific timing problems**:
- **35s–48s**: First "La-da-dee" chorus (6 lines, ~36 syllables). WhisperX returned compound words "La-da-dee," and "la-da-da-dow" as single tokens. Gap fill placed them but timing was rough.
- **48s–53s**: Verse "In my sleep I see her begging..." was compressed to ~2s. Should span ~5s. Caused by the preceding gap consuming too much time.
- **~76s–120s (43.8s gap)**: WhisperX had compound "Ladadee" at 75.7s that didn't match individual syllables. Later individual "La" words at 119s matched instead, creating massive gap.
- **~144s–208s (63.2s gap)**: Lyrics order vs audio order mismatch for repeated chorus sections.

**Root causes**:
1. WhisperX merges "La-da-dee" into compound words → no match with individual syllable lyrics
2. Sequential matching with lookahead can't handle repeated identical sections
3. Gap-fill energy detection works but can't distinguish between different "La-da-dee" choruses

**Debug files generated**: `alignment_whisper_debug_pre_gap_fill.txt`, `alignment_whisper_debug_post_gap_fill.txt` in `backend/downloads/`

---

## Testing Log

| Song | Artist | Issues | Severity | Notes |
|------|--------|--------|----------|-------|
| She's Only Happy in the Sun | Ben Harper | First word half-beat offset | Minor | BPM 178 (89 real). Metronome half-beat toggle helped verify. |
| Gypsy Woman | Crystal Waters | Repetitive "La da dee" sections misaligned | Major | ~30 "La-da-dee" lines + ~20 "Ah!" lines. WhisperX recognized <10%. See detailed case above. |

---

## Editor Wishlist
- [ ] Undo history viewer (show list of undo states)
- [ ] Snap-to-grid toggle (currently always snaps)
- [ ] Waveform zoom (independent of note zoom)
- [ ] Pitch bend visualization
