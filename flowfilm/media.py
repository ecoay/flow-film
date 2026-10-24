"""Local ffmpeg work: probing, last-frame grabs and the final cut."""
import json, shutil, subprocess, tempfile
from pathlib import Path


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"{cmd[0]} failed: {r.stderr[-800:]}")
    return r.stdout


def duration(path):
    out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)])
    return float(json.loads(out)["format"]["duration"])


def video_size(path):
    out = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                "-of", "json", str(path)])
    s = json.loads(out)["streams"][0]
    return s["width"], s["height"]


def has_audio(path):
    out = _run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0",
                str(path)])
    return bool(out.strip())


def last_frame(video, out_png):
    """Grab the final frame (used as the next shot's start frame for an invisible join)."""
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-y", "-v", "error", "-sseof", "-0.25", "-i", str(video), "-update", "1", "-q:v", "2", str(out_png)])
    if not out_png.exists():  # very short clips: fall back to reverse-select
        _run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vf", "reverse", "-frames:v", "1", str(out_png)])
    return out_png


def cut(clips, out, narration=None, music=None, clip_volume=0.35, music_volume=0.15, tail=0.5):
    """Join clips in order, scaled to the largest clip. If narration is longer than the footage, the last frame is
    held so the film always runs at least as long as the voice (plus `tail` seconds)."""
    clips = [Path(c) for c in clips]
    if not clips:
        raise ValueError("no clips to cut")
    sizes = [video_size(c) for c in clips]
    W, H = max(sizes, key=lambda s: s[0] * s[1])
    W, H = W - W % 2, H - H % 2
    foot = sum(duration(c) for c in clips)
    voice = duration(narration) if narration else 0.0
    target = max(foot, voice + tail if narration else foot)
    hold = max(0.0, target - foot)

    args, parts = ["ffmpeg", "-y", "-v", "error"], []
    for c in clips:
        args += ["-i", str(c)]
    n = len(clips)
    for i, c in enumerate(clips):
        parts.append(f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
                     f"setsar=1,fps=30,format=yuv420p[v{i}]")
        d = duration(c)
        if has_audio(c):
            parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,volume={clip_volume},apad,atrim=0:{d}[a{i}]")
        else:
            parts.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{d}[a{i}]")
    parts.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vc][ac]")
    vlast = "vc"
    if hold > 0:
        parts.append(f"[vc]tpad=stop_mode=clone:stop_duration={hold:.3f}[vh]")
        vlast = "vh"
    mix = []
    idx = n
    if narration:
        args += ["-i", str(narration)]
        parts.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo[nar]")
        mix.append("[nar]")
        idx += 1
    if music:
        args += ["-stream_loop", "-1", "-i", str(music)]
        parts.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,volume={music_volume}[mus]")
        mix.append("[mus]")
    if mix:
        parts.append("[ac]apad[acp]")
        parts.append("[acp]" + "".join(mix) + f"amix=inputs={len(mix) + 1}:duration=longest:normalize=0[am]")
    else:
        parts.append("[ac]apad[am]")
    parts.append(f"[am]atrim=0:{target:.3f}[aout]")
    args += ["-filter_complex", ";".join(parts), "-map", f"[{vlast}]", "-map", "[aout]", "-t", f"{target:.3f}",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(out)]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    _run(args)
    return {"out": str(out), "footage_s": round(foot, 2), "narration_s": round(voice, 2),
            "held_last_frame_s": round(hold, 2), "length_s": round(duration(out), 2), "size": f"{W}x{H}"}


def prepare_voice(src, out, delay=0.5):
    """Turn a user-recorded voiceover into the film's narration track: leading silence, loudness-normalized."""
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True)
    ms = int(delay * 1000)
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-af",
          f"adelay={ms}:all=1,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000", "-ac", "2", str(out)])
    return {"engine": "recorded", "source": str(src), "out": str(out)}
