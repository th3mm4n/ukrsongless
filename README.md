# Впізнай пісню · UA

A Songless-style guessing game for iconic Ukrainian songs. Listen to a short clip, guess the song; every wrong guess or skip unlocks a longer clip (1s, 2s, 4s, 8s, 15s, 30s).

Single static page, no build step, no backend.

## Run

Open `index.html` in a browser (double-click is enough). Needs internet: clips are fetched from the Deezer API at runtime.

## Features

- **Daily** mode: same song for everyone each day (deterministic shuffle by date), result saved in `localStorage`.
- **Unlimited** mode: random songs, no quick repeats.
- Autocomplete accepts Cyrillic or Latin input (`vstavay`, `boombox`, `shchedryk`).
- Copyable emoji result.

## How audio works

`songs.js` stores only Deezer track IDs. At runtime the page asks Deezer (JSONP, so it works from `file://`) for a fresh 30s preview URL, because preview URLs expire. If the track lookup fails it falls back to a search by artist and title.

Known limit: Deezer previews are a 30s excerpt chosen by Deezer, usually from the middle of the song, not the start. Real from-the-start clips would need a different audio source (see ideas below).

## Edit the song list

`songs.js` is the single source of truth. Each entry: `id` (Deezer track ID), `t` title, `a` artist as displayed, `al` Latin artist name (search only).

```
python3 tools/find_song.py "Скрябін Кохана"   # find IDs, prints paste-ready lines
python3 tools/verify_songs.py                 # check every ID still resolves with a preview
```

Aim: songs most people know, not deep cuts. Prefer the original/most recognisable version.

## Ideas / TODO

- From-the-start clips (e.g. YouTube IFrame API with per-song start offset)
- Difficulty tiers (very famous / well known)
- Statistics and streaks
- More songs
- Host on GitHub Pages
