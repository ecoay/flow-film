# flow-film

Make short narrated films in **Google Flow** from a Linux box, step by step, with a hard credit budget.
Built to be run by a Grok Bot through its shell, but every command works by hand too.

Not affiliated with Google. It operates Flow's web page in your own signed-in Chrome profile, at a human pace.
Flow's interface changes without notice, and automating it may conflict with Google's terms, so use an
account you're comfortable with, at your own risk.

## Install

```bash
git clone https://github.com/ecoay/flow-film /workspace/flow-film && /workspace/flow-film/setup.sh
```

`setup.sh` installs ffmpeg, espeak-ng, Chrome, and Playwright, and links `flowfilm` into `~/.local/bin`.

```bash
flowfilm login        # opens Chrome; sign in to Google yourself (once). The tool never sees your password.
flowfilm status       # signed in? credits left?
```

## Pipeline
| Step | Command | Cost |
|---|---|---|
| Set up a film | `flowfilm new --film lamp --story "..." --aspect 16:9 --budget 45 --voice Charon` | 0 |
| Cast | `flowfilm character --film lamp --name Pip --describe "..."` | 0 |
| Stills | `flowfilm stills --film lamp --prompt "..." --prompt "..."` (or `--file prompts.json`) | 0 |
| Pick key frames | `flowfilm approve --film lamp --ids 2 5 7` | 0 |
| Shot A→B | `flowfilm shot --film lamp --start-kf 1 --end-kf 2 --prompt "..." --move push-in --max-credits 15` | quoted |
| Continue | `flowfilm continue --film lamp --end-kf 3 --prompt "..."` (starts on the previous clip's real last frame) | quoted |
| Library | `flowfilm library --film lamp`, `flowfilm download --film lamp --media-id ID --to file.mp4` | 0 |
| Narration | `flowfilm narrate --film lamp --file story.txt --style "warm, unhurried"` | 0 |
| Final cut | `flowfilm cut --film lamp [--music bed.mp3]` | 0 |
| Camera moves | `flowfilm moves` | |

**Budget guard:** before every paid shot, flow-film reads the price Flow shows and refuses (exit code 2, nothing
generated) if it's missing, above `--max-credits`, above what's left of the film's budget, or above your balance.

**Narration:** uses Gemini TTS when `GEMINI_API_KEY` is set (free key from Google AI Studio; keep it in an env
secret, never in chat). Otherwise it uses piper (`PIPER_MODEL=/path/voice.onnx`) or espeak-ng.

**Final cut:** joins clips in order at the largest clip's size, ducks clip audio under the voice, loops an optional
music bed, and holds the last frame so the film is never shorter than the narration.

Output goes to `~/flow-film-out/<film>/` (film.json, stills/, shots/, frames/, narration.wav, <film>.mp4).

## When Flow changes
Every button and label lives in `flowfilm/ui.json` with fallbacks. If a command says an element wasn't found, run
`flowfilm snapshot --out page.txt`, find the new label in the dump, and edit ui.json.

## Tests
`python3 -m pytest -q tests` (offline: budget, presets, config, state, ffmpeg cut, TTS, CLI, locators on a stand-in page).

## Environment
`FLOWFILM_HOME` (~/.flow-film), `FLOWFILM_OUT` (~/flow-film-out), `FLOWFILM_CDP_PORT` (9444), `FLOWFILM_CHROME`,
`FLOWFILM_PACE` (0.8 s), `FLOWFILM_TTS_MODEL`, `GEMINI_API_KEY`, `PIPER_MODEL`.

MIT © 2026 Bruce Young / Tenacié LLC.

### Better free local voice (piper)
```bash
pip install --break-system-packages piper-tts
mkdir -p ~/.flow-film/piper && cd ~/.flow-film/piper
for f in en_US-ryan-high.onnx en_US-ryan-high.onnx.json; do
  curl -fsSLO "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/$f"; done
export PIPER_MODEL=~/.flow-film/piper/en_US-ryan-high.onnx
```
Note: on Flow's free plan the 1080p download is disabled; flow-film takes the best enabled quality (720p).

## Changes (Oct 2026)
- `--film` must be the short film name; paths are rejected (they used to create a 16:9 duplicate).
- `stills --variants N` images per prompt; output includes `warnings` when an image doesn't match the film aspect.
- `approve --ids` is space-separated.
- `shot`/`continue` require `--prompt`; short plain motion lines work best, and dropping names helps when Flow reports a failed generation.
- `narrate --voice-file vo.mp3 [--voice-delay 0.5]` uses an owner-recorded voiceover (delayed, loudness-normalized) instead of TTS. TTS needs `GEMINI_API_KEY`, or espeak-ng/piper.
- Faster prompt typing.
