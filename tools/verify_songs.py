#!/usr/bin/env python3
"""Check every song in songs.js: Deezer track exists, has a preview, and show title/artist for a sanity check.
Usage: python3 tools/verify_songs.py"""
import json, re, sys, urllib.request, pathlib

src = (pathlib.Path(__file__).parent.parent / "songs.js").read_text(encoding="utf-8")
songs = json.loads(re.search(r"const SONGS = (\[.*\]);", src, re.S).group(1))
bad, seen = 0, set()
for s in songs:
    if s["id"] in seen:
        print("DUPLICATE", s["id"], s["t"]); bad += 1
    seen.add(s["id"])
    try:
        d = json.load(urllib.request.urlopen("https://api.deezer.com/track/%d" % s["id"], timeout=20))
    except Exception as e:
        print("ERR ", s["id"], s["t"], e); bad += 1; continue
    ok = "error" not in d and d.get("preview")
    if not ok: bad += 1
    print("OK " if ok else "BAD", s["id"], "|", s["t"], "|", s["a"], "=>", d.get("title"), "|", (d.get("artist") or {}).get("name"))
print("%d songs, %d problems" % (len(songs), bad))
sys.exit(1 if bad else 0)
