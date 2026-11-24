#!/usr/bin/env python3
"""Check every song in a song list: Deezer track exists, has a preview, and show title/artist for a sanity check.
Usage: python3 tools/verify_songs.py              (songs.js, the list the game uses)
       python3 tools/verify_songs.py songs_ru.js  (stored Russian list, not used by the game yet)
Songs with "id": null (not on Deezer) are listed as NOTE and do not count as problems."""
import json, re, sys, time, urllib.request, pathlib

name = sys.argv[1] if len(sys.argv) > 1 else "songs.js"
src = (pathlib.Path(__file__).parent.parent / name).read_text(encoding="utf-8")
songs = json.loads(re.search(r"const SONGS\w* = (\[.*\]);", src, re.S).group(1))
bad, seen, missing = 0, set(), 0

def fetch(i):
    for k in range(5):   # Deezer answers {"error": {"code": 4, "message": "Quota limit exceeded"}} when hit too fast
        d = json.load(urllib.request.urlopen("https://api.deezer.com/track/%d" % i, timeout=20))
        if (d.get("error") or {}).get("code") == 4: time.sleep(2 + k * 2); continue
        return d
    return d

for s in songs:
    if s.get("id") is None:
        print("NOTE no Deezer id |", s["t"], "|", s["a"]); missing += 1; continue
    if s["id"] in seen:
        print("DUPLICATE", s["id"], s["t"]); bad += 1
    seen.add(s["id"])
    try:
        d = fetch(s["id"])
    except Exception as e:
        print("ERR ", s["id"], s["t"], e); bad += 1; continue
    ok = "error" not in d and d.get("preview")
    if not ok: bad += 1
    print("OK " if ok else "BAD", s["id"], "|", s["t"], "|", s["a"], "=>", d.get("title"), "|", (d.get("artist") or {}).get("name"))
print("%d songs, %d problems%s" % (len(songs), bad, ", %d without Deezer id" % missing if missing else ""))
sys.exit(1 if bad else 0)
