# Впізнай пісню · UA

A Songless-style guessing game for iconic Ukrainian songs. You hear a very short clip, guess the song, and every wrong guess or skip unlocks a longer clip (1s, 2s, 4s, 8s, 15s, 30s). Six attempts.

Single static page. No build step, no backend, no dependencies.

Reference games this is modelled on:
- https://songless.pro/ru/unlimited
- https://lessgames.com/songless

## Table of contents

1. [Run it](#run-it)
2. [The concept](#the-concept)
3. [How it works now](#how-it-works-now)
4. [The core problem: where does the audio come from](#the-core-problem-where-does-the-audio-come-from)
5. [Audio source options](#audio-source-options)
6. [Decision and what was measured](#decision-and-what-was-measured)
7. [Win reveal: playing the whole song](#win-reveal-playing-the-whole-song)
8. [Data model and editing songs](#data-model-and-editing-songs)
9. [Choosing songs](#choosing-songs)
10. [Working on this with Claude](#working-on-this-with-claude)
11. [Gotchas we already hit](#gotchas-we-already-hit)
12. [Legal notes](#legal-notes)
13. [TODO / ideas](#todo--ideas)

## Run it

Open `index.html` in a browser (double-click is enough). Internet is required: clips come from SoundCloud (full track, from the start) or, for songs without a SoundCloud link, from Deezer previews. Both work from `file://`, so no local server is needed. To share it, GitHub Pages or any static host works the same way.

## The concept

- **Goal:** recognise a song from the shortest possible clip.
- **Loop:** play clip, type a guess (autocomplete over the known song list), submit or skip. Wrong or skipped means the next clip is longer. Six tries, then the answer is revealed.
- **Right artist:** a wrong guess by the same artist (any shared artist in a collab) shows as a yellow slot marked ≈, with the status line "Виконавець правильний, пісня ні." Share text uses 🟨 for it.
- **Only from the beginning:** only songs with a SoundCloud link are picked as answers. If a link fails to play, the game takes another song ("Ця пісня зараз не грає, беремо іншу…"; daily: the next song in today's order) instead of playing the Deezer preview, which starts mid-song. Songs without SoundCloud can still be guessed.
- **New part first:** right after a skip or wrong guess, the first ▶ plays only the newly unlocked part (e.g. 1s to 2s); every ▶ after that plays from the start (0 to 2s). The status line says so. Not saved across reloads: after a reload ▶ plays from the start.
- **Audience:** people who know Ukrainian music. So the list is *iconic* songs most people recognise, not deep cuts.
- **Modes:**
  - **Daily:** everyone gets the same song on a given day (the date is taken in Kyiv time, so it switches at the same moment everywhere). No server: days are grouped into fixed 100-day cycles and each cycle orders all songs with a seeded "inside-out" shuffle keyed by their position in `songs.js`. Appending songs, or adding a SoundCloud link to an existing song, changes at most a day or two per cycle, so today's song almost never moves. Reordering or deleting entries does reshuffle the schedule. If a day's song has no SoundCloud link, or its link fails to play, a song from outside the cycle's 100 slots is used instead. The result is kept in `localStorage` together with the song ID, so saved progress for a different song is ignored.
  - **Unlimited:** random song each round, avoiding the last 30.
- **Search box:** accepts Cyrillic or Latin (`vstavay`, `boombox`, `shchedryk`). Latin is transliterated to Cyrillic, and each song also has a Latin artist alias.
- **Share:** copies an emoji result (green, red, black squares) to the clipboard.

Why the 1s, 2s, 4s, 8s, 15s, 30s ladder: early clips are nearly impossible and reward real fans, later clips make it fair. The progress bar uses a square-root scale so the short clips are still visible.

## How it works now

Files:

| File | Purpose |
|---|---|
| `index.html` | The whole game: UI, game logic, matching, audio. Plain JS, no framework. |
| `songs.js` | `const SONGS = [...]`, the single source of truth for songs. |
| `tools/find_song.py` | Search Deezer, print paste-ready `songs.js` lines. |
| `tools/verify_songs.py` | Check every song still resolves with a Deezer preview. |
| `tools/verify_sc.py` | Check every `sc` link in headless Chrome: loads, full track (not a 30s snip), length vs Deezer, and a 1s play for non-DRM tracks. Needs Playwright. |
| `songs_ru.js`, `songs_en.js` | Russian- and English-language songs (`SONGS_RU`, `SONGS_EN`), same format as `songs.js`. **Not loaded by the game.** Stored for a planned language mode: Ukrainian, Russian, English or a mix. `id` is null for the few tracks not on Deezer; no SoundCloud links yet. |
| `tools/find_sc.py` | Find SoundCloud tracks for songs without `sc`, following the picking rules, and audio-match non-DRM candidates to the Deezer recording. Writes a JSON report; `--apply` adds the picks to `songs.js`. Needs Playwright, numpy, ffmpeg. |
| `tools/sc_check.html` | Open in a real browser: plays the first second of every `sc` track (cold and buffered) and reports timing. The only way to verify DRM tracks. |

Each round picks one of two audio engines:

**SoundCloud engine** (song has an `sc` field):
1. `songs.js` stores the SoundCloud **track page URL** (stable, no expiring tokens) and an optional `start` offset in seconds.
2. The round loads the SoundCloud widget in an invisible iframe (`height:0`, the widget shows the title so it must stay hidden). The iframe has `allow="autoplay; encrypted-media"`.
3. On `READY` the page reads the track metadata. A `SNIP` policy (30s preview for non-subscribers) or an unstreamable track means fallback to Deezer.
4. Pre-buffer: after the first tap anywhere on the page (a user gesture is needed for sound), the widget plays muted from `start`, and as soon as the position moves it pauses and rewinds. This cuts the first-play delay from about 0.9s to about 25ms.
5. A clip: `seekTo(start)`, `play()`, then `PLAY_PROGRESS` events report the real track position. The clip is armed only once the position actually advances (stale events from before the seek, and a stream that never decodes, both report a fixed position). The clip stops when `position - start >= clip length`, so start latency never shortens the clip. A `requestAnimationFrame` loop moves the progress head, extrapolating at most 250ms past the last event.
6. If the clip never starts (9s, or 3s if the muted warm-up already stalled), or stalls for 5s mid-clip, the round switches to the Deezer preview and tells the player.

**Deezer engine** (no `sc`, or SoundCloud failed):
1. `songs.js` stores only a Deezer **track ID** per song.
2. On each round the page asks Deezer for that track via **JSONP** (a `<script>` tag with `?output=jsonp&callback=...`). JSONP is used because Deezer's API sends no CORS headers, and JSONP also works from `file://`.
3. The response contains a fresh 30 second `preview` MP3 URL. These URLs are signed and expire, so they must never be stored in `songs.js`.
4. If the track lookup fails, it falls back to a Deezer search by artist and title.
5. An `<audio>` element plays from 0s and a `requestAnimationFrame` loop stops it at the unlocked length.

**Known limitation of the Deezer engine:** a Deezer preview is a fixed 30s excerpt chosen by Deezer. Matching previews against full tracks showed it starts about 48s into the song, so the "1 second clip" is not the intro. This is why songs are being migrated to the SoundCloud engine.

## The core problem: where does the audio come from

Everything else in this game is easy. The hard part is getting audio that:
1. starts at a known position (ideally 0:00, or a per-song offset we choose),
2. is legal to use,
3. can be controlled precisely from JavaScript (start, stop at 1s, 2s, ...),
4. works for Ukrainian music (catalogue coverage),
5. does not break after a few weeks (expiring URLs, API changes).

No single source is perfect. Below is every option we considered.

## Audio source options

### 1. Deezer 30s previews (fallback)
- **How:** public API, JSONP, preview MP3 per track.
- **Pros:** no API key, no account, works from `file://`, great catalogue of Ukrainian artists, trivially verifiable (`tools/verify_songs.py`), precise `<audio>` control.
- **Cons:** only 30s, and the excerpt starts about 48s into the track. We cannot choose where. URLs expire (handled by fetching at runtime).
- **Verdict:** fallback for every song without a working SoundCloud link.

### 2. SoundCloud Widget API (chosen, built)
- **How:** embed `https://w.soundcloud.com/player/?url=<track url>` in an `<iframe>`, load `https://w.soundcloud.com/player/api.js`, control it with `play()`, `pause()`, `seekTo(ms)`, `setVolume()` and events (`READY`, `PLAY`, `PAUSE`, `PLAY_PROGRESS`, `FINISH`). No API key needed.
- **Pros:** full track from any position, works from `file://`, precise once buffered (see measurements below), and the same widget is the full-song reveal.
- **Cons:**
  - SoundCloud tracks come in three kinds (`getCurrentSound()` tells which):
    - **Plain HLS stream** (`monetization_model` `BLACKBOX`, `NOT_APPLICABLE`, sometimes `AD_SUPPORTED`): plays anywhere, including the Claude sandbox.
    - **DRM stream** (`cbc/ctr-encrypted-hls`, most official label uploads, `AD_SUPPORTED`): needs Widevine (Chrome, Firefox, Edge) or FairPlay (Safari) and `encrypted-media` on the iframe. Plays in normal browsers, not in the sandbox's Chrome for Testing.
    - **`SNIP`** (`SUB_HIGH_TIER`): only 30s for non-Go+ listeners. Useless. Some major official uploads are only this kind (Go_A's Eurovision "SHUM", Ruslana's "Wild Dances", Jamala's "1944").
  - Where the official upload is a snip or missing, only fan re-uploads remain. They can be taken down and may be a different recording, so match them to the Deezer recording (see Data model).
  - Not checked yet: whether DRM tracks ever get an audio ad before the track in the widget, and whether a phone's lock screen or media notification shows the track title while a clip plays (that would spoil the answer).
- **Verdict:** chosen. See the next section.

### 3. YouTube IFrame Player API
- **How:** `<iframe>` player, `player.seekTo(startSeconds)`, `player.playVideo()`. Needs a video ID per song.
- **Pros:** widest coverage. Official uploads exist for every one of the first 15 songs, all embeddable (checked with the oEmbed endpoint).
- **Cons (measured or checked):**
  - From `file://` the player fails with **Error 153** ("video player configuration error"). Needs GitHub Pages or a local server.
  - The player must stay visible (YouTube API policies, minimum 200x200), and it shows the title and thumbnail, which spoils the guess. Hiding or covering it breaks the policy.
  - Official channel videos are monetized and can play a pre-roll ad first, fatal for a 1s clip.
  - Official music videos often have non-music intros, so every song would need a `start` offset.
  - Headless Chrome in the Claude sandbox could load the player but YouTube never streamed the video (bot protection on datacenter IPs), so timing could not be measured here.
- **Verdict:** not for clips. Possible later as a reveal-only fallback for songs with no SoundCloud upload, on GitHub Pages.

### 4. iTunes Search API previews
- **How:** `https://itunes.apple.com/search?term=...&media=music` returns a 30s `previewUrl`. Supports JSONP via `callback=`.
- **Pros:** no key, easy.
- **Cons:** also a 30s excerpt, usually from the middle, so it has the same problem as Deezer. Catalogue of Ukrainian music is smaller. (Note: in the Claude sandbox this host was blocked by the proxy, so it could not be tested there. It should work from a normal browser.)
- **Verdict:** only useful as an extra fallback if Deezer lacks a track.

### 5. Spotify
- **Previews:** `preview_url` was removed for new apps in late 2024. Do not build on it.
- **Embed iframe + iFrame API:** works, plays 30s for logged-out users and the full track for logged-in Premium users. Controls are limited and clips cannot be timed reliably.
- **Verdict:** not suitable for the guessing clips. Could be used for a "listen on Spotify" link on the reveal screen.

### 6. Self-hosted audio files
- **How:** put MP3 snippets in the repo or a bucket.
- **Pros:** full control, perfect timing, offline.
- **Cons:** **copyright.** Hosting copyrighted recordings without a licence is not OK, even short clips. Only use it for music you have rights to (e.g. public domain recordings or artists who give permission).
- **Note:** this is what lessgames.com/songless does for its guessing clips (checked in the Network tab, Nov 2026): it loads `cdn.lessgames.com/songs/<id>.aac`, about 17s clips, and uses a SoundCloud widget (`api.soundcloud.com/tracks/<id>`, `auto_play=true`) only for the reveal after the round.
- **Verdict:** avoid for commercial releases.

### 7. Deezer widget embed (reveal only)
- Deezer offers an embeddable iframe player (`widget.deezer.com`). It plays 30s for anonymous users. Could be shown on the reveal screen next to the Deezer link, but it does not give us timing control.

### Comparison

| Source | Starts at 0:00 / chosen offset | Precise 1s clips | Ukrainian coverage | Needs per-song work | Works from `file://` |
|---|---|---|---|---|---|
| Deezer preview | No (starts ~48s in) | Yes | Good | Track ID only (verifiable by script) | Yes |
| SoundCloud widget | Yes | Yes once buffered (~25ms start, stops within ~15ms) | Official uploads for most big artists, some only as 30s snips | Track URL (metadata by script, DRM playback in a real browser) | Yes |
| YouTube IFrame | Yes | Unmeasured; ads and visible-player rule | Excellent | Video ID | No (Error 153) |
| iTunes preview | No | Yes | Medium | Search only | Yes |
| Spotify embed | Partly | No | Good | Track ID | n/a |
| Own files | Yes | Yes | n/a | Rights needed | Yes |

## Decision and what was measured

**Decision (Nov 2026):** SoundCloud widget for clips and for the full-song reveal, Deezer as the per-song fallback. Track choice: the **official upload first**; a fan upload only where the official one is a 30s snip, missing, or a different version from the famous one. YouTube not used for clips.

Measured in headless Chrome (Playwright), playable SoundCloud tracks:

| | `http://localhost` | `file://` |
|---|---|---|
| Widget loads and plays | yes | yes |
| First play, cold | ~0.9s until audio | ~0.9s |
| Next plays (buffered) | ~25ms | ~10-25ms |
| 1s clip stops at | 1001-1016ms of track time | 1003-1014ms |

Inside the game: 1s, 2s and 4s clips stopped at 0.998s, 1.994s and 3.996s of track time. In the second round, with the muted pre-buffer, click-to-audio was 122ms. A DRM track that cannot decode falls back to Deezer after about 3s.

**Real browser (desktop Chrome on Windows, NL, not logged in to SoundCloud, Nov 2026):**
- `tools/sc_check.html` logic: **15 of 15 OK**, including all 9 DRM tracks. Cold start 1.1-1.7s for DRM tracks (licence request), ~0.5s for plain streams; buffered start 20-24ms for all; 1s clips stopped at 1000-1015ms. No ads heard or seen (an ad would show up as a long cold start).
- The game with Вставай (DRM), real clicks, second round so pre-buffered: 1s/2s/4s clips stopped at 0.986s/2.008s/3.999s, click to audio 276ms for the first clip, ~40ms after. Win reveal showed the widget and played from 0:00.
- In a real browser `policy` reads `MONETIZE` for these tracks (the sandbox saw other values such as `ALLOW`); the game only rejects `SNIP` and `BLOCK`.

Still not verified:
- **Firefox and Safari**, and **phones**: run `tools/sc_check.html` there.
- **Phones:** whether the lock screen or media notification shows the song title during a clip, and whether the muted warm-up is silent on iOS (iOS ignores `setVolume`).

Status of the first migration (15 songs): see TODO.

## Win reveal: playing the whole song

On lessgames, after the round you hear the whole song in an embedded SoundCloud block. This game does the same (built):

- **SoundCloud songs:** on win and on loss the hidden widget is expanded above the result card and plays the whole track from 0:00. `finish()` always runs from a click (guess or give up), so the browser allows sound. The "▶ Уся пісня" button and the big ▶ toggle play and pause, and the widget's own controls work too. A finished daily round that is reloaded shows the widget without autoplay. Links go to SoundCloud and Deezer.
- **Deezer songs:** the reveal plays the 30s preview and links to the full track on Deezer, as before.
- **Possible later:** a YouTube or Spotify embed as a reveal-only block for songs without a SoundCloud upload.

## Data model and editing songs

`songs.js` is the single source of truth:

```js
const SONGS = [
 {"id":106383746,"t":"Вставай","a":"Океан Ельзи","al":"Okean Elzy"},
 ...
];
```

| Field | Meaning |
|---|---|
| `id` | Deezer track ID. Unique. Never store preview URLs, they expire. |
| `t` | Title as shown to the player. |
| `a` | Artist as shown. |
| `al` | Latin artist name, only used for search. |
| `sc` | Optional. SoundCloud **track page URL** (`https://soundcloud.com/<user>/<track>`, no query string). Clips play from the start of this full track. Never store stream URLs, they expire. |
| `start` | Optional. Offset in seconds into the SoundCloud track where clips start (e.g. to skip a silent intro). The reveal always plays from 0:00. Ignored by the Deezer fallback. |

Example:

```js
{"id": 106383746, "t": "Вставай", "a": "Океан Ельзи", "al": "Okean Elzy", "sc": "https://soundcloud.com/okieanielzi/vstavaj"}
```

Workflow:

```
python3 tools/find_song.py "Скрябін Кохана"   # prints candidate lines with IDs and rank
python3 tools/verify_songs.py                 # every Deezer ID must say OK
python3 tools/verify_sc.py                    # every sc link: loads, full track, length vs Deezer
# then open tools/sc_check.html in a real browser for DRM tracks
```

Picking a SoundCloud track:
- Search `https://soundcloud.com/search/sounds?q=<artist> <title>` in Cyrillic and Latin. Official artist accounts often have unusual slugs (`okieanielzi`, `skriabin-scmusic`, `bumboks-music`), so look at the uploader name, not the slug.
- Prefer the official upload. Skip anything `SNIP` (`tools/verify_sc.py` flags it).
- The length should be within a few seconds of the Deezer track (`verify_sc.py` warns at more than 8s). A big difference usually means a remix, live or radio edit.
- For fan uploads, check it is the same recording. `tools/find_sc.py` does this automatically for non-DRM candidates by correlating log spectrograms with the Deezer preview (same recording: r of 0.65-0.97, usually 0.8+; different recording: ~0.4). DRM candidates cannot be decoded in the sandbox, so they are only accepted when official and within 5s of the Deezer length.
- `tools/find_sc.py` ranks: official (uploader name matches the artist, or a label-distributed `AD_SUPPORTED`/`MONETIZE` upload with the artist in the title) first, then closest length, then play count. It rejects titles with remix, live, cover, karaoke, sped up, nightcore and similar words.

Deezer's metadata sometimes differs from what we show (for example "(Radio Edit)" suffixes). Show the clean title in `t`.

Tips for finding things on Deezer:
- Search in Cyrillic and in Latin, results differ a lot.
- An artist's top tracks are at `https://api.deezer.com/artist/<artistId>/top?limit=40` (artist ID from `https://api.deezer.com/search/artist?q=...`). The `rank` field is a rough popularity score.
- Prefer the original recording. Folk songs have hundreds of versions, pick the one most people know.

## Choosing songs

Rules we used:
- The bar is "most Ukrainians would recognise it", not "good song".
- A mix of decades and genres: classics and folk, 90s rock, 2000s pop, Eurovision, recent hits.
- Ukrainian language preferred. Skip Russian-language songs by Ukrainian artists.
- Duplicated titles are fine (e.g. two songs called "Люди"), the autocomplete shows the artist next to the title.
- Aim for a list large enough that the daily mode does not repeat quickly. Each 100-day daily cycle draws 100 songs without repeats, so a larger list means songs come back less often.

Ideas for more: add a `tier` (1 = everybody knows, 2 = well known) and a difficulty selector.

## Working on this with Claude

This repo is built to be worked on with Claude (Claude Code or Claude chat). Context a new session needs:

**What the project is:** a static browser game. All logic is in `index.html`, data in `songs.js`. Do not introduce a build step unless there is a strong reason.

**Facts Claude should know (learned the hard way):**
- Claude's sandbox can reach `api.deezer.com`, so Deezer IDs can be checked with `tools/verify_songs.py`. It could **not** reach `itunes.apple.com` (blocked in an earlier session).
- As of Nov 2026 the sandbox reaches soundcloud.com, the widget and YouTube. Headless Chrome (`/usr/bin/google-chrome`, Chrome for Testing) can search SoundCloud, load the widget and play **non-DRM** tracks, so `tools/verify_sc.py` works there. It has **no Widevine**, so DRM tracks (most official uploads) never play in the sandbox. YouTube loads but never streams video to the sandbox. Those must be checked in a real browser (`tools/sc_check.html`).
- Claude can drive a headless Chrome with Playwright to test the page, and `file://` works for the page. Songs can be forced in a test with `SONGS.splice(0, SONGS.length, ...SONGS.filter(s => s.t === "Stefania"))` before clicking the Безліміт tab.
- Hosted "artifact" pages (e.g. inside claude.ai) block `fetch` and remote audio, so the game cannot run there. Test locally or on GitHub Pages.
- The game must work offline from `file://`, hence JSONP for Deezer and a separate `songs.js` instead of `fetch("songs.json")`.

**Handy prompts:**
- "Add 20 more iconic Ukrainian songs from the 80s and 90s to `songs.js`, verify them with `tools/verify_songs.py`."
- "Add `sc` links for the next 20 songs in `songs.js`, official uploads first, run `tools/verify_sc.py` and report which have no usable upload."
- "Add difficulty tiers and a selector."
- "Add stats and streaks stored in `localStorage`."

**Conventions:**
- Keep `songs.js` as plain `const SONGS = [...]`, one song per line, so diffs are readable.
- Only **append** new songs at the end of `songs.js`. Reordering or deleting entries reshuffles the daily schedule for everyone.
- Run `python3 tools/verify_songs.py` before every commit that touches songs, and `python3 tools/verify_sc.py` when `sc` links change.
- No dependencies. Keep UI text in Ukrainian.

## Gotchas we already hit

- **Expiring preview URLs:** never store them. Resolve at runtime.
- **CORS:** Deezer's API has none, use JSONP (`output=jsonp&callback=fn`).
- **Autoplay:** browsers only allow audio after a user gesture. Playback starts from the play button.
- **Clip timing:** stop the clip using `audio.currentTime` in a `requestAnimationFrame` loop, not `setTimeout`, for accuracy.
- **Deezer 30s preview is from the middle of the track.** See the core problem above.
- **Search matching:** Cyrillic is normalised (`и`, `ї` to `і`, `ґ` to `г`, apostrophes removed) and Latin input is transliterated, including `y` after a vowel meaning `й`.
- **Deezer titles can be oddly spelled** (for example the Latin `i` in "Квiти"), so keep display titles in `songs.js` clean.
- **SoundCloud iframe needs `allow="autoplay; encrypted-media"`.** Without `encrypted-media`, DRM tracks fail with "Permissions policy violation: encrypted-media is not allowed".
- **Stale widget events:** after `seekTo()`, `PLAY_PROGRESS` can still report the old position, and a stream that cannot decode reports the start position forever. Arm a clip only when the position is near `start` and has advanced.
- **`AD_SUPPORTED` is not the same as DRM.** Check `media.transcodings[].format.protocol` for `encrypted-hls` (Один в каное "Човен" is `AD_SUPPORTED` but plain HLS).
- **`SNIP` tracks** play 30s only and report `duration: 30000`. Skip them.
- **The widget shows the title and artwork**, so during a round it is kept at `height:0` (not `display:none`, so it still loads and plays) and only expanded on reveal.
- **Pre-buffering needs a user gesture.** It runs after the first tap anywhere on the page, so the very first clip of a visit has ~0.9s start delay. The clip length is still correct because it is measured in track time.

## Legal notes

- Using official previews and embeds, linking back to the platform, is the safe route.
- Do not host copyrighted recordings in this repo.
- Credit Deezer, SoundCloud or YouTube where their audio or players are used. The page footer names SoundCloud and Deezer, and the reveal shows the SoundCloud player with its branding plus links to both.
- This is a fan project, not legal advice. If it becomes public or commercial, check each platform's terms of use for the APIs and embeds you rely on.

## TODO / ideas

- [x] SoundCloud widget support with optional `sc` and `start` fields, Deezer fallback
- [x] Full-song reveal on win and loss
- [x] After a skip or wrong guess the first ▶ plays only the new part, later presses from the start
- [x] Imported Tim's YouTube Music playlist "123" (653 tracks, 645 loaded; YouTube Music hides unavailable ones), sorted by the language of the song:
  - **Ukrainian: 46 new songs added to the game** (20 more were already in it). 147 songs now, 141 on SoundCloud. All 45 new SoundCloud links (15 DRM) played in desktop Chrome; `start` offsets for 5 with silent intros. Only Кульбаби (official upload is a 30s snip) and the 5 earlier ones stay on Deezer.
  - Not added: Gogol Bordello - П'ята авеню and Qarpa - Виживи (not on Deezer), Борис Сичевський - Ти ж мене підманула (same song as the existing Підманула by Воплі Відоплясова; two versions would be confusing in a guessing game).
  - **Russian: 281 songs stored in `songs_ru.js`**, including Ukrainian artists who sing in Russian. Время и Стекло - Дим and АСАФАТОV - Заведу кота carry a `note`: language not confirmed. 3 without a Deezer id.
  - **English: 233 songs stored in `songs_en.js`.** 2 without a Deezer id (Adele - Hello is not on Deezer).
  - Not stored: 39 tracks in other languages or instrumentals (Rammstein, Stromae, PSY, Shakira, Daft-Punk-style instrumentals, etc.).
  - Ukrainian-language songs from the playlist are added even when less famous: they are Tim's picks.
- [x] Imported Tim's Spotify playlists "націоналісточка" (120) and "Українська бімба" (195), raw lists in `data/playlists/`: 114 Ukrainian songs added to the game (261 total), 70 Russian to `songs_ru.js`. Skipped: remixes and live duplicates of songs already in the game, 4 songs not on Deezer, 2 tracks of unknown language, 1 instrumental.
- [x] SoundCloud links for the Spotify-playlist songs: 245 of 261 songs now on SoundCloud. 16 have no usable upload and play Deezer previews (official is a 30s snip, or only remixes/other versions exist).
- [x] Real-browser check of the 105 SoundCloud links from the Spotify import: all 105 played in desktop Chrome (Nov 24). Note: checking many links in a row makes SoundCloud throttle for a while (a block of consecutive "did not play"); re-run only the failures a few minutes later before concluding a link is broken.
- [x] Silent-intro `start` offsets measured for the 68 non-DRM links of that import (21 set). DRM tracks cannot be measured in the sandbox.
- [x] Fixed: DZIDZIO Павук/Ялта were gachi "right version" mashups (Павук replaced, Ялта has no normal upload), Wellboy Вишні was the New Year version (replaced).
- [ ] Language mode: let the player choose Ukrainian, Russian, English or a mix (data is ready in `songs_ru.js` and `songs_en.js`; add SoundCloud links with `tools/find_sc.py` first)
- [x] Removed on request (Nov 2026): Wild Dances, 1944, Фортеця Бахмут, Heart of Steel, Gravity, Under the Ladder, Чуєш мамо, Стожари, Прірва. Do not re-add them.
- [x] First 15 songs migrated to SoundCloud: Вставай, Обійми, Люди як кораблі, Вахтерам, Червона рута, Щедрик, Stefania, Shum, Wild Dances, 1944, Плакала, Човен, Весна, Журавлі, Dancing Lasha Tumbai
  - Official uploads: 11 (Shum is Go_A's official radio edit, 183s, not the 172s Eurovision cut, which is a 30s snip on SoundCloud. Щедрик is the official Хор Гомін recording, not the Viter recording that Deezer has.)
  - Fan uploads, matched to the Deezer recording: Wild Dances, 1944 (official is a 30s snip), Червона рута (no verified official account), Плакала (the only official upload is a 2022 re-recording)
  - Stefania: KALUSH's official upload is a different edit from the Deezer one (same song)
- [x] Verify the 9 DRM tracks in a real browser: all 15 OK in desktop Chrome (Windows)
- [ ] Same check in Firefox, Safari and on a phone
- [ ] Check on a phone whether the media notification or lock screen shows the song title during a clip
- [x] Remaining songs migrated with `tools/find_sc.py`: **105 of 110 songs now on SoundCloud** (64 DRM, 41 plain; after removing 9 songs on request: 96 of 101). All 105 played in desktop Chrome (Windows) with `tools/sc_check.html` logic; 4 failed once in a row and passed on a re-run, so a rare transient failure is possible (the game then falls back to Deezer).
  - Fan uploads (official is a snip, missing, or a different version; all audio-matched to Deezer): Квіти в волоссі, Бета-каротин, Розпрягайте хлопці коней, Понад хмарами, Файне місто Тернопіль, Роксоляна, Ой у вишневому саду, Плакала, Червона рута
  - Official but a different version from Deezer: У мене немає дому (230s vs 198s, 14s quiet intro, so `start: 13.7`), Два кольори (320s vs 273s), Shum, Stefania, Щедрик
  - `start` offsets for silent intros: У мене немає дому, Молоком, Не йди, Плакала, Гуцулка Ксеня, Три хвилини, Човен (measured on plain streams only; DRM tracks could not be measured)
  - **Stay on Deezer, no usable upload:** Україно (Петриненко) and Стільникове кохання, Пливе кача (official uploads are 30s snips only), Свята (KAZKA: only remixes and an acoustic version), Ніч яка місячна (no Солов'яненко recording on SoundCloud)
- [ ] Maybe: YouTube or Spotify embed as a reveal-only block for songs with no SoundCloud upload (YouTube needs GitHub Pages)
- [ ] Difficulty tiers (very famous, well known)
- [ ] Statistics and streaks
- [ ] More songs, 200 or more
- [ ] GitHub Pages deployment
- [ ] Hint mode: show the artist or the decade after N wrong guesses
- [ ] Artist-guess mode
