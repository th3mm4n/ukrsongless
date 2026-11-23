#!/usr/bin/env python3
"""Find a SoundCloud track for songs in songs.js that have no `sc` yet, following the project rules:
official upload first, fan upload only where the official one is a 30s SNIP, missing, or a different version.

For each song it searches SoundCloud (Cyrillic and Latin queries), drops snips, remixes, live, covers and
tracks whose length differs from Deezer by more than 8s, ranks official/label uploads first, and for
non-DRM candidates checks by audio that it is the same recording as the Deezer preview (correlation of
log spectrograms: same recording r ~0.8-0.95, different ~0.4). DRM candidates cannot be decoded in the
sandbox, so they are accepted only when they look official and the length matches; check those in a real
browser with tools/sc_check.html.

Writes a JSON report; it does not edit songs.js. Apply picks with --apply REPORT.

Needs: playwright (+ Chrome; set CHROME=/path), numpy, ffmpeg.
Usage:
  python3 tools/find_sc.py --out sc_report.json [title-substring ...]
  python3 tools/find_sc.py --apply sc_report.json"""
import asyncio, json, os, pathlib, re, subprocess, sys, tempfile, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).parent.parent
SONGS_JS = ROOT / "songs.js"
MATCH_OK = 0.65      # spectrogram correlation needed to call it the same recording
MAX_LEN_DIFF = 8     # seconds vs Deezer
BAD_WORDS = r"remix|ремікс|ремикс|rmx|live|наживо|концерт|cover|кавер|karaoke|караоке|instrumental|мінус|минус|minus|speed ?up|sped|slowed|nightcore|8d|bass ?boost|mashup|мешап|acoustic|акустик|piano|orchestra version|версия|tribute|reprise|demo|intro|outro|vip"

# ---------- text matching (same rules as the game) ----------
MAP2 = {"shch": "щ", "sh": "ш", "ch": "ч", "zh": "ж", "kh": "х", "ts": "ц", "ya": "я", "yu": "ю", "ye": "є", "yi": "ї", "ie": "є", "iu": "ю", "ia": "я"}
MAP1 = dict(zip("abvhgdezyiklmnoprstufwjqc", "абвггдезиіклмнопрстуфвйкк")); MAP1["x"] = "кс"
def translit(s):
    s = s.lower(); out = ""; i = 0
    while i < len(s):
        if s[i:i+4] == "shch": out += "щ"; i += 4
        elif s[i:i+2] in MAP2: out += MAP2[s[i:i+2]]; i += 2
        elif s[i] == "y" and i and s[i-1] in "aeiou": out += "й"; i += 1
        else: out += MAP1.get(s[i], s[i]); i += 1
    return out
def norm(s):
    s = re.sub(r"[ʼ'’`]", "", s.lower())
    s = s.replace("ґ", "г").replace("и", "і").replace("ї", "і").replace("є", "е").replace("ь", "").replace("ы", "і").replace("э", "е").replace("ё", "е")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9а-яіе ]", " ", s)).strip()
def forms(s): return {norm(s), norm(translit(s))}
def contains(hay, needle):
    hs = forms(hay)
    return any(n and any(n in h for h in hs) for n in forms(needle))

# ---------- audio match ----------
import numpy as np
SR = 8000
def decode(src, out):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-ac", "1", "-ar", str(SR), "-f", "f32le", out], check=True, timeout=240)
    return np.fromfile(out, dtype=np.float32)
def feat(x):
    n, h = 1024, 400
    fr = np.lib.stride_tricks.sliding_window_view(x, n)[::h] * np.hanning(n)
    S = np.abs(np.fft.rfft(fr, axis=1))[:, 5:400]
    edges = np.geomspace(1, S.shape[1], 33).astype(int)
    M = np.stack([S[:, edges[i]:max(edges[i+1], edges[i]+1)].mean(1) for i in range(32)])
    M = np.log(M + 1e-6); M -= M.mean(1, keepdims=True)
    return M
def best_match(full, preview):
    A, B = feat(full), feat(preview)
    q = B[:, 100:400]; qz = (q - q.mean()) / (q.std() + 1e-9); n = qz.size
    best = (-1.0, 0)
    for k in range(0, A.shape[1] - q.shape[1], 2):
        w = A[:, k:k+q.shape[1]]
        r = float(((w - w.mean()) / (w.std() + 1e-9) * qz).sum() / n)
        if r > best[0]: best = (r, k)
    return best[0], best[1] * 0.05 - 5

