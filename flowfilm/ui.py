"""Loads ui.json and turns its entries into Playwright locators, trying fallbacks in order."""
import json, os, re
from pathlib import Path

_PATH = Path(os.environ.get("FLOWFILM_UI", Path(__file__).with_name("ui.json")))


def load(path=None):
    return json.loads(Path(path or _PATH).read_text())


UI = load()


def expand(spec, **vars_):
    for k, v in vars_.items():
        spec = spec.replace("{" + k + "}", re.escape(str(v)))
    return spec


def parse(spec):
    """'role:button:Name' -> ('role','button',regex); 'text:x' -> ('text',None,regex); else ('css',None,spec)."""
    if spec.startswith("role:"):
        _, role, name = spec.split(":", 2)
        return "role", role, re.compile(name, re.I)
    if spec.startswith("text:"):
        return "text", None, re.compile(spec[5:], re.I)
    return "css", None, spec


def locate(page, key, **vars_):
    """Return the first fallback for `key` that matches something visible, or None."""
    for spec in UI[key]:
        kind, role, val = parse(expand(spec, **vars_))
        if kind == "role":
            loc = page.get_by_role(role, name=val)
        elif kind == "text":
            loc = page.get_by_text(val)
        else:
            loc = page.locator(val)
        try:
            if loc.count() and loc.first.is_visible():
                return loc.first
        except Exception:
            continue
    return None


def need(page, key, **vars_):
    loc = locate(page, key, **vars_)
    if loc is None:
        raise RuntimeError(f"Flow UI element '{key}' not found. Flow may have changed; update flowfilm/ui.json "
                           f"(tried: {UI[key]}). Run `flowfilm snapshot` to dump the page.")
    return loc
