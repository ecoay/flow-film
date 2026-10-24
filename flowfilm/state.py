"""Per-film working state in <films>/<slug>/film.json: answers, cast, stills, approved key frames and shots."""
import json, os, re, time
from pathlib import Path

FILMS = Path(os.environ.get("FLOWFILM_OUT", Path.home() / "flow-film-out"))


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "film"


class Film:
    def __init__(self, name):
        if "/" in name or name.startswith("~"):
            raise ValueError(f"--film takes the short film name (e.g. 'myfilm'), not a path: {name!r}")
        self.dir = FILMS / slug(name)
        self.file = self.dir / "film.json"
        self.data = json.loads(self.file.read_text()) if self.file.exists() else {
            "name": name, "created": time.strftime("%Y-%m-%d %H:%M"), "aspect": "16:9", "budget": 45,
            "spent": 0, "voice": None, "flow_project_url": None, "cast": [], "stills": [], "keyframes": [],
            "shots": [], "narration": None}

    def save(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps(self.data, indent=2))
        return self

    @property
    def remaining(self):
        return self.data["budget"] - self.data["spent"]

    def approve(self, still_ids):
        known = {s["id"]: s for s in self.data["stills"]}
        missing = [i for i in still_ids if i not in known]
        if missing:
            raise KeyError(f"unknown still id(s): {missing}")
        self.data["keyframes"] = [known[i] for i in still_ids]
        return self.data["keyframes"]

    def keyframe(self, n):
        """1-based key frame path."""
        return self.data["keyframes"][n - 1]["file"]
