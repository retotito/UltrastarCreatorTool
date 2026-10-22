# YouTube Import (Step 1)

> **Status:** Current · **Last updated:** 2026-10-22

Paste a YouTube link in Step 1's **Full Mix** card instead of uploading a file. The app shows the video (thumbnail,
title, channel, length, and the artist/title it found), then downloads **only the audio** as the full mix. Vocal
separation and everything after work as with an uploaded file.

## What is saved in the session

| Field | From |
|---|---|
| `original_audio` | the best audio stream, converted to 44.1 kHz WAV like an upload |
| `artist`, `title` | YouTube Music's own fields, else "Artist – Title" in the video title (labels like "(Official Video)" removed), else the channel name. Only set if the session has none yet |
| `language` | the uploader's setting, else the language of YouTube's original automatic captions (`xx-orig`); often unknown |
| `youtube_url` | written as the `#YOUTUBE` header on export |
| `youtube_thumbnail` | thumbnail URL (for a cover later) |

Artist and title are a proposal: Step 1 then opens "Which song is this?" (`SongNameModal.svelte`), which checks
the video title against lrclib.net (`services/song_identify.py`) and lets the user correct the names. Uploaded files
get the same window (names from their tags and file name). Step 2's automatic LRCLIB search waits until the names
are confirmed (`song_confirmed`).

## Tools: yt-dlp and QuickJS

`backend/services/download_tools.py` downloads them on first use into the app's data folder (`tools/`; in dev
`backend/tools/`, gitignored):

- **yt-dlp** ("onedir" zip from the latest GitHub release; starts fast) and **QuickJS-ng** (the JavaScript runtime
  yt-dlp needs for YouTube's checks), both verified against GitHub's SHA-256 digest.
- They are not bundled because YouTube changes often and an old yt-dlp stops working. When a download fails for a
  reason that isn't the video itself, the app updates yt-dlp and tries once more.
- Without network the installed version is kept.

## Safety

- Only an 11-character video id reaches yt-dlp, after `--`; links are checked against YouTube's hosts
  (`services/youtube.py` `video_id`), so nothing typed can become a yt-dlp option.
- yt-dlp runs with `--ignore-config`, `--no-playlist` and only the bundled QuickJS (`--no-js-runtimes`).
- The UI notes that users should only download songs they have the right to use (YouTube's terms forbid downloads).

## Errors

`services/youtube.py` `explain` turns yt-dlp's errors into messages: private, age-restricted, members-only, not
available in your country, live, removed, no network, "confirm you're not a bot".

## Not (yet) done

- No video download (not needed for charting).
- Lyrics: YouTube's automatic captions are speech recognition and not better than Whisper on singing, so they are
  only used for the language. Captions written by the uploader are listed (`subtitle_languages`) but not used yet;
  Step 2 should offer them next to the LRCLIB suggestions.
