# Instructions for Claude

Read `README.md` first. It explains the concept, the audio source options and their trade-offs, the data model, and the gotchas we already hit.

Short version:
- Static browser game: `index.html` (all logic) plus `songs.js` (data). No build step, no dependencies, must work from `file://`.
- Audio: songs with an `sc` field (SoundCloud track page URL, optional `start` offset in seconds) play clips from the start of the full track through a hidden SoundCloud widget, and the widget plays the whole song on the reveal. Songs without `sc`, or whose SoundCloud track fails, use Deezer 30s previews via JSONP.
- Never store expiring URLs (Deezer preview URLs, SoundCloud stream URLs). Only Deezer track IDs and SoundCloud track page URLs.
- After editing `songs.js`, run `python3 tools/verify_songs.py` (needs internet) and make sure every line is OK. When `sc` links change, also run `python3 tools/verify_sc.py` (Playwright; set `CHROME=/usr/bin/google-chrome` in the sandbox).
- The sandbox's Chrome has no Widevine: DRM SoundCloud tracks (most official uploads) cannot be played there. Say so, and point the user to `tools/sc_check.html` in a real browser. Never claim a DRM track was verified by playback.
- SoundCloud picks: official upload first, fan upload only where the official one is a 30s `SNIP`, missing, or a different version. Length should match Deezer within a few seconds.
- The SoundCloud iframe must keep `allow="autoplay; encrypted-media"`.
- Test the page with headless Chrome or Playwright on `file://`.
- UI text stays in Ukrainian. Songs must be iconic, widely known, Ukrainian-language.
