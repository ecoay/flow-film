"""flowfilm command line. Every command prints one JSON object so the bot can read the result."""
import argparse, json, sys
from pathlib import Path
from . import presets, media, tts
from .state import Film
from .budget import OverBudget


def out(obj, code=0):
    print(json.dumps(obj, indent=2)); sys.exit(code)


def flow():
    from .flow import Flow
    return Flow()


def cmd_new(a):
    f = Film(a.film)
    f.data.update({k: v for k, v in dict(story=a.story, aspect=a.aspect, budget=a.budget, voice=a.voice).items()
                   if v is not None})
    out({"film": str(f.save().dir), **f.data})


def cmd_login(a):
    fl = flow()
    ok = fl.wait_for_login(a.minutes)
    out({"signed_in": ok, "balance": fl.balance() if ok else None,
         "note": None if ok else "Sign in to Google in the Chrome window on the box desktop, then run again."})


def cmd_status(a):
    fl = flow()
    s = fl.signed_in()
    res = {"signed_in": s, "balance": fl.balance() if s else None}
    if a.film:
        f = Film(a.film); res.update(budget=f.data["budget"], spent=f.data["spent"], remaining=f.remaining)
    out(res)


def cmd_character(a):
    f = Film(a.film); fl = flow(); fl.open_project(f)
    fl.character(a.name, a.describe, a.ref or [])
    f.data["cast"].append({"name": a.name, "describe": a.describe}); f.save()
    out({"character": a.name, "cost": 0})


def cmd_stills(a):
    f = Film(a.film)
    if a.project_url: f.data["flow_project_url"] = a.project_url; f.save()
    fl = flow(); fl.open_project(f)
    items = json.loads(Path(a.file).read_text()) if a.file else a.prompt
    made, warnings = [], []
    for it in items:
        it = it if isinstance(it, dict) else {"prompt": it}
        p = it["prompt"] + (" " + Path(a.style_file).read_text().strip() if a.style_file else "")
        ids = fl.still(p, f.data["aspect"], a.variants, it.get("refs", []) + (a.ref or []),
                       it.get("cast", []) + (a.cast or []))
        for mid in ids:
            n = len(f.data["stills"]) + 1
            dest = f.dir / "stills" / f"still-{n:02d}.png"
            fl.download(mid, dest, video=False)
            try:
                w, h = media.video_size(dest)
                want_tall = f.data["aspect"] == "9:16"
                if (h > w) != want_tall:
                    warnings.append(f"still {n} is {w}x{h}, not {f.data['aspect']}: check Flow's aspect setting")
            except Exception:
                pass
            rec = {"id": n, "beat": it.get("beat"), "prompt": p, "media_id": mid, "file": str(dest)}
            f.data["stills"].append(rec); made.append(rec)
        f.save()
    out({"stills": made, "warnings": warnings, "cost": 0, "next": "Show them to the user, then `flowfilm approve --film F --ids ...`"})


def cmd_approve(a):
    f = Film(a.film); kf = f.approve(a.ids); f.save()
    out({"keyframes": [k["file"] for k in kf]})


def _shot(f, fl, prompt, start, end, a):
    prompt = presets.apply(prompt, a.move)
    limit = min(a.max_credits, f.remaining)
    bal = fl.balance()
    quote, ids = fl.shot(prompt, f.data["aspect"], a.seconds, a.res, limit, bal, start, end)
    n = len(f.data["shots"]) + 1
    dest = f.dir / "shots" / f"shot-{n:02d}.mp4"
    fl.download("latest-video", dest, video=True)
    f.data["spent"] += quote
    f.data["shots"].append({"n": n, "prompt": prompt, "start": start, "end": end, "credits": quote,
                            "media_id": ids[0], "file": str(dest)})
    f.save()
    return {"shot": str(dest), "credits": quote, "spent": f.data["spent"], "remaining": f.remaining}


def cmd_shot(a):
    f = Film(a.film)
    start = f.keyframe(a.start_kf) if a.start_kf else a.start
    end = f.keyframe(a.end_kf) if a.end_kf else a.end
    fl = flow(); fl.open_project(f)
    try:
        out(_shot(f, fl, a.prompt, start, end, a))
    except OverBudget as e:
        out({"refused": str(e)}, 2)


def cmd_continue(a):
    f = Film(a.film)
    if not f.data["shots"]:
        out({"error": "no previous shot to continue from"}, 1)
    prev = f.data["shots"][-1]["file"]
    start = str(media.last_frame(prev, f.dir / "frames" / f"after-shot-{len(f.data['shots']):02d}.png"))
    end = f.keyframe(a.end_kf) if a.end_kf else None
    fl = flow(); fl.open_project(f)
    try:
        res = _shot(f, fl, a.prompt, start, end, a); res["joined_from"] = start; out(res)
    except OverBudget as e:
        out({"refused": str(e)}, 2)


