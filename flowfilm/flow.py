"""Playwright driver for flow.google.com, run in a dedicated Chrome profile over CDP.
All UI hooks come from ui.json via flowfilm.ui. Nothing here types Google credentials: the user signs in by hand."""
import os, re, shutil, socket, subprocess, time
from pathlib import Path
from . import ui
from .ui import UI, locate, need
from .budget import parse_credits, parse_balance, guard

HOME = Path(os.environ.get("FLOWFILM_HOME", Path.home() / ".flow-film"))
PROFILE = HOME / "chrome-profile"
PORT = int(os.environ.get("FLOWFILM_CDP_PORT", "9444"))
CHROMES = [os.environ.get("FLOWFILM_CHROME"), "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
           "/usr/bin/chromium", "/usr/bin/chromium-browser"]
PACE = float(os.environ.get("FLOWFILM_PACE", "0.8"))  # seconds between UI actions: human pace, no evasion tricks


def with_lang(url):
    sep = "&" if "?" in url else "?"
    return url if UI["lang_param"] in url else f"{url}{sep}{UI['lang_param']}"


def _port_open():
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def launch_chrome(url=None):
    if _port_open():
        return
    exe = next((c for c in CHROMES if c and Path(c).exists()), None)
    if not exe:
        raise RuntimeError("Chrome not found; set FLOWFILM_CHROME")
    PROFILE.mkdir(parents=True, exist_ok=True)
    for lock in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        (PROFILE / lock).unlink(missing_ok=True)
    subprocess.Popen([exe, f"--user-data-dir={PROFILE}", f"--remote-debugging-port={PORT}", "--no-first-run",
                      "--no-default-browser-check", "--disable-features=Translate", with_lang(url or UI["home_url"])],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(60):
        if _port_open():
            return
        time.sleep(0.5)
    raise RuntimeError(f"Chrome did not open its debug port {PORT}")


class Flow:
    def __init__(self):
        from playwright.sync_api import sync_playwright
        launch_chrome()
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
        self.ctx = self.browser.contexts[0]
        pages = [p for p in self.ctx.pages if "flow.google" in p.url or "labs.google" in p.url]
        self.page = pages[0] if pages else (self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page())

    def close(self):
        self._pw.stop()  # detach only; Chrome keeps running so the sign-in persists

    # ---------- basics ----------
    def goto(self, url):
        self.page.goto(with_lang(url), wait_until="domcontentloaded")
        self.page.wait_for_timeout(2500)

    def signed_in(self):
        if "flow.google" not in self.page.url and "labs.google" not in self.page.url:
            self.goto(UI["home_url"])
        return not re.search(UI["signed_out_url_regex"], self.page.url)

    def wait_for_login(self, minutes=10):
        self.goto(UI["home_url"])
        end = time.time() + minutes * 60
        while time.time() < end:
            if not re.search(UI["signed_out_url_regex"], self.page.url):
                return True
            time.sleep(3)
        return False

    def balance(self):
        """The balance sits inside the account menu (verified live): open it, read 'N AI credits', close it."""
        loc = locate(self.page, "credit_balance")
        opened = False
        if loc is None:
            menu = locate(self.page, "account_menu")
            if menu is None:
                return None
            menu.click(); opened = True
            self.page.wait_for_timeout(1500)
            loc = locate(self.page, "credit_balance")
        val = parse_balance(loc.inner_text(), loc.get_attribute("aria-label")) if loc else None
        if opened:
            self.close_overlays()
        return val

    def tidy(self):
        """Clear what a fresh project shows: the welcome dialog, the agent chat panel, and Agent mode."""
        for key in ("welcome_dismiss",):
            loc = locate(self.page, key)
            if loc: loc.click(); self.page.wait_for_timeout(1500)
        if locate(self.page, "session_panel_marker") is not None:
            loc = locate(self.page, "session_panel_close")
            if loc: loc.click(); self.page.wait_for_timeout(1200)
        agent = locate(self.page, "agent_toggle")
        if agent is not None and agent.get_attribute("aria-pressed") == "true":
            agent.click(); self.page.wait_for_timeout(1200)

    def snapshot(self, out):
        Path(out).write_text(f"URL: {self.page.url}\n\n" + self.page.locator("body").aria_snapshot())
        return out

    def click(self, key, **kw):
        need(self.page, key, **kw).click()
        self.page.wait_for_timeout(int(PACE * 1000))

    # ---------- project ----------
    def open_project(self, film):
        url = film.data.get("flow_project_url")
        if url:
            self.goto(url); self.tidy()
            return url
        self.goto(UI["home_url"])
        self.click("new_project")
        self.page.wait_for_url(re.compile(r"/project/"), timeout=30000)
        film.data["flow_project_url"] = self.page.url.split("?")[0]
        film.save()
        self.page.wait_for_timeout(3000); self.tidy()
        return film.data["flow_project_url"]

    # ---------- grid ----------
    def tile_ids(self):
        """Stable identity per tile: media id, else media src. Titles are NOT unique, so never key on them."""
        js = """(sels) => { const out=[]; for (const sel of sels){ document.querySelectorAll(sel).forEach(t=>{
            const m=t.querySelector('[data-media-id]'); const v=t.querySelector('video,img');
            const id=(m&&m.getAttribute('data-media-id'))||(v&&(v.currentSrc||v.src))||'';
            if(id) out.push(id);}); if(out.length) break;} return out; }"""
        return self.page.evaluate(js, UI["grid_tile"])

    def busy(self):
        return bool(re.search(UI["tile_progress_regex"], self.page.locator("body").inner_text()))

    def wait_new_tiles(self, before, want=1, timeout=600):
        end = time.time() + timeout
        while time.time() < end:
            self.page.wait_for_timeout(4000)
            new = [i for i in self.tile_ids() if i not in before]
            if len(new) >= want and not self.busy():
                return new
            if locate(self.page, "tile_error") is not None and not self.busy():
                fresh = [i for i in self.tile_ids() if i not in before]
                if len(fresh) < want:
                    raise RuntimeError("Flow reported a failed generation (Flow says failed items are not charged). "
                                       "Run the command again.")
        raise TimeoutError("Timed out waiting for Flow. The result may still land: check `flowfilm library` "
                           "and re-download instead of generating again.")

    def tile_by_id(self, media_id):
        for sel in UI["grid_tile"]:
            loc = self.page.locator(sel).filter(has=self.page.locator(
                f"[data-media-id='{media_id}'], img[src='{media_id}'], video[src='{media_id}']"))
            if loc.count():
                return loc.first
        raise RuntimeError(f"tile {media_id[:40]} not visible in the grid")

    def download(self, media_id, dest, video=True):
        if media_id == "latest-video":  # signed-URL ids change on reload; the newest video tile is the safe handle
            tile = self.page.locator(UI["grid_tile"][0]).filter(has=self.page.locator(UI["video_tile_marker"])).first
        else:
            tile = self.tile_by_id(media_id)
        tile.scroll_into_view_if_needed()
        self.close_overlays()
        tile.click(button="right")
        self.page.wait_for_timeout(int(PACE * 1000))
        need(self.page, "download_menu_item").hover(); self.page.wait_for_timeout(1000)
        key = "download_quality_video" if video else "download_quality_image"
        choice = None
        for spec in UI[key]:  # best quality first, skipping ones the plan disables (1080p on free, seen live)
            kind, role, val = ui.parse(spec)
            loc = (self.page.get_by_role(role, name=val) if kind == "role" else
                   self.page.get_by_text(val) if kind == "text" else self.page.locator(val)).first
            try:
                if loc.count() and loc.is_visible() and loc.get_attribute("aria-disabled") != "true" and \
                        not loc.locator("xpath=ancestor-or-self::*[@aria-disabled='true' or @disabled]").count():
                    choice = loc; break
            except Exception:
                continue
        if choice is None:
            raise RuntimeError("no enabled download quality found")
        with self.page.expect_download(timeout=300000) as dl:
            choice.click()
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        tmp = dl.value.path()
        shutil.copy(tmp, dest)
        return str(dest)

    # ---------- composer ----------
    def type_prompt(self, text):
        box = need(self.page, "prompt_box")
        box.click()
        self.page.keyboard.press("Control+A")
        self.page.keyboard.press("Delete")
        box.type(text, delay=2, timeout=120000)

    def close_overlays(self):
        """Escape closes menus and popovers; the account panel needs its own close button (verified live)."""
        acct = locate(self.page, "account_close")
        if acct is not None:
            acct.click(); self.page.wait_for_timeout(600)
        for _ in range(4):
            if not self.page.locator(".cdk-overlay-backdrop-showing").count():
                return
            self.page.keyboard.press("Escape"); self.page.wait_for_timeout(500)

    def configure(self, video, aspect, seconds=None, res=None, variants=1, frames=False):
        if locate(self.page, "mode_image") is None:
            self.close_overlays()
            self.click("settings_toggle")
        self.click("mode_video" if video else "mode_image")
        model = UI["video_model"] if video else UI["image_model"]
        fam = locate(self.page, "model_family")
        if fam is not None and model.lower() not in (fam.inner_text() or "").lower():
            fam.click(); self.page.wait_for_timeout(1000)
            self.click("model_option", model=model)
        if video and frames:
            self.click("video_frames")
        for key, kw in (("aspect_option", {"aspect": aspect}), ("variants_option", {"n": variants})):
            loc = locate(self.page, key, **kw)
            if loc: loc.click(); self.page.wait_for_timeout(300)
        if video:
            for key, kw in (("duration_option", {"seconds": seconds}), ("resolution_option", {"res": res})):
                if kw[list(kw)[0]] is None:
                    continue
                loc = locate(self.page, key, **kw)
                if loc: loc.click(); self.page.wait_for_timeout(300)
        q = locate(self.page, "price_quote")
        quote = parse_credits(q.inner_text()) if q else None
        self.close_overlays()
        return quote

    def attach_frame(self, slot, file):
        """Verified live 2026-10-15: the Start/End slot opens the asset picker; we upload the frame under a unique
        name (so it can't be confused with a look-alike asset) and click it, which attaches it to the slot."""
        src = Path(file)
        tag = f"ff-{int(time.time())}-{slot.split('_')[0]}{src.suffix}"
        tmp = HOME / "uploads" / tag
        tmp.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, tmp)
        self.close_overlays()
        self.click(slot)
        with self.page.expect_file_chooser(timeout=15000) as fc:
            self.click("ingredient_upload")
        fc.value.set_files(str(tmp))
        opt = self.page.get_by_role("option", name=re.compile(re.escape(tag)))
        for _ in range(90):
            agree = locate(self.page, "upload_rights_agree")
            if agree is not None: agree.click()
            if opt.count() and "Uploading" not in opt.first.inner_text():
                break
            self.page.wait_for_timeout(1000)
        else:
            raise TimeoutError(f"frame upload {tag} never finished")
        opt.first.click()
        self.page.wait_for_timeout(1200)
        self.click("ingredient_add")  # picker shows a preview; "Add to prompt" fills the slot
        self.page.wait_for_timeout(1500)
        slot_btn = self.page.get_by_role("button", name=re.compile(r"^(Start|End)$"))
        names = [n.strip() for n in slot_btn.all_inner_texts()]
        want = "Start" if slot.startswith("start") else "End"
        if want in names:  # an empty slot still shows its label
            raise RuntimeError(f"{want} frame did not attach; nothing generated")

    def generate(self):
        before = set(self.tile_ids())
        self.click("generate_button")
        return before

    # ---------- high level ----------
    def still(self, prompt, aspect, variants=1, refs=(), cast=()):
        """Images are free in Flow; the guard still refuses anything that quotes a price above 0."""
        clear = locate(self.page, "clear_prompt")
        if clear: clear.click(); self.page.wait_for_timeout(800)
        if refs or cast:  # ingredients button only exists in Image mode; switch first
            self.configure(False, aspect, variants=variants)
            self.page.keyboard.press("Escape"); self.page.wait_for_timeout(800)
        for r in refs: self.add_ingredient(r)
        for c in cast: self.add_named(c)
        if refs or cast:
            self.page.keyboard.press("Escape"); self.page.wait_for_timeout(800)
        quote = self.configure(False, aspect, variants=variants)
        if quote != 0:
            self.page.keyboard.press("Escape")
            raise RuntimeError(f"Images quoted {quote if quote is not None else 'no readable'} credits; only a "
                               f"confirmed 0-credit quote is allowed. Not generating.")
        self.page.keyboard.press("Escape"); self.page.wait_for_timeout(800)  # close settings overlay
        self.type_prompt(prompt)
        before = self.generate()
        return self.wait_new_tiles(before, want=variants, timeout=300)

    def shot(self, prompt, aspect, seconds, res, limit, balance, start=None, end=None):
        clear = locate(self.page, "clear_prompt")
        if clear: clear.click(); self.page.wait_for_timeout(800)
        quote = self.configure(True, aspect, seconds, res, 1, frames=bool(start or end))
        guard(quote, limit, balance)
        if start: self.attach_frame("start_frame_slot", start)
        if end: self.attach_frame("end_frame_slot", end)
        self.type_prompt(prompt)
        again = self.configure(True, aspect, seconds, res, 1, frames=bool(start or end))
        guard(again, limit, balance)
        quote = again
        before = self.generate()
        return quote, self.wait_new_tiles(before, timeout=900)

    def add_ingredient(self, file):
        """Upload a local image through the ingredients picker and attach it to the prompt (free).
        Flow asks once per session to confirm upload rights ("I agree"); we confirm only for files the user gave us."""
        if locate(self.page, "ingredient_upload") is None:
            self.click("ingredients_button")
        name = Path(file).name
        opt = self.page.get_by_role("option", name=re.compile(re.escape(name)))
        if not opt.count():  # not in the project yet: upload it
            with self.page.expect_file_chooser(timeout=15000) as fc:
                self.click("ingredient_upload")
            fc.value.set_files(str(file))
        for _ in range(60):
            agree = locate(self.page, "upload_rights_agree")
            if agree is not None: agree.click()
            if opt.count() and "Uploading" not in opt.first.inner_text():
                break
            self.page.wait_for_timeout(1000)
        else:
            raise TimeoutError(f"upload of {name} never finished")
        opt.first.click(); self.page.wait_for_timeout(1000)
        add = locate(self.page, "ingredient_add")  # 2026-10-15: picking the option now attaches directly
        if add is not None: add.click()

    def add_named(self, label):
        """Attach an existing project asset or character (by its listed name) to the prompt."""
        if locate(self.page, "ingredient_upload") is None:
            self.click("ingredients_button")
        opt = self.page.get_by_role("option", name=re.compile(re.escape(label), re.I))
        if not opt.count():
            tab = self.page.get_by_role("tab", name="Characters")
            if tab.count(): tab.click(); self.page.wait_for_timeout(1500)
        if not opt.count():
            raise RuntimeError(f"'{label}' is not in this Flow project")
        opt.first.click(); self.page.wait_for_timeout(1000)
        add = locate(self.page, "ingredient_add")  # 2026-10-15: picking the option now attaches directly
        if add is not None: add.click()

    def character(self, name, description, refs=()):
        """Verified live 2026-10-15: Characters nav -> /character page -> refs as ingredients -> describe ->
        Start generation (Nano Banana, free; refuses if any credit price is shown) -> name -> Done."""
        self.click("nav_characters")
        self.page.wait_for_timeout(2000)
        loc = locate(self.page, "character_new")
        if loc: loc.click(); self.page.wait_for_timeout(1500)
        for r in refs:
            self.add_ingredient(r)
        self.page.keyboard.press("Escape"); self.page.wait_for_timeout(800)
        box = need(self.page, "character_prompt")
        box.click(); box.type(description + ". Exactly one figure.", delay=3)
        main = self.page.locator(UI["main_region"]).first
        priced = [x for x in re.findall(r"(\d+)\s+(?:AI\s+)?credits?", main.inner_text()) if x != "0"]
        if priced:
            raise RuntimeError(f"Flow shows a price ({priced[0]} credits) for this character; stopped, nothing generated.")
        self.click("generate_button")
        end = time.time() + 240
        while time.time() < end:
            self.page.wait_for_timeout(4000)
            if locate(self.page, "character_name") is not None and not re.search(
                    UI["tile_progress_regex"], main.inner_text()):
                break
        field = need(self.page, "character_name")
        field.click(); field.fill(name); self.page.keyboard.press("Enter")
        self.page.wait_for_timeout(1200)
        self.click("character_done")
        return name