PROBE = """<!DOCTYPE html><html><body><iframe id="f" allow="autoplay; encrypted-media"></iframe>
<script src="https://w.soundcloud.com/player/api.js"></script><script>
window.R={}; const f=document.getElementById('f');
f.src="https://w.soundcloud.com/player/?auto_play=false&url="+encodeURIComponent(new URLSearchParams(location.search).get('u'));
const w=SC.Widget(f); w.bind(SC.Widget.Events.READY,()=>{R.ready=1;w.setVolume(0);w.play();});
</script></body></html>"""

async def grab_stream(browser, probe_uri, url):
    pg = await browser.new_page(); found = []
    async def on(r):
        try:
            ct = r.headers.get("content-type", "")
            if "json" in ct and ("/stream/" in r.url or "/streams" in r.url or "transcodings" in r.url or "media" in r.url):
                j = await r.json()
                if isinstance(j, dict) and j.get("url"): found.append(j["url"])
            elif "mpegurl" in ct or r.url.split("?")[0].endswith(".m3u8"): found.append(r.url)
        except Exception: pass
    pg.on("response", lambda r: asyncio.ensure_future(on(r)))
    try:
        await pg.goto(probe_uri + "?u=" + urllib.parse.quote(url, safe=""))
        for _ in range(40):
            await pg.wait_for_timeout(250)
            if found: break
    finally:
        await pg.close()
    return found[-1] if found else None

async def search(page, q):
    hits = []
    async def on(r):
        if "api-v2.soundcloud.com/search" in r.url:
            try:
                for t in (await r.json()).get("collection", []):
                    if t.get("kind") == "track": hits.append(t)
            except Exception: pass
    h = lambda r: asyncio.ensure_future(on(r))
    page.on("response", h)
    try:
        await page.goto("https://soundcloud.com/search/sounds?q=" + urllib.parse.quote(q), timeout=60000)
        await page.wait_for_timeout(3500)
    finally:
        page.remove_listener("response", h)
    return hits

def describe(t):
    protos = [x["format"]["protocol"] for x in (t.get("media") or {}).get("transcodings", [])]
    u = t.get("user") or {}
    return {"url": t["permalink_url"], "title": t.get("title", ""), "user": u.get("username", ""), "user_full": u.get("full_name", ""),
            "verified": bool(u.get("verified")), "policy": t.get("policy"), "mon": t.get("monetization_model"),
            "dur": round((t.get("full_duration") or t.get("duration") or 0) / 1000), "plays": t.get("playback_count") or 0,
            "drm": any("encrypted" in p for p in protos), "embed": t.get("embeddable_by"), "streamable": t.get("streamable")}

def artists(song):
    # "alyona alyona & Jerry Heil" -> each name separately
    parts = re.split(r"\s*(?:&|,| feat\.? | ft\.? | x |спільно з)\s*", song["a"] + " & " + (song.get("al") or ""), flags=re.I)
    return [x for x in parts if len(norm(x)) > 2]
def by_artist(c, song):
    who = c["user"] + " " + c["user_full"]
    return any(contains(who, a) for a in artists(song))
def official(c, song):
    if by_artist(c, song): return True
    # label-distributed upload naming the artist in the title (not a rip: rips of game radios etc. are caught by by_artist ranking)
    return c["mon"] in ("AD_SUPPORTED", "MONETIZE", "SUB_HIGH_TIER") and any(contains(c["title"], a) for a in artists(song))

