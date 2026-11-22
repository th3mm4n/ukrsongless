#!/usr/bin/env python3
"""Find Deezer track IDs and print ready-to-paste songs.js lines.
Usage: python3 tools/find_song.py "Океан Ельзи Вставай"
Then fix the title/artist spelling and add the Latin artist name in "al"."""
import json, sys, urllib.parse, urllib.request

q = " ".join(sys.argv[1:])
d = json.load(urllib.request.urlopen("https://api.deezer.com/search?limit=8&q=" + urllib.parse.quote(q), timeout=20))
for t in d.get("data", []):
    if not t.get("preview"): continue
    print(json.dumps({"id": t["id"], "t": t["title"], "a": t["artist"]["name"], "al": t["artist"]["name"]}, ensure_ascii=False) + ",  // rank", t["rank"], "|", t["album"]["title"])
