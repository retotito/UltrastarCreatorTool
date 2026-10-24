# YouTube Import (Step 1)

> **Status:** Current · **Last updated:** 2026-10-23

Paste a YouTube link in Step 1's **Full Mix** card instead of uploading a file and press **⬇ Download**: the app
downloads **only the audio** as the full mix. Vocal separation and everything after work as with an uploaded file.

Uploads and downloads look the same: a window with a spinner and progress blocks the page until the file is there,
then "Which song is this?" asks for artist, title and language(s), and the card shows the file as
"Artist - Title.wav". **Cancel** stops it: for YouTube, closing the event stream makes the backend kill yt-dlp
(`download_audio(..., cancelled)`) and remove the partial download (and the new session's folder). **🗑 Delete** on
the card removes the file to upload or download another one.

## What is saved in the session

| Field | From |
|---|---|
| `original_audio` | the best audio stream, converted to 44.1 kHz WAV like an upload |
| `artist`, `title` | YouTube Music's own fields, else "Artist – Title" in the video title (labels like "(Official Video)" removed), else the channel name. A new download always replaces them as the proposal for the song window |
| `language` | the uploader's setting, else the language of YouTube's original automatic captions (`xx-orig`); often unknown |
| `youtube_url` | written as the `#YOUTUBE` header on export |
| `youtube_thumbnail` | thumbnail URL (for a cover later) |

Artist and title are a proposal: Step 1 then opens "Which song is this?" (`SongNameModal.svelte`), which checks
the video title against lrclib.net (`services/song_identify.py`) and lets the user correct the names and choose the
language, plus an optional second one (`language2`; written as `#LANGUAGE:English, German` by
`services/ultrastar.py` `language_header`). Uploaded files
get the same window (names from their tags and file name). Step 2 searches LRCLIB only when asked, with the
confirmed names.

## Subtitles as lyrics (Step 2)

Songs imported from YouTube get a **YouTube** tab on each side of Step 2. "Load subtitles" asks
`/api/youtube-subtitles/{id}`: the video's tracks (`services/youtube.py` `subtitle_tracks`), best first, written by
the uploader (in the song's language first), then YouTube's automatic captions in the language it heard
(`-orig`; speech recognition, weak on singing). yt-dlp fetches only the chosen track as WebVTT (`--skip-download`),
`vtt_to_lyrics` makes lyrics lines of it (no timings, tags, "♪", "[Music]"; a line repeated by rolling captions
once). With several tracks the tab offers a choice.

The **import** already loads the uploader's subtitles (not the automatic captions) right after the audio: they
fill the left side's YouTube tab, which Step 2 then shows first (`lyrics_sources.tabs.left = "youtube"`).

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
- Lyrics shown only in the picture (burned in) can't be read; that would need text recognition on the video.