def cmd_library(a):
    f = Film(a.film); fl = flow(); fl.open_project(f)
    known = {s["media_id"] for s in f.data["stills"] + f.data["shots"]}
    ids = fl.tile_ids()
    out({"tiles": [{"media_id": i, "downloaded": i in known} for i in ids]})


def cmd_download(a):
    f = Film(a.film); fl = flow(); fl.open_project(f)
    out({"file": fl.download(a.media_id, a.to, video=not a.image), "cost": 0})


def cmd_narrate(a):
    f = Film(a.film)
    dest = f.dir / "narration.wav"
    if a.voice_file:  # user-recorded voiceover: delay, loudness-normalize, store as the film's narration
        res = media.prepare_voice(a.voice_file, dest, a.voice_delay)
    else:
        text = Path(a.file).read_text() if a.file else a.text
        if not text:
            raise ValueError("give --text/--file for TTS, or --voice-file for a recorded voiceover")
        res = tts.narrate(text, dest, a.voice or f.data.get("voice"), a.style, a.engine)
    res["seconds"] = round(media.duration(dest), 2)
    f.data["narration"] = res; f.save(); out(res)


def cmd_cut(a):
    f = Film(a.film)
    clips = a.clips or [s["file"] for s in f.data["shots"]]
    nar = None if a.no_narration else (a.narration or (f.data["narration"] or {}).get("out"))
    res = media.cut(clips, a.out or f.dir / f"{f.dir.name}.mp4", nar, a.music, a.clip_volume, a.music_volume)
    out(res)


def cmd_moves(a):
    out(presets.MOVES)


def cmd_snapshot(a):
    fl = flow(); out({"file": fl.snapshot(a.out)})


def main(argv=None):
    p = argparse.ArgumentParser(prog="flowfilm")
    sp = p.add_subparsers(dest="cmd", required=True)

    def sub(name, fn, film=True):
        s = sp.add_parser(name); s.set_defaults(fn=fn)
        if film: s.add_argument("--film", required=True)
        return s

    s = sub("new", cmd_new); s.add_argument("--story"); s.add_argument("--aspect", choices=["16:9", "9:16"])
    s.add_argument("--budget", type=int); s.add_argument("--voice")
    s = sub("login", cmd_login, False); s.add_argument("--minutes", type=int, default=10)
    s = sub("status", cmd_status, False); s.add_argument("--film")
    s = sub("character", cmd_character); s.add_argument("--name", required=True); s.add_argument("--describe", required=True)
    s.add_argument("--ref", action="append", help="reference image (repeatable)")
    s = sub("stills", cmd_stills); s.add_argument("--prompt", action="append"); s.add_argument("--file")
    s.add_argument("--variants", type=int, default=1); s.add_argument("--ref", action="append")
    s.add_argument("--cast", action="append", help="Flow character name to attach")
    s.add_argument("--style-file", help="text appended to every prompt (house style)")
    s.add_argument("--project-url", help="reuse an existing Flow project (characters are per project)")
    s = sub("approve", cmd_approve); s.add_argument("--ids", type=int, nargs="+", required=True, help="space-separated, story order: --ids 3 7 12")
    for name, fn in (("shot", cmd_shot), ("continue", cmd_continue)):
        s = sub(name, fn); s.add_argument("--prompt", required=True, help="short plain motion line; avoid character names if Flow fails"); s.add_argument("--move")
        s.add_argument("--seconds", type=int, default=10); s.add_argument("--res", default="720p")
        s.add_argument("--max-credits", type=int, default=15); s.add_argument("--end-kf", type=int)
        if name == "shot":
            s.add_argument("--start-kf", type=int); s.add_argument("--start"); s.add_argument("--end")
    sub("library", cmd_library)
    s = sub("download", cmd_download); s.add_argument("--media-id", required=True); s.add_argument("--to", required=True)
    s.add_argument("--image", action="store_true")
    s = sub("narrate", cmd_narrate); s.add_argument("--text"); s.add_argument("--file"); s.add_argument("--voice")
    s.add_argument("--voice-file", help="user-recorded voiceover (mp3/wav/m4a) instead of TTS")
    s.add_argument("--voice-delay", type=float, default=0.5, help="seconds of silence before the voiceover")
    s.add_argument("--style"); s.add_argument("--engine", choices=["auto", "gemini", "local"], default="auto")
    s = sub("cut", cmd_cut); s.add_argument("--clips", nargs="+"); s.add_argument("--narration"); s.add_argument("--music")
    s.add_argument("--out"); s.add_argument("--no-narration", action="store_true")
    s.add_argument("--clip-volume", type=float, default=0.35); s.add_argument("--music-volume", type=float, default=0.15)
    sub("moves", cmd_moves, False)
    s = sub("snapshot", cmd_snapshot, False); s.add_argument("--out", default="flow-snapshot.txt")
    a = p.parse_args(argv)
    try:
        a.fn(a)
    except SystemExit:
        raise
    except Exception as e:
        out({"error": f"{type(e).__name__}: {e}"}, 1)


if __name__ == "__main__":
    main()