async def process(song, browser, page, probe_uri, work):
    dz = json.load(urllib.request.urlopen("https://api.deezer.com/track/%d" % song["id"], timeout=20))
    dz_dur = dz.get("duration"); rep = {"id": song["id"], "t": song["t"], "a": song["a"], "deezer_dur": dz_dur, "candidates": []}
    seen = {}
    for q in dict.fromkeys([song["a"] + " " + song["t"], (song.get("al") or "") + " " + song["t"]]):
        for t in await search(page, q.strip()):
            seen.setdefault(t["permalink_url"], describe(t))
    cands = []
    for c in seen.values():
        why = []
        if c["policy"] in ("SNIP", "BLOCK") or c["streamable"] is False: why.append("snip/blocked")
        if c["embed"] not in (None, "all"): why.append("no embed")
        if not contains(c["title"], song["t"]): why.append("title")
        if re.search(BAD_WORDS, c["title"], re.I) and not re.search(BAD_WORDS, song["t"], re.I): why.append("variant")
        if dz_dur and abs(c["dur"] - dz_dur) > MAX_LEN_DIFF: why.append("length %s vs %s" % (c["dur"], dz_dur))
        c["official"] = official(c, song); c["by_artist"] = by_artist(c, song)
        c["rejected"] = why
        rep["candidates"].append(c)
        if not why: cands.append(c)
    # the artist's own account first, then other official (label) uploads, then closer length, then plays
    cands.sort(key=lambda c: (not c["by_artist"], not c["official"], abs(c["dur"] - (dz_dur or c["dur"])), -c["plays"]))
    rep["pick"] = None
    preview = None
    for c in cands[:6]:
        if c["drm"]:
            if c["official"] and abs(c["dur"] - (dz_dur or c["dur"])) <= 5:
                rep["pick"] = dict(c, how="official DRM upload (length match, audio not checkable here)"); break
            continue
        if preview is None:
            urllib.request.urlretrieve(dz["preview"], work / "dz.mp3"); preview = decode(str(work / "dz.mp3"), str(work / "dz.raw"))
        stream = await grab_stream(browser, probe_uri, c["url"])
        if not stream: c["match"] = "no stream"; continue
        try: full = decode(stream, str(work / "sc.raw"))
        except Exception as e: c["match"] = "decode failed"; continue
        r, at = best_match(full, preview); c["match"] = round(r, 2); c["preview_at"] = round(at, 1)
        if r >= MATCH_OK:
            rep["pick"] = dict(c, how=("official" if c["official"] else "fan") + " upload, same recording as Deezer (r=%.2f)" % r); break
        if c["official"] and rep.get("official_other_version") is None:
            rep["official_other_version"] = c   # e.g. KALUSH Stefania: official but a different edit
    if not rep["pick"]:
        # the artist's own full upload exists but in a different version (longer/shorter than Deezer): still the official
        # recording of the song, preferred over a fan upload by the project rules
        other = [c for c in rep["candidates"] if c["by_artist"] and c["rejected"] and all(w.startswith("length") for w in c["rejected"])
                 and c["dur"] >= 90]
        if other and not rep.get("official_other_version"):
            rep["official_other_version"] = dict(min(other, key=lambda c: abs(c["dur"] - (dz_dur or c["dur"]))), match="not checked")
    if not rep["pick"] and rep.get("official_other_version"):
        c = rep["official_other_version"]; rep["pick"] = dict(c, how="official upload, different version from Deezer (%s)" % c["match"])
    return rep

async def main(argv):
    from playwright.async_api import async_playwright
    out = argv[argv.index("--out") + 1] if "--out" in argv else "sc_report.json"
    filt = [a for i, a in enumerate(argv) if a != "--out" and (i == 0 or argv[i-1] != "--out")]
    src = SONGS_JS.read_text(encoding="utf-8")
    songs = json.loads(re.search(r"const SONGS = (\[.*\]);", src, re.S).group(1))
    todo = [s for s in songs if not s.get("sc") and (not filt or any(f.lower() in (s["t"] + " " + s["a"]).lower() for f in filt))]
    work = pathlib.Path(tempfile.mkdtemp()); probe = work / "probe.html"; probe.write_text(PROBE, encoding="utf-8")
    report = json.load(open(out)) if os.path.exists(out) else {}
    async with async_playwright() as p:
        kw = {"args": ["--autoplay-policy=no-user-gesture-required"]}
        if os.environ.get("CHROME"): kw["executable_path"] = os.environ["CHROME"]
        b = await p.chromium.launch(**kw)
        page = await (await b.new_context(locale="en-US")).new_page()
        for i, s in enumerate(todo):
            if str(s["id"]) in report: continue
            try: rep = await process(s, b, page, probe.as_uri(), work)
            except Exception as e: rep = {"id": s["id"], "t": s["t"], "a": s["a"], "error": str(e)[:200], "pick": None}
            report[str(s["id"])] = rep
            json.dump(report, open(out, "w"), ensure_ascii=False, indent=1)
            pk = rep.get("pick")
            print("%3d/%d %-28s %s" % (i + 1, len(todo), (s["t"] + " | " + s["a"])[:28], (pk["url"].replace("https://soundcloud.com/", "") + "  [" + pk["how"] + "]") if pk else "NO PICK " + rep.get("error", "")), flush=True)
        await b.close()

def apply(path):
    report = json.load(open(path)); src = SONGS_JS.read_text(encoding="utf-8"); n = 0
    for k, rep in report.items():
        if not rep.get("pick") or rep.get("skip"): continue
        line = re.search(r'\{"id": %s,[^\n]*\}' % k, src)
        if not line or '"sc"' in line.group(0): continue
        src = src.replace(line.group(0), line.group(0)[:-1] + ', "sc": "%s"}' % rep["pick"]["url"]); n += 1
    SONGS_JS.write_text(src, encoding="utf-8"); print("applied", n)

if __name__ == "__main__":
    if "--apply" in sys.argv: apply(sys.argv[sys.argv.index("--apply") + 1])
    else: asyncio.run(main(sys.argv[1:]))
