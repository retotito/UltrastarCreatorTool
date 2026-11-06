# Backlog

> **Status:** Current · **Last updated:** 2026-11-06

Open ideas and tasks that aren't planned in detail yet. When one is started, it gets its own plan in this folder
(or goes straight into the code if it is small) and is removed here.

## Before publishing

- **Duets**: planned in [duets.md](duets.md).
- **About / Credits view in the app**: the models, their authors and licences (non-commercial for the aligner and
  GAME), not only in the README.
- **Windows build test** of the current branch, and an old Intel Mac.

## Website

- **Two new tutorials** (5.0 and duets): they go first in `website/index.html`. Then mark the part of the older videos
  about Step 2 as outdated: in version 4 the alignment ignored manual corrections to the lyrics, and that's no longer so.
- **Replace the old tutorials**: the old videos stay on the website until new ones exist. Before an old video is deleted
  from YouTube, remove it from `website/index.html` and `README.md`, or its link breaks.

## Editor

- Check that **mic sing-along** and **vocal trace** (pitch hits against the notes) are still accurate; they are
  months old.
- **Set PREVIEW button** (`#PREVIEWSTART`), like Set END. Low priority: the game picks a preview position by itself.

## Pipeline

- **Romanized Chinese/Japanese lyrics aren't split into syllables**: for `zh`/`ja` the hyphenation is "one syllable
  per character", so pinyin or romaji words become one note each ("arigatou", "zhongguo"). Use syllable rules when
  the text is Latin: pinyin's ~400 fixed syllables (zhong-guo, xie-xie), romaji's (C)V units with "n" and double
  consonants (a-ri-ga-tou, ki-t-te). Alignment itself is fine with romanized lyrics.
- Songs in other scripts (Chinese/Japanese characters especially) are aligned through uroman's romanization, which
  is rough: measure the timing on a few songs.

- "good-bye" is still too short.
- "favorite" should be split fa-vo-rite.
- Compare our pitches with Tune Studio's on more songs.
- GAME isn't fully deterministic between runs.
- RoFormer: timing on "Roxanne", and its speed.
- Try Tune Studio's syllable-start head (`boundary.onnx`, mirrored in Retotito/ultrastar-models) for syllable starts.
- Later, trained locally on the user's own computer: our own timing head, published in a separate repository
  (not in the mirror).

## Later

- **Work out `#VIDEOGAP` automatically** when the audio comes from elsewhere: compare the video's sound with the
  song's audio. There is no video in the editor to line it up by eye.
- **Linux without WebKitGTK**: Tauri's Linux web view (WebKitGTK) is the weak spot for audio, keys and drawing
  (silent players, Space delivered twice). Check Tauri's Chromium runtime (`tauri-runtime-cef`, alpha in
  2026-11) once it is stable, or open the app in the system browser on Linux. 5.0 ships without Linux: after the
  fixes (audio endpoint, Space once) playback still didn't work reliably on an Ubuntu 24.04 laptop. The release
  workflow keeps its Linux steps (.deb with GStreamer dependencies) for a later try.
- GitHub Actions builds (when publishing).
- Text recognition for lyrics burned into a video.
