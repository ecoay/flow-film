import base64, io, json, os, subprocess, sys, tempfile, wave
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp()); os.environ["FLOWFILM_OUT"] = str(TMP / "films")
from flowfilm import budget, presets, ui, media, tts, state


def test_parse_credits():
    assert budget.parse_credits("15 credits") == 15
    assert budget.parse_credits("1,250 AI credits") == 1250
    assert budget.parse_credits("Google Flow credits: 40") == 40
    assert budget.parse_credits("") is None


def test_parse_balance():
    assert budget.parse_balance("50 AI credits") == 50
    assert budget.parse_balance("", "50 AI credits") == 50
    assert budget.parse_balance("Plan 5 of 5\n50 AI credits") == 50
    assert budget.parse_balance("Google Flow credits", None) is None
    assert budget.parse_balance("5") is None


def test_guard():
    assert budget.guard(15, 15, 50) == 15
    for q, lim, bal in ((16, 15, 50), (None, 15, 50), (15, 20, 10)):
        with pytest.raises(budget.OverBudget):
            budget.guard(q, lim, bal)


def test_presets():
    assert len(presets.MOVES) >= 20
    assert "Camera:" in presets.apply("A cat", "orbit")
    with pytest.raises(KeyError):
        presets.apply("x", "nope")


def test_ui_config_valid():
    import re
    for k, v in ui.UI.items():
        if isinstance(v, list):
            for spec in v:
                kind, role, val = ui.parse(ui.expand(spec, aspect="16:9", seconds=10, res="720p", n=1, name="a"))
                assert kind in ("css", "role", "text")


def test_state_approve():
    f = state.Film("Lamp Test")
    f.data["stills"] = [{"id": i, "file": f"s{i}.png"} for i in (1, 2, 3)]
    assert [k["file"] for k in f.approve([3, 1])] == ["s3.png", "s1.png"]
    assert f.keyframe(1) == "s3.png"
    with pytest.raises(KeyError):
        f.approve([9])


def _clip(path, secs, size, audio):
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=24:duration={secs}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={secs}", "-shortest"]
    subprocess.run(cmd + ["-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def test_cut_holds_for_long_narration():
    a = _clip(TMP / "a.mp4", 2, "1280x720", True)
    b = _clip(TMP / "b.mp4", 2, "640x360", False)
    nar = TMP / "n.wav"
    tts.local("This narration is deliberately longer than four seconds of footage so the cut must hold "
              "the final frame until the voice has completely finished speaking.", nar)
    music = _clip(TMP / "m.mp4", 1, "64x64", True)
    res = media.cut([a, b], TMP / "film.mp4", nar, music)
    assert res["size"] == "1280x720"
    assert res["held_last_frame_s"] > 0
    assert res["length_s"] >= res["narration_s"]


def test_cut_without_narration():
    a = _clip(TMP / "c.mp4", 2, "640x360", True)
    res = media.cut([a, a], TMP / "f2.mp4")
    assert abs(res["length_s"] - 4) < 0.3 and res["held_last_frame_s"] == 0


def test_last_frame():
    a = _clip(TMP / "d.mp4", 2, "320x240", False)
    png = media.last_frame(a, TMP / "last.png")
    assert png.exists() and png.stat().st_size > 1000


def test_gemini_tts_mocked():
    pcm = b"\x00\x01" * 24000
    payload = {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/L16;codec=pcm;rate=24000",
                                                                     "data": base64.b64encode(pcm).decode()}}]}}]}
    seen = {}

    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def opener(req, timeout):
        seen["body"] = json.loads(req.data); seen["key"] = req.headers.get("X-goog-api-key")
        return R(json.dumps(payload).encode())
    out = TMP / "g.wav"
    tts.gemini("hello", out, "Charon", "warmly", key="k", opener=opener)
    assert seen["key"] == "k"
    assert seen["body"]["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Charon"
    with wave.open(str(out)) as w:
        assert w.getframerate() == 24000 and w.getnframes() == 24000


def test_narrate_falls_back_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    r = tts.narrate("hi there", TMP / "l.wav", voice="Charon")
    assert r["engine"].startswith("espeak") or r["engine"] == "piper"


def test_cli_end_to_end_offline():
    sh = str(ROOT / "flowfilm.sh")
    run = lambda *a: json.loads(subprocess.run([sh, *a], capture_output=True, text=True).stdout)
    r = run("new", "--film", "CLI Test", "--story", "lamplighter", "--aspect", "9:16", "--budget", "45")
    assert r["budget"] == 45 and r["aspect"] == "9:16"
    run("narrate", "--film", "CLI Test", "--text", "Short line.", "--engine", "local")
    a = _clip(TMP / "e.mp4", 3, "720x1280", True)
    r = run("cut", "--film", "CLI Test", "--clips", str(a))
    assert r["length_s"] >= r["narration_s"]


def test_dom_locators_on_fake_flow_page():
    """Exercise ui.json fallbacks, tile identity and price parsing against a local stand-in page (not real Flow)."""
    from playwright.sync_api import sync_playwright
    from flowfilm.flow import Flow
    html = """<html><body><div class=ProseMirror contenteditable=true></div>
    <button aria-label='Start generation'>go</button><a href='#'>15 credits</a>
    <flow-grid-tile-container><img data-media-id='m1' src='x.png'></flow-grid-tile-container>
    <flow-grid-tile-container><img src='https://flow.google.com/asb/abc'></flow-grid-tile-container></body></html>"""
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome", headless=True)
        pg = b.new_page(); pg.set_content(html)
        assert ui.locate(pg, "generate_button") is not None
        assert budget.parse_credits(ui.locate(pg, "price_quote").inner_text()) == 15
        fake = Flow.__new__(Flow); fake.page = pg
        assert fake.tile_ids() == ["m1", "https://flow.google.com/asb/abc"]
        assert ui.locate(pg, "character_name") is None
        with pytest.raises(RuntimeError, match="ui.json"):
            ui.need(pg, "character_name")
        b.close()
