# Instructions for Claude

Read `README.md` first. It explains the concept, the audio source options and their trade-offs, the data model, and the gotchas we already hit.

Short version:
- Static browser game: `index.html` (all logic) plus `songs.js` (data). No build step, no dependencies, must work from `file://`.
- Only songs with an `sc` field are picked as answers (`PLAYABLE`), so clips always start at the beginning. Songs without `sc` stay in `SONGS` for the guess search. If a SoundCloud track fails, the game takes another song (daily: a spare song for today, `shift` saved in the daily state). Tim does not want Deezer previews played: they start mid-song.
- Audio: songs with an `sc` field (SoundCloud track page URL, optional `start` offset in seconds) play clips from the start of the full track through a hidden SoundCloud widget, and the widget plays the whole song on the reveal. Deezer previews are never played: songs without `sc` are never answers, and a failing SoundCloud track is replaced by another song. Deezer is only used for track IDs and for checking song length in the tools.
- Never store expiring URLs (Deezer preview URLs, SoundCloud stream URLs). Only Deezer track IDs and SoundCloud track page URLs.
- After editing `songs.js`, run `python3 tools/verify_songs.py` (needs internet) and make sure every line is OK. When `sc` links change, also run `python3 tools/verify_sc.py` (Playwright; set `CHROME=/usr/bin/google-chrome` in the sandbox).
- The sandbox's Chrome has no Widevine: DRM SoundCloud tracks (most official uploads) cannot be played there. Say so, and point the user to `tools/sc_check.html` in a real browser. Never claim a DRM track was verified by playback.
- SoundCloud picks: official upload first, fan upload only where the official one is a 30s `SNIP`, missing, or a different version. Length should match Deezer within a few seconds. `tools/find_sc.py` applies these rules and audio-matches non-DRM candidates; review its report (rips such as game-radio uploads can look official) before `--apply`.
- Gameplay rule: after a skip or wrong guess, the first ▶ plays only the newly unlocked part (previous clip end to new clip end); later presses play from the start. Keep this when touching playback.
- Gameplay rule: a wrong guess by the right artist (any shared artist, compared with the game's `norm()`) is shown in yellow (`.slot.artist`, 🟨 in share text).
- The SoundCloud iframe must keep `allow="autoplay; encrypted-media"`.
- Test the page with headless Chrome or Playwright on `file://`.
- UI text stays in Ukrainian. Songs in `songs.js` must be by Ukrainian artists (any language: Стрыкало, Потап и Настя, MOZGI etc. belong here even when they sing in Russian). Ёлка counts as Ukrainian; ВИА Гра, Лолита, Ярослав Евдокимов do not. Tim's own picks (e.g. from his playlists) are added even if less famous.
- `songs_ru.js` (`SONGS_RU`) and `songs_en.js` (`SONGS_EN`) store songs by non-Ukrainian artists in Russian and English for a planned language mode (Ukrainian / Russian / English / mix). They are NOT loaded by `index.html`; never add them to the game unless Tim asks. Same format as `songs.js`; `id` may be null when a track is not on Deezer.
- Workflow: commit and push to GitHub after every change (each step, not only at the end). Work on the open PR branch, never push to main.
- Daily song: only **append** to `songs.js`. The daily schedule is keyed by each song's position, so appending songs or adding `sc` links moves only a few days, but reordering or deleting entries reshuffles it for everyone. The saved daily state stores the song `id`; keep that when touching it.
