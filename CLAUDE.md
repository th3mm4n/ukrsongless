# Instructions for Claude

Read `README.md` first. It explains the concept, the audio source options and their trade-offs, the data model, and the gotchas we already hit.

Short version:
- Static browser game: `index.html` (all logic) plus `songs.js` (data). No build step, no dependencies, must work from `file://`.
- Audio currently comes from Deezer 30s previews via JSONP. Never store preview URLs, only Deezer track IDs.
- After editing `songs.js`, run `python3 tools/verify_songs.py` (needs internet) and make sure every line is OK.
- Test the page with headless Chrome or Playwright on `file://`.
- UI text stays in Ukrainian. Songs must be iconic, widely known, Ukrainian-language.
