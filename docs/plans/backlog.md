# Backlog

> **Status:** Current · **Last updated:** 2026-10-25

Open ideas and tasks that aren't planned in detail yet. When one is started, it gets its own plan in this folder
(or goes straight into the code if it is small) and is removed here.

## Before publishing

- **Duets**: planned in [duets.md](duets.md).
- **About / Credits view in the app**: the models, their authors and licences (non-commercial for the aligner and
  GAME), not only in the README.
- **Windows build test** of the current branch, and an old Intel Mac.

## Editor

- **Set VIDEOGAP button**, like the Set END button: pick the position in the editor and write `#VIDEOGAP`. No video
  in the editor.
- **`#START`** (where the game starts playing, to skip an intro): a Set START mode like Set END. Not decided yet
  whether it is worth it.

## Pipeline

- "good-bye" is still too short.
- "favorite" should be split fa-vo-rite.
- Compare our pitches with Tune Studio's on more songs.
- GAME isn't fully deterministic between runs.
- RoFormer: timing on "Roxanne", and its speed.
- Try Tune Studio's syllable-start head (`boundary.onnx`, mirrored in Retotito/ultrastar-models) for syllable starts.
- Later, trained locally on the user's own computer: our own timing head, published in a separate repository
  (not in the mirror).

## Later

- GitHub Actions builds (when publishing).
- Text recognition for lyrics burned into a video.
