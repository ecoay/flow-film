"""Narration: Gemini text-to-speech when GEMINI_API_KEY is set, otherwise a local engine (piper or espeak-ng)."""
import base64, json, os, shutil, subprocess, urllib.error, urllib.request, wave
from pathlib import Path

GEMINI_MODEL = os.environ.get("FLOWFILM_TTS_MODEL", "gemini-3.8-flash-tts")
GEMINI_VOICES = ["Charon", "Kore", "Puck", "Fenrir", "Aoede", "Leda", "Orus", "Zephyr", "Enceladus", "Sulafat"]
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _pcm_to_wav(pcm, path, rate=24000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)


def gemini(text, out, voice="Charon", style=None, key=None, opener=urllib.request.urlopen):
    key = key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    spoken = f"{style.strip()}: {text}" if style else text
    body = {"contents": [{"parts": [{"text": spoken}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    req = urllib.request.Request(API.format(model=GEMINI_MODEL), data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        with opener(req, timeout=300) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read())["error"]["message"]
        except Exception:
            msg = e.reason
        raise RuntimeError(f"Gemini TTS {e.code} ({GEMINI_MODEL}): {msg}") from None
    part = data["candidates"][0]["content"]["parts"][0]["inlineData"]
    rate = 24000
    if "rate=" in part.get("mimeType", ""):
        rate = int(part["mimeType"].split("rate=")[1].split(";")[0])
    _pcm_to_wav(base64.b64decode(part["data"]), out, rate)
    return {"engine": "gemini", "voice": voice, "out": str(out)}


def local(text, out, voice=None):
    piper_model = os.environ.get("PIPER_MODEL")
    if shutil.which("piper") and piper_model:
        subprocess.run(["piper", "--model", piper_model, "--output_file", str(out)], input=text, text=True, check=True)
        return {"engine": "piper", "voice": piper_model, "out": str(out)}
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise RuntimeError("No local TTS found. Install espeak-ng (setup.sh does) or piper, or set GEMINI_API_KEY.")
    subprocess.run([exe, "-v", voice or "en-us", "-s", "150", "-w", str(out), text], check=True)
    return {"engine": Path(exe).name, "voice": voice or "en-us", "out": str(out)}


def narrate(text, out, voice=None, style=None, engine="auto"):
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True)
    if engine in ("auto", "gemini") and os.environ.get("GEMINI_API_KEY"):
        try:
            return gemini(text, out, voice or "Charon", style)
        except Exception as e:
            if engine == "gemini":
                raise
            res = local(text, out)
            res["note"] = f"Gemini failed ({e}); used local voice instead"
            return res
    if engine == "gemini":
        raise RuntimeError("engine=gemini but GEMINI_API_KEY is not set")
    return local(text, out, None if (voice or "")[:1].isupper() else voice)
