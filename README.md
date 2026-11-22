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
6. [Recommended path](#recommended-path)
7. [Win reveal: playing the whole song](#win-reveal-playing-the-whole-song)
8. [Data model and editing songs](#data-model-and-editing-songs)
9. [Choosing songs](#choosing-songs)
10. [Working on this with Claude](#working-on-this-with-claude)
11. [Gotchas we already hit](#gotchas-we-already-hit)
12. [Legal notes](#legal-notes)
13. [TODO / ideas](#todo--ideas)

## Run it

Open `index.html` in a browser (double-click is enough). Internet is required: clips come from the Deezer API at runtime. Works from `file://`, so no local server is needed. To share it, GitHub Pages or any static host works the same way.

## The concept

- **Goal:** recognise a song from the shortest possible clip.
- **Loop:** play clip, type a guess (autocomplete over the known song list), submit or skip. Wrong or skipped means the next clip is longer. Six tries, then the answer is revealed.
- **Audience:** people who know Ukrainian music. So the list is *iconic* songs most people recognise, not deep cuts.
- **Modes:**
  - **Daily:** everyone gets the same song on a given day. Picked by a deterministic shuffle (seeded RNG) indexed by the date, so no server is needed. Result is kept in `localStorage`.
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
| `tools/verify_songs.py` | Check every song still resolves with a preview. |

Audio flow today (Deezer):
1. `songs.js` stores only a Deezer **track ID** per song.
2. On each round the page asks Deezer for that track via **JSONP** (a `<script>` tag with `?output=jsonp&callback=...`). JSONP is used because Deezer's API sends no CORS headers, and JSONP also works from `file://`.
3. The response contains a fresh 30 second `preview` MP3 URL. These URLs are signed and expire, so they must never be stored in `songs.js`.
4. If the track lookup fails, it falls back to a Deezer search by artist and title.
5. An `<audio>` element plays from 0s and a `requestAnimationFrame` loop stops it at the unlocked length.

**Known limitation:** a Deezer preview is a fixed 30s excerpt chosen by Deezer, usually from the middle of the song. So the "1 second clip" is not the intro, it is a random-feeling moment from the middle. This is the main weakness versus Songless and lessgames, which (as far as we can tell) play from the start of the real track.

## The core problem: where does the audio come from

Everything else in this game is easy. The hard part is getting audio that:
1. starts at a known position (ideally 0:00, or a per-song offset we choose),
2. is legal to use,
3. can be controlled precisely from JavaScript (start, stop at 1s, 2s, ...),
4. works for Ukrainian music (catalogue coverage),
5. does not break after a few weeks (expiring URLs, API changes).

No single source is perfect. Below is every option we considered.

## Audio source options

### 1. Deezer 30s previews (current)
- **How:** public API, JSONP, preview MP3 per track.
- **Pros:** no API key, no account, works from `file://`, great catalogue of Ukrainian artists, trivially verifiable (`tools/verify_songs.py`), precise `<audio>` control.
- **Cons:** only 30s, excerpt is from the middle of the track and we cannot choose where. URLs expire (handled by fetching at runtime). Needs internet and Deezer staying open.
- **Verdict:** best for getting started and a good fallback. Not "from the start".

### 2. SoundCloud Widget API (promising, not built yet)
- **How:** embed `https://w.soundcloud.com/player/?url=<track url>` in an `<iframe>`, load SoundCloud's widget JS, then control it with `widget.play()`, `widget.pause()`, `widget.seekTo(ms)`, `widget.getPosition()` and events (`READY`, `PLAY`, `PLAY_PROGRESS`).
- **Pros:** plays the **full track** from any position, so clips can start at 0:00 or at a chosen offset. Very likely what lessgames uses (not confirmed, their page text does not say; check with DevTools, Network tab, filter `soundcloud`). Also gives the win reveal for free (see below).
- **Cons:**
  - Each song needs a SoundCloud URL and we cannot verify them automatically from the Claude sandbox, someone has to open each in a browser.
  - Coverage is uneven: official uploads exist for many modern artists and labels, but old classics may only exist as random re-uploads. Some uploads have embedding disabled.
  - The widget is an iframe, so seeking has some latency. The 1 second clip will not be as tight as a local `<audio>` element unless we pre-buffer (play muted and pause before the round starts).
  - Possible ads on the widget, and mobile browsers restrict autoplay (needs a user tap, which we already have).
  - SoundCloud API changes and registration for client IDs have been restrictive for years. The embed widget itself needs no key.
- **Verdict:** best option for real "from the start" clips. Do it incrementally (see Recommended path).

### 3. YouTube IFrame Player API
- **How:** hidden `<iframe>` player, `player.seekTo(startSeconds)`, `player.playVideo()`, stop with a timer. Needs a video ID per song.
- **Pros:** widest coverage of any source, every Ukrainian song has an official video or audio upload. Full track, any start offset. Official, legal embedding.
- **Cons:** the player must stay visible enough in the DOM, some videos block embedding, ads can play first, autoplay rules, and seeking has latency. Running from `file://` can fail with an embedding error because there is no proper origin, so use GitHub Pages or a local server. Videos get deleted or region blocked, so IDs rot.
- **Verdict:** best coverage, worst precision for 1s clips. Good as a per-song fallback when SoundCloud has nothing.

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
- **Verdict:** avoid for commercial releases.

### 7. Deezer widget embed (reveal only)
- Deezer offers an embeddable iframe player (`widget.deezer.com`). It plays 30s for anonymous users. Could be shown on the reveal screen next to the Deezer link, but it does not give us timing control.

### Comparison

| Source | Starts at 0:00 / chosen offset | Precise 1s clips | Ukrainian coverage | Needs per-song work | Works from `file://` |
|---|---|---|---|---|---|
| Deezer preview | No (middle excerpt) | Yes | Good | Track ID only (verifiable by script) | Yes |
| SoundCloud widget | Yes | Medium (iframe latency) | Uneven | Track URL (manual check) | Yes |
| YouTube IFrame | Yes | Medium to low | Excellent | Video ID (manual check) | Often no |
| iTunes preview | No | Yes | Medium | Search only | Yes |
| Spotify embed | Partly | No | Good | Track ID | n/a |
| Own files | Yes | Yes | n/a | Rights needed | Yes |

## Recommended path

1. **Keep Deezer as the default** so the game always works.
2. **Add an optional per-song `sc` field** (SoundCloud track URL) and an optional `start` (seconds offset). If a song has `sc`, play it through the SoundCloud widget from `start`; otherwise use Deezer. Mixed lists are fine.
3. Start with 10 to 15 very famous songs, test how the first-second latency feels, then decide whether to go all in.
4. Optionally add a `yt` field (YouTube video ID) as a second fallback for songs without a SoundCloud upload, hosted on GitHub Pages rather than `file://`.
5. Pre-buffer: load and seek the widget before the round starts, so pressing play starts instantly.

Sketch of the extended data model:

```js
{ id: 106383746, t: "Вставай", a: "Океан Ельзи", al: "Okean Elzy",
  sc: "https://soundcloud.com/okeanelzy/vstavay",  // optional, plays from start
  start: 0 }                                          // optional offset in seconds
```

## Win reveal: playing the whole song

On lessgames, after you guess correctly you hear the whole song in an embedded SoundCloud block. We want the same:

- **With SoundCloud:** on win (and on loss), show the SoundCloud widget (or just unhide it) and call `widget.seekTo(0); widget.play()`. Nothing extra is needed, since the full track is already available through the same widget.
- **Without SoundCloud (today):** the reveal screen plays the 30s preview and links to the full track on Deezer.
- **Alternative reveal:** a YouTube embed or a Spotify embed iframe, which both play the full song, can be used purely as a reveal block even if clips use Deezer.

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

Workflow:

```
python3 tools/find_song.py "Скрябін Кохана"   # prints candidate lines with IDs and rank
python3 tools/verify_songs.py                 # every ID must say OK
```

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
- Aim for a list large enough that the daily mode does not repeat quickly. Currently 110 songs, so the daily song cycles about every 3.5 months.

Ideas for more: add a `tier` (1 = everybody knows, 2 = well known) and a difficulty selector.

## Working on this with Claude

This repo is built to be worked on with Claude (Claude Code or Claude chat). Context a new session needs:

**What the project is:** a static browser game. All logic is in `index.html`, data in `songs.js`. Do not introduce a build step unless there is a strong reason.

**Facts Claude should know (learned the hard way):**
- Claude's sandbox can reach `api.deezer.com`, so Deezer IDs can be checked with `tools/verify_songs.py`. It could **not** reach `itunes.apple.com` (blocked), and it cannot verify SoundCloud or YouTube URLs. Those must be checked in a real browser.
- Claude can drive a headless Chrome with Playwright to test the page, and `file://` works for the page.
- Hosted "artifact" pages (e.g. inside claude.ai) block `fetch` and remote audio, so the game cannot run there. Test locally or on GitHub Pages.
- The game must work offline from `file://`, hence JSONP for Deezer and a separate `songs.js` instead of `fetch("songs.json")`.

**Handy prompts:**
- "Add 20 more iconic Ukrainian songs from the 80s and 90s to `songs.js`, verify them with `tools/verify_songs.py`."
- "Implement the optional `sc` field using the SoundCloud Widget API, falling back to Deezer when it is missing. Keep the 1, 2, 4, 8, 15, 30 second ladder."
- "On win, show the full song in an embedded player instead of the 30s preview."
- "Add difficulty tiers and a selector."
- "Add stats and streaks stored in `localStorage`."

**Conventions:**
- Keep `songs.js` as plain `const SONGS = [...]`, one song per line, so diffs are readable.
- Run `python3 tools/verify_songs.py` before every commit that touches songs.
- No dependencies. Keep UI text in Ukrainian.

## Gotchas we already hit

- **Expiring preview URLs:** never store them. Resolve at runtime.
- **CORS:** Deezer's API has none, use JSONP (`output=jsonp&callback=fn`).
- **Autoplay:** browsers only allow audio after a user gesture. Playback starts from the play button.
- **Clip timing:** stop the clip using `audio.currentTime` in a `requestAnimationFrame` loop, not `setTimeout`, for accuracy.
- **Deezer 30s preview is from the middle of the track.** See the core problem above.
- **Search matching:** Cyrillic is normalised (`и`, `ї` to `і`, `ґ` to `г`, apostrophes removed) and Latin input is transliterated, including `y` after a vowel meaning `й`.
- **Deezer titles can be oddly spelled** (for example the Latin `i` in "Квiти"), so keep display titles in `songs.js` clean.

## Legal notes

- Using official previews and embeds, linking back to the platform, is the safe route.
- Do not host copyrighted recordings in this repo.
- Credit Deezer, SoundCloud or YouTube where their audio or players are used. The page footer already says previews are from Deezer.
- This is a fan project, not legal advice. If it becomes public or commercial, check each platform's terms of use for the APIs and embeds you rely on.

## TODO / ideas

- [ ] SoundCloud widget support with optional `sc` and `start` fields (see Recommended path)
- [ ] Full-song reveal on win
- [ ] YouTube fallback (`yt` field), hosted on GitHub Pages
- [ ] Difficulty tiers (very famous, well known)
- [ ] Statistics and streaks
- [ ] More songs, 200 or more
- [ ] GitHub Pages deployment
- [ ] Hint mode: show the artist or the decade after N wrong guesses
- [ ] Artist-guess mode
