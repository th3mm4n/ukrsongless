#!/usr/bin/env python3
"""Check every song with an `sc` field: the SoundCloud widget loads it, it is a full track (not a 30s SNIP),
embeddable, and roughly as long as the Deezer version. Non-DRM tracks are also played for 1 second.

DRM tracks (most official label uploads) cannot be played in headless Chrome for Testing (no Widevine),
so for those only the metadata is checked. Check playback in a real browser with tools/sc_check.html.

Needs: pip install playwright && playwright install chromium   (or set CHROME=/path/to/chrome)
Usage: python3 tools/verify_sc.py [substring-filter]"""
import asyncio, json, os, pathlib, re, sys, tempfile, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).parent.parent
src = (ROOT / "songs.js").read_text(encoding="utf-8")
songs = [s for s in json.loads(re.search(r"const SONGS = (\[.*\]);", src, re.S).group(1)) if s.get("sc")]
if len(sys.argv) > 1:
    songs = [s for s in songs if sys.argv[1].lower() in (s["t"] + s["a"] + s["sc"]).lower()]

PAGE = """<!DOCTYPE html><html><body><iframe id="f" allow="autoplay; encrypted-media" width="400" height="166"></iframe>
<script src="https://w.soundcloud.com/player/api.js"></script><script>
const f = document.getElementById("f"); window.R = {};
f.src = "https://w.soundcloud.com/player/?auto_play=false&url=" + encodeURIComponent(new URLSearchParams(location.search).get("u"));
const w = SC.Widget(f);
w.bind(SC.Widget.Events.ERROR, () => R.error = true);
w.bind(SC.Widget.Events.READY, () => w.getCurrentSound(s => R.sound = s || null));
window.clip = ms => new Promise(res => { const t0 = performance.now(); let first = null;
  const done = r => { w.unbind(SC.Widget.Events.PLAY_PROGRESS); w.pause(); res(r); };
  setTimeout(() => done({ played: false }), 12000);
  w.bind(SC.Widget.Events.PLAY_PROGRESS, e => { if (first === null && e.currentPosition > 0) first = performance.now() - t0;
    if (e.currentPosition >= ms) done({ played: true, latency: Math.round(first), stopAt: Math.round(e.currentPosition) }); });
  w.seekTo(0); w.play(); });
</script></body></html>"""

def deezer_duration(i):
    try: return json.load(urllib.request.urlopen("https://api.deezer.com/track/%d" % i, timeout=20)).get("duration")
    except Exception: return None

async def main():
    from playwright.async_api import async_playwright
    page_file = pathlib.Path(tempfile.mkdtemp()) / "sc_probe.html"
    page_file.write_text(PAGE, encoding="utf-8")
    bad = drm = 0
    async with async_playwright() as p:
        kw = {"args": ["--autoplay-policy=no-user-gesture-required"]}
        if os.environ.get("CHROME"): kw["executable_path"] = os.environ["CHROME"]
        b = await p.chromium.launch(**kw)
        for s in songs:
            label = "%s | %s" % (s["t"], s["a"])
            if "?" in s["sc"] or not re.match(r"^https://(soundcloud\.com|api\.soundcloud\.com/tracks)/", s["sc"]):
                print("BAD ", label, "- sc must be a plain track page URL, no query string:", s["sc"]); bad += 1; continue
            pg = await b.new_page()
            await pg.goto(page_file.as_uri() + "?u=" + urllib.parse.quote(s["sc"], safe=""))
            try:
                await pg.wait_for_function("window.R && (R.sound !== undefined || R.error)", timeout=20000)
            except Exception:
                pass
            r = await pg.evaluate("window.R")
            snd = r.get("sound")
            if not snd:
                print("BAD ", label, "- widget did not load the track:", s["sc"]); bad += 1; await pg.close(); continue
            protos = {t["format"]["protocol"] for t in (snd.get("media") or {}).get("transcodings", [])}
            is_drm = any("encrypted" in x for x in protos)
            dur = round((snd.get("full_duration") or snd.get("duration") or 0) / 1000)
            dz = deezer_duration(s["id"])
            problems = []
            if snd.get("policy") in ("SNIP", "BLOCK") or snd.get("streamable") is False: problems.append("only a %s preview / not streamable" % snd.get("policy"))
            if snd.get("embeddable_by") not in (None, "all"): problems.append("embedding restricted: %s" % snd.get("embeddable_by"))
            notes = []
            if dz and abs(dz - dur) > 8: notes.append("length %ss vs Deezer %ss (different version?)" % (dur, dz))
            if is_drm:
                drm += 1; notes.append("DRM stream, playback not testable here (use tools/sc_check.html)")
            elif not problems:
                c = await pg.evaluate("clip(1000)")
                if not c.get("played"): problems.append("did not play")
                else: notes.append("played 1s, latency %sms, stopped at %sms" % (c["latency"], c["stopAt"]))
            await pg.close()
            if problems: bad += 1
            print("BAD " if problems else "OK  ", label, "=>", snd.get("title"), "|", (snd.get("user") or {}).get("username"),
                  "| %ss %s %s" % (dur, snd.get("policy"), snd.get("monetization_model")), "|", "; ".join(problems + notes))
        await b.close()
    print("%d songs with sc, %d problems, %d DRM (metadata only)" % (len(songs), bad, drm))
    sys.exit(1 if bad else 0)

asyncio.run(main())
