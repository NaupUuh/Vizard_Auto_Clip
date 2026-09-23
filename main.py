"""
VIZARD AUTO-CLIP TOOL (Anonymous / Local file mode)
====================================================
Quy trinh (khong can dang nhap):
  1. Chon file video le HOAC ca folder (tu quet video).
  2. Voi moi video: mo profile GPM -> vizard.ai/upload -> upload file
     -> bat "Get AI clips" -> chon Ratio / Clip length / Model / Template
     / cac tuy chon -> "Get AI clips" -> cho gen xong.
  3. Tai TAT CA clip ve, tao thu muc con "AI Vizard" trong thu muc goc.
  4. Chay nhieu luong song song (moi luong = 1 profile GPM).

Chay anonymous => clip co watermark, project tu xoa sau 24h (khong sao,
tai xong la co file).
"""
import os, sys, json, time, re, asyncio, threading, queue, subprocess, importlib.util
import urllib.request, urllib.parse, ssl
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_DIR = Path(__file__).resolve().parent
STATE_FILE = APP_DIR / "state.json"
APP_VERSION = "1.1.0"

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".3gp", ".webm", ".m4v", ".flv", ".wmv"}
TOOL_NOTE = "vizard-tool"
MAX_ATTEMPTS = 3  # so lan thu lai 1 video truoc khi tinh la loi that


class CreditExhausted(Exception):
    """Profile het credit (modal Upgrade) -> video chua xu ly, can profile khac."""
    pass

# ------------------------- bootstrap deps -------------------------
def ensure(pkg, import_name=None):
    name = import_name or pkg
    if importlib.util.find_spec(name) is not None:
        return
    print(f"[setup] Dang cai {pkg} ...", flush=True)
    last = None
    for attempt in range(3):
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", pkg])
            return
        except Exception as e:
            last = e
            print(f"[setup] {pkg} loi (thu {attempt+1}/3), thu lai...", flush=True)
            time.sleep(3)
    raise RuntimeError(f"Khong cai duoc {pkg}: {last}")

def bootstrap():
    # dam bao pip san sang (may moi co the thieu)
    try:
        import pip  # noqa
    except Exception:
        try:
            subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"],
                           capture_output=True, timeout=180)
        except Exception:
            pass
    ensure("certifi")
    ensure("playwright")
    ensure("yt-dlp", "yt_dlp")
    ensure("Pillow", "PIL")
    # ensure chromium protocol client exists (harmless if already there)
    try:
        import playwright  # noqa
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                       capture_output=True, timeout=600)
    except Exception:
        pass
    # fix stale CA store on fresh Windows machines
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
        urllib.request.install_opener(opener)
    except Exception:
        pass

bootstrap()
from playwright.async_api import async_playwright, TimeoutError as PWTimeout  # noqa

import shutil, zipfile

# ------------------------- ffmpeg locator (self-bootstrap) -------------------------
FFMPEG_CACHE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "vizard_auto_clip" / "ffmpeg"
_FFMPEG_PATH = None

def find_ffmpeg():
    """Tim ffmpeg.exe: PATH -> cac vi tri quen thuoc -> cache -> tai ve."""
    global _FFMPEG_PATH
    if _FFMPEG_PATH and Path(_FFMPEG_PATH).exists():
        return _FFMPEG_PATH
    # 1) PATH
    p = shutil.which("ffmpeg")
    if p:
        _FFMPEG_PATH = p; return p
    # 2) cac vi tri thuong co san tren may user
    for cand in [
        Path(os.environ.get("LOCALAPPDATA","")) / "ffmpeg" / "bin" / "ffmpeg.exe",
        FFMPEG_CACHE / "ffmpeg.exe",
    ]:
        if cand.exists():
            _FFMPEG_PATH = str(cand); return _FFMPEG_PATH
    # 3) tai portable build
    try:
        FFMPEG_CACHE.mkdir(parents=True, exist_ok=True)
        url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        zp = FFMPEG_CACHE / "ffmpeg.zip"
        urllib.request.urlretrieve(url, str(zp))
        with zipfile.ZipFile(zp) as z:
            for n in z.namelist():
                if n.endswith("/bin/ffmpeg.exe"):
                    with z.open(n) as src, open(FFMPEG_CACHE / "ffmpeg.exe", "wb") as dst:
                        shutil.copyfileobj(src, dst)
                elif n.endswith("/bin/ffprobe.exe"):
                    with z.open(n) as src, open(FFMPEG_CACHE / "ffprobe.exe", "wb") as dst:
                        shutil.copyfileobj(src, dst)
        zp.unlink(missing_ok=True)
        exe = FFMPEG_CACHE / "ffmpeg.exe"
        if exe.exists():
            _FFMPEG_PATH = str(exe); return _FFMPEG_PATH
    except Exception:
        pass
    return None


# ------------------------- YouTube search (yt-dlp) -------------------------
def _fmt_dur(sec):
    try:
        sec = int(sec or 0)
    except Exception:
        return "?"
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def _fmt_views(v):
    try:
        v = int(v or 0)
    except Exception:
        return "?"
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v/1_000:.1f}K"
    return str(v)

def youtube_search(keyword, limit=15, min_sec=0, max_sec=0):
    """Tim YouTube theo keyword, sap xep theo view giam dan.
    Tra list dict: title, url, duration_sec, duration, views, view_count.
    Loc theo do dai neu min_sec/max_sec > 0."""
    import yt_dlp
    # lay nhieu hon de con loc
    n = max(limit * 3, 30)
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True,
            "skip_download": True, "default_search": "ytsearch"}
    results = []
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{n}:{keyword}", download=False)
        for e in (info.get("entries") or []):
            if not e:
                continue
            dur = e.get("duration") or 0
            if min_sec and dur and dur < min_sec:
                continue
            if max_sec and dur and dur > max_sec:
                continue
            vid = e.get("id", "")
            results.append({
                "title": e.get("title", "")[:70],
                "url": f"https://www.youtube.com/watch?v={vid}",
                "duration_sec": dur,
                "duration": _fmt_dur(dur),
                "view_count": e.get("view_count") or 0,
                "views": _fmt_views(e.get("view_count")),
            })
    results.sort(key=lambda r: r["view_count"], reverse=True)
    return results[:limit]


# ============================= GPM CLIENT (v3) =============================
class GPMClient:
    def __init__(self, base_url):
        u = (base_url or "").strip().rstrip("/")
        # tu chuan hoa: neu chi nhap host:port (khong co /api/vN) -> them /api/v1 (GPM Global)
        if u and "/api/v" not in u:
            u = u + "/api/v1"
        self.base_url = u

    def _get(self, path, params=None, timeout=30):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
        if not data.get("success", False):
            raise RuntimeError(data.get("message") or "GPM API failed")
        return data.get("data")

    def _post(self, path, body, timeout=60):
        url = self.base_url + path
        req = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
        if not data.get("success", False):
            raise RuntimeError(data.get("message") or "GPM API failed")
        return data.get("data")

    def list_profiles(self, per_page=100):
        out, page = [], 1
        while True:
            d = self._get("/profiles", {"per_page": per_page, "page": page}, timeout=30)
            last_page = None
            if isinstance(d, dict):
                last_page = d.get("last_page")
                d = d.get("data", [])
            if not d:
                break
            out.extend(d)
            if last_page is not None:
                if page >= last_page:
                    break
            elif len(d) < per_page:
                break
            page += 1
            if page > 200:
                break
        return out

    def list_tool_profiles(self):
        return [p for p in self.list_profiles()
                if str(p.get("note") or "").strip() == TOOL_NOTE]

    def create_profile(self, name):
        data = self._post("/profiles/create",
                          {"profile_name": name, "group_name": "All"})
        pid = (data or {}).get("id")
        if pid:
            try:
                self._post(f"/profiles/update/{pid}", {"note": TOOL_NOTE})
            except Exception:
                pass
        return pid

    def start_profile(self, pid, hidden=False):
        params = {"skip_proxy_check": "true"}
        return self._get(f"/profiles/start/{pid}", params, timeout=120)

    def stop_profile(self, pid):
        try:
            return self._get(f"/profiles/stop/{pid}", timeout=60)
        except Exception:
            return None

    @staticmethod
    def ws_from_start(data, tries=15):
        """Lay CDP websocket tu ket qua start.
        GPM Global tra 'websocket_debugging_url' truc tiep.
        Ban thuong tra 'remote_debugging_address' (host:port) -> resolve /json/version."""
        data = data or {}
        ws = data.get("websocket_debugging_url")
        if ws:
            return ws
        addr = data.get("remote_debugging_address", "")
        port = data.get("remote_debugging_port")
        if not addr and port:
            addr = f"127.0.0.1:{port}"
        if not addr:
            raise RuntimeError("GPM khong tra ws/addr khi start")
        last = ""
        for _ in range(tries):
            try:
                with urllib.request.urlopen(f"http://{addr}/json/version", timeout=8) as r:
                    return json.loads(r.read().decode("utf-8"))["webSocketDebuggerUrl"]
            except Exception as e:
                last = str(e); time.sleep(1)
        raise RuntimeError(f"Cannot resolve CDP ws from {addr}: {last}")


# ============================= VIZARD WORKFLOW =============================
class VizardWorker:
    def __init__(self, log_fn, blur_wm=False):
        self.log = log_fn
        self.blur_wm = blur_wm

    async def attach(self, ws_url):
        pw = await async_playwright().start()
        browser, last = None, ""
        for _ in range(20):
            try:
                browser = await pw.chromium.connect_over_cdp(ws_url, timeout=10000)
                break
            except Exception as e:
                last = str(e); await asyncio.sleep(1)
        if not browser:
            try: await pw.stop()
            except Exception: pass
            raise RuntimeError(f"Cannot attach GPM browser: {last}")
        return pw, browser

    async def _dismiss_popups(self, page):
        for txt in ["Accept all", "Accept All", "Chấp nhận", "Got it", "Skip", "Close", "×"]:
            try:
                b = page.get_by_text(txt, exact=False)
                if await b.count():
                    await b.first.click(timeout=1500)
                    await page.wait_for_timeout(400)
            except Exception:
                pass

    async def _dismiss_tour(self, page):
        """Close the '/project/' onboarding tour bubbles (they cover Download)."""
        try:
            for _ in range(5):
                if not await page.locator(".project-guide-bubble").count():
                    break
                await page.evaluate("""() => {
                    document.querySelectorAll('.project-guide-bubble iconpark-icon[name="closesmall"]')
                        .forEach(x => { try { x.click(); } catch(e){} });
                    document.querySelectorAll('.project-guide-bubble, [class*="guide-bubble"], [class*="guide-mask"], [class*="guide-overlay"]')
                        .forEach(el => el.remove());
                }""")
                await page.wait_for_timeout(400)
        except Exception:
            pass

    async def _close_signup_modal(self, page):
        """Vizard bung modal Sign up khi doi config luc chua login. X di, chay tiep."""
        try:
            closed = await page.evaluate("""() => {
                let did = false;
                document.querySelectorAll('iconpark-icon[name="close"].close-button')
                    .forEach(x => { try { x.click(); did = true; } catch(e){} });
                return did;
            }""")
            if closed:
                await page.wait_for_timeout(500)
            return closed
        except Exception:
            return False

    async def _check_credit_exhausted(self, page):
        """True neu hien modal Upgrade/het credit."""
        try:
            body = (await page.inner_text("body")).lower()
            return any(k in body for k in [
                "upgrade your plan", "more credits", "credits you need",
                "credits per month", "out of credits", "run out of credits"])
        except Exception:
            return False

    async def process_video(self, page, video_path, cfg, dest_dir, stop_fn, _retry=0):
        """Run one full video through Vizard, return list of downloaded files."""
        vname = Path(video_path).name
        self.log(f"[{vname}] mo trang upload...")
        await page.goto("https://vizard.ai/upload", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        await self._dismiss_popups(page)

        # 1) upload file
        fi = page.locator("#file-input")
        await fi.wait_for(state="attached", timeout=30000)
        await fi.set_input_files(str(video_path))
        self.log(f"[{vname}] da chon file, cho web nhan dien...")
        # wait until file card shows (filename + resolution/duration)
        ok = False
        for _ in range(30):
            await page.wait_for_timeout(2000)
            body = await page.inner_text("body")
            if Path(video_path).stem[:12] in body or re.search(r"\d+p", body):
                ok = True; break
            if stop_fn(): raise RuntimeError("Stopped")
        if not ok:
            raise RuntimeError("Web khong nhan file (upload fail)")

        # 2-7) cau hinh + tao clip + tai (dung chung voi link mode)
        return await self._config_gen_download(page, vname, cfg, dest_dir, stop_fn,
                                               retry_fn=lambda r: self._process_retry(page, video_path, cfg, dest_dir, stop_fn, r),
                                               _retry=_retry)

    async def process_link(self, page, link, cfg, dest_dir, stop_fn, _retry=0):
        """Chay 1 link video (YouTube...) qua Vizard link mode."""
        vname = link[-40:]
        self.log(f"[link] mo trang & nhap link: {link[:60]}")
        await page.goto("https://vizard.ai/upload", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        await self._dismiss_popups(page)
        # 1) nhap link + Continue
        inp = page.locator('input[placeholder="Drop a video link"]')
        await inp.wait_for(state="visible", timeout=30000)
        await inp.click(); await inp.fill(link); await page.wait_for_timeout(500)
        await page.locator("button.win-confirm-button").filter(has_text="Continue").first.click()
        self.log(f"[link] cho Vizard tai video ve...")
        # cho Vizard fetch xong -> hien card + resolution
        ok = False
        for _ in range(40):   # fetch link co the lau
            await page.wait_for_timeout(3000)
            if stop_fn(): raise RuntimeError("Stopped")
            body = await page.inner_text("body")
            low = body.lower()
            if await self._check_credit_exhausted(page):
                raise CreditExhausted("Profile het credit")
            if re.search(r"\d+p", body) and ("get ai clips" in low or "model v" in low):
                ok = True; break
            if any(k in low for k in ["invalid", "not support", "unable to", "failed to fetch"]):
                raise RuntimeError(f"Link loi: {body[:120]}")
        if not ok:
            raise RuntimeError("Vizard khong tai duoc link (timeout fetch)")
        return await self._config_gen_download(page, vname, cfg, dest_dir, stop_fn,
                                               retry_fn=lambda r: self._link_retry(page, link, cfg, dest_dir, stop_fn, r),
                                               _retry=_retry)

    async def _config_gen_download(self, page, vname, cfg, dest_dir, stop_fn, retry_fn, _retry=0):
        """Phan dung chung: bat toggle -> Upload -> config -> Get AI clips -> cho -> tai."""
        # 2) enable "Get AI clips" toggle if off
        try:
            sw = page.locator("div.el-switch").last
            cls = await sw.get_attribute("class") or ""
            if "is-checked" not in cls:
                await sw.click(); await page.wait_for_timeout(1500)
        except Exception as e:
            self.log(f"[{vname}] toggle warn: {str(e)[:60]}")

        # 3) choose Model if v2 requested
        if cfg.get("model", "v1").lower() == "v2":
            await self._select_model(page, "v2")

        # 4) click Upload/Continue confirm -> opens config panel
        await page.locator("div.win-confirm-button, button.win-confirm-button").first.click()
        self.log(f"[{vname}] cau hinh clip...")
        for _ in range(15):
            await page.wait_for_timeout(1500)
            if "Ratio" in await page.inner_text("body"):
                break

        # 5) apply config (best-effort; modal Sign up -> X di)
        await self._set_ratio(page, cfg.get("ratio", "9:16"))
        await self._set_clip_length(page, cfg.get("clip_length", "Any length"))
        await self._set_template(page, cfg.get("template", "Default"))
        await self._set_checkboxes(page, cfg)
        if await self._close_signup_modal(page):
            self.log(f"[{vname}] gap modal Sign up -> X di, tiep tuc")

        # 6) start generation
        await page.wait_for_timeout(800)
        await self._close_signup_modal(page)
        await page.locator("div.submit-clip-button").first.click()
        self.log(f"[{vname}] dang tao clip (cho 2-8 phut)...")

        # 7) wait for results /project/ (theo BUOC, chong treo)
        deadline = time.time() + cfg.get("timeout", 1800)
        # cac buoc Vizard hien theo thu tu; map sang ten tieng Viet de log
        STEPS = [
            ("upload", "Upload"),
            ("create project", "Tao project"),
            ("process video", "Xu ly video"),
            ("find best parts", "Tim doan hay nhat"),
            ("edit clips", "Chinh sua clip"),
            ("finalizing", "Hoan thien"),
        ]
        last_step = None
        last_pct = None
        # moc thoi gian de phat hien treo: reset moi khi BUOC doi (khong theo %)
        step_since = time.time()
        NO_PROGRESS_LIMIT = 180  # qua 180s ma khong sang buoc moi -> reload 1 lan
        reloaded_once = False
        while time.time() < deadline:
            if stop_fn(): raise RuntimeError("Stopped")
            await asyncio.sleep(8)
            u = page.url
            if await self._check_credit_exhausted(page):
                raise CreditExhausted("Profile het credit")
            body_raw = await page.inner_text("body")
            body = body_raw.lower()
            if "/project/" in u and any(k in body for k in
                    ["virality", "remove watermark", "publish", "highest"]):
                self.log(f"[{vname}] clip da san sang!")
                break
            # xac dinh buoc hien tai = buoc cuoi cung xuat hien trong noi dung
            cur_idx = -1
            for idx, (key, _) in enumerate(STEPS):
                if key in body:
                    cur_idx = idx
            m = re.search(r"(\d+)%", body)
            pct = m.group(1) if m else None
            if cur_idx >= 0:
                label = STEPS[cur_idx][1]
                extra = f" {pct}%" if (pct and cur_idx == len(STEPS)-1) else ""
                msg = f"buoc {cur_idx+1}/{len(STEPS)}: {label}{extra}"
                if cur_idx != last_step or pct != last_pct:
                    self.log(f"[{vname}] {msg}")
                    last_pct = pct
                if cur_idx != last_step:
                    last_step = cur_idx
                    step_since = time.time()   # sang buoc moi -> reset dong ho treo
            # treo: qua lau khong sang buoc moi (du % co nhay)
            if time.time() - step_since > NO_PROGRESS_LIMIT:
                if not reloaded_once:
                    reloaded_once = True
                    step_since = time.time()
                    self.log(f"[{vname}] treo qua {NO_PROGRESS_LIMIT}s -> tai lai trang de tiep tuc...")
                    try:
                        await page.reload(wait_until="domcontentloaded", timeout=30000)
                    except Exception:
                        pass
                    await page.wait_for_timeout(4000)
                elif _retry < 2:
                    self.log(f"[{vname}] van treo -> lam lai tu dau (lan {_retry+1})")
                    return await retry_fn(_retry + 1)
                else:
                    raise RuntimeError(f"treo qua lau sau {_retry+1} lan thu")
        else:
            raise RuntimeError("Timeout cho Vizard gen clip")

        await page.wait_for_timeout(3000)
        await self._dismiss_tour(page)
        return await self._download_all(page, dest_dir, vname)

    async def _process_retry(self, page, video_path, cfg, dest_dir, stop_fn, _retry):
        try:
            await page.goto("about:blank", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(1500)
        except Exception:
            pass
        return await self.process_video(page, video_path, cfg, dest_dir, stop_fn, _retry)

    async def _link_retry(self, page, link, cfg, dest_dir, stop_fn, _retry):
        try:
            await page.goto("about:blank", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(1500)
        except Exception:
            pass
        return await self.process_link(page, link, cfg, dest_dir, stop_fn, _retry)

    # ---- config helpers ----
    async def _select_model(self, page, model):
        try:
            await page.locator("div.select-model").first.click(timeout=4000)
            await page.wait_for_timeout(800)
            target = "Model v2" if model == "v2" else "Model v1"
            opt = page.get_by_text(target, exact=False)
            if await opt.count():
                await opt.last.click(timeout=3000)
                await page.wait_for_timeout(600)
        except Exception as e:
            self.log(f"model select warn: {str(e)[:60]}")

    async def _open_and_pick(self, page, label, target):
        """Open the dropdown row whose .pre label == label, then pick target.
        Best-effort + nhanh: neu bung modal Sign up thi X di va bo qua (khong ep)."""
        # neu da co modal thi dong truoc
        await self._close_signup_modal(page)
        # 1) open the row by its label (click the row container)
        try:
            row = page.locator(f"div.multiple-select-input:has(div.pre:text-is('{label}'))")
            if not await row.count():
                row = page.locator("div.multiple-select-input").filter(has_text=label)
            if not await row.count():
                return False
            await row.first.click(timeout=2500)
        except Exception:
            return False
        await page.wait_for_timeout(600)
        # neu click lam bung modal Sign up -> X di, bo qua dropdown nay
        if await self._close_signup_modal(page):
            self.log(f"[cfg] doi {label} bung Sign up -> giu mac dinh, tiep tuc")
            return False
        # 2) if already on target, done
        try:
            cur = (await row.first.locator("div.value").inner_text()).strip()
            if cur == target:
                # close dropdown by clicking row again
                await row.first.click(timeout=2000)
                return True
        except Exception:
            pass
        # 3) pick the option
        try:
            opt = page.locator(f"div.single-select-item:text-is('{target}')")
            if not await opt.count():
                opt = page.get_by_text(target, exact=True)
            if await opt.count():
                await opt.last.click(timeout=3000)
                await page.wait_for_timeout(600)
                return True
            self.log(f"dropdown warn ({label}->{target}): khong thay option")
        except Exception as e:
            self.log(f"dropdown warn ({label}->{target}): {str(e)[:50]}")
        return False

    async def _set_ratio(self, page, ratio):
        if ratio:
            await self._open_and_pick(page, "Ratio", ratio)

    async def _set_clip_length(self, page, length):
        if length:
            await self._open_and_pick(page, "Clip length", length)

    async def _set_template(self, page, template):
        if template and template != "Default":
            try:
                t = page.get_by_text(template, exact=True)
                if await t.count():
                    await t.first.click(timeout=3000)
                    await page.wait_for_timeout(500)
            except Exception:
                pass

    async def _set_checkboxes(self, page, cfg):
        """Set each feature checkbox to desired state by its label text."""
        wanted = {
            "Add emojis": cfg.get("add_emojis", True),
            "Highlight keywords": cfg.get("highlight_keywords", True),
            "Add B-rolls": cfg.get("add_brolls", False),
            "Remove silences": cfg.get("remove_silences", False),
            "Auto-censor": cfg.get("auto_censor", False),
        }
        for label, want in wanted.items():
            try:
                await page.evaluate("""([label, want]) => {
                    const vis = e => e.offsetParent !== null;
                    // find the text node element
                    const nodes = Array.from(document.querySelectorAll('*')).filter(e =>
                        vis(e) && (e.innerText||'').trim() === label && e.children.length < 3);
                    if (!nodes.length) return;
                    let node = nodes[0];
                    // walk up to a container holding an .el-checkbox
                    let box = null, cur = node;
                    for (let i=0; i<5 && cur; i++) {
                        box = cur.querySelector('.el-checkbox');
                        if (box) break;
                        // also check previous siblings
                        let sib = cur.previousElementSibling;
                        while (sib) { if (sib.classList && sib.classList.contains('el-checkbox')) { box = sib; break; } sib = sib.previousElementSibling; }
                        if (box) break;
                        cur = cur.parentElement;
                    }
                    if (!box) return;
                    const checked = box.classList.contains('is-checked');
                    if (checked !== want) box.click();
                }""", [label, want])
                await page.wait_for_timeout(200)
            except Exception:
                pass

    # ---- download ----
    async def _download_all(self, page, dest_dir, vname):
        dest_dir = Path(dest_dir); dest_dir.mkdir(parents=True, exist_ok=True)
        downloaded = []
        # nut Download rieng tung clip (bo qua nut "batch download" o tren cung -
        # no bi disabled khi chua Select all). Chi nut nay moi tai truc tiep.
        sel = "div.border-button.narrow-video-button:has-text('Download')"
        btns = page.locator(sel)
        n = await btns.count()
        self.log(f"[{vname}] tim thay {n} nut Download")
        # tu dong chap nhan dialog (beforeunload) khong lam treo
        page.on("dialog", lambda d: asyncio.create_task(d.accept()))
        downloads_folder = Path.home() / "Downloads"
        for i in range(n):
            try:
                btn = page.locator(sel).nth(i)
                try:
                    await btn.scroll_into_view_if_needed(timeout=8000)
                    await btn.evaluate("el => el.scrollIntoView({block:'center'})")
                except Exception:
                    pass
                await page.wait_for_timeout(600)
                # ghi nhan file Downloads truoc khi bam
                before = set(f.name for f in downloads_folder.glob("*.mp4") if f.is_file())
                # bam Download (Chrome tu tai, khong dung expect_download vi no khong bat duoc event)
                try:
                    await btn.click(timeout=10000, force=True)
                except Exception:
                    await btn.evaluate("el => el.click()")
                self.log(f"[{vname}] dang cho file tai xuong (clip {i+1})...")
                # cho file moi xuat hien trong Downloads (timeout 90s)
                new_file = None
                for _ in range(90):
                    await asyncio.sleep(1)
                    after = set(f.name for f in downloads_folder.glob("*.mp4") if f.is_file())
                    diff = after - before
                    if diff:
                        # lay file lon nhat (truong hop nhieu file cung luc)
                        candidates = [downloads_folder / fn for fn in diff]
                        new_file = max(candidates, key=lambda f: f.stat().st_size if f.exists() else 0)
                        # doi cho file khong con tang kich thuoc (tai xong)
                        stable = 0
                        last_sz = 0
                        while stable < 3:
                            await asyncio.sleep(1)
                            sz = new_file.stat().st_size if new_file.exists() else 0
                            if sz == last_sz:
                                stable += 1
                            else:
                                stable = 0
                                last_sz = sz
                        break
                if not new_file or not new_file.exists():
                    raise RuntimeError(f"Khong tim thay file tai xuong clip {i+1}")
                # copy sang dest_dir + doi ten
                fn = re.sub(r'[\\/:*?"<>|]', "_", new_file.name)
                out = dest_dir / fn
                k = 1
                while out.exists():
                    out = dest_dir / f"{Path(fn).stem}_{k}{Path(fn).suffix}"; k += 1
                import shutil
                shutil.move(str(new_file), str(out))
                self.log(f"[{vname}] tai: {out.name} ({out.stat().st_size/1024:.0f}KB)")
                # hau xu ly: che mo logo + cat 2.5s cuoi
                final = await asyncio.to_thread(self._blur_watermark, str(out))
                downloaded.append(final)
            except Exception as e:
                self.log(f"[{vname}] dl {i} loi: {str(e)[:80]}")
        return downloaded

    # cac vung logo Vizard co the xuat hien (ti le theo khung hinh)
    WM_REGIONS = {
        "TR": (0.50, 0.005, 0.99, 0.13),    # goc tren-phai "Vizard.ai"
        "RM": (0.63, 0.205, 0.97, 0.30),    # phai-giua "made with Vizard.ai"
        "LM": (0.03, 0.195, 0.35, 0.32),    # trai-giua "made with Vizard.ai"
    }

    @staticmethod
    def _ffprobe_path(ff):
        d = os.path.dirname(ff)
        base = os.path.basename(ff).replace("ffmpeg", "ffprobe")
        cand = os.path.join(d, base)
        return cand if os.path.exists(cand) else (shutil.which("ffprobe") or cand)

    def _probe_dims(self, ff, path):
        probe = self._ffprobe_path(ff)
        try:
            r = subprocess.run([probe, "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
                capture_output=True, text=True, timeout=30)
            if "," in r.stdout:
                w, h = [int(x) for x in r.stdout.strip().split(",")[:2]]
                return w, h
        except Exception:
            pass
        return 720, 1280

    def _probe_duration(self, ff, path):
        probe = self._ffprobe_path(ff)
        try:
            r = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration",
                "-of", "csv=p=0", path], capture_output=True, text=True, timeout=30)
            return float(r.stdout.strip())
        except Exception:
            return 0.0

    def _detect_wm_regions(self, ff, path):
        """Tra ve list cac vung ('TR'/'LM') THUC SU co logo tinh (chu trang dung yen).
        Dung per-pixel MIN over frames: chu logo luon sang -> min cao; mat/canh dong -> min thap.
        Nho vay khong bao gio che nham mat nguoi."""
        try:
            from PIL import Image
        except Exception:
            # khong co PIL -> che ca 2 vung cho an toan (van blur nhe)
            return list(self.WM_REGIONS.keys())
        import tempfile, glob, shutil as _sh
        tmpd = tempfile.mkdtemp(prefix="vzwm_")
        found = []
        try:
            # trich 6 frame, scale 360 rong cho nhanh
            r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y",
                "-i", path, "-vf", "fps=1,scale=360:-1", "-frames:v", "6",
                os.path.join(tmpd, "f_%02d.png")], capture_output=True, timeout=120)
            files = sorted(glob.glob(os.path.join(tmpd, "*.png")))
            if len(files) < 2:
                return list(self.WM_REGIONS.keys())
            imgs = [Image.open(f).convert("L") for f in files]
            W, H = imgs[0].size
            pix = [im.load() for im in imgs]
            for name, (fx0, fy0, fx1, fy1) in self.WM_REGIONS.items():
                x0, y0 = int(fx0*W), int(fy0*H); x1, y1 = int(fx1*W), int(fy1*H)
                cnt = tot = 0
                for yy in range(y0, y1, 2):
                    for xx in range(x0, x1, 2):
                        mn = min(p[xx, yy] for p in pix)
                        if mn > 185:
                            cnt += 1
                        tot += 1
                ratio = cnt / max(tot, 1)
                if ratio > 0.035:   # co du pixel sang-tinh -> co logo
                    found.append(name)
            return found
        except Exception:
            return list(self.WM_REGIONS.keys())
        finally:
            try: _sh.rmtree(tmpd, ignore_errors=True)
            except Exception: pass

    def _blur_watermark(self, path):
        """Che MO NHE dung vung co logo (tu dong dò), roi cat 2.5s cuoi.
        Ghi de file goc. Khong co ffmpeg -> bo qua."""
        ff = find_ffmpeg()
        if not ff:
            self.log("khong tim thay ffmpeg -> bo qua che watermark")
            return path
        try:
            W, H = self._probe_dims(ff, path)
            regions = self._detect_wm_regions(ff, path) if self.blur_wm else []
            # xay filter blur cho tung vung phat hien
            vf_chain = ""
            if regions:
                n = len(regions)
                parts = [f"[0:v]split={n+1}[base]" + "".join(f"[t{i}]" for i in range(n)) + ";"]
                cur = "base"
                for i, name in enumerate(regions):
                    fx0, fy0, fx1, fy1 = self.WM_REGIONS[name]
                    rx, ry = int(fx0*W), int(fy0*H)
                    rw, rh = int((fx1-fx0)*W), int((fy1-fy0)*H)
                    # blur MANH hon (2 pass) de an han logo ma van khong qua xau
                    parts.append(f"[t{i}]crop={rw}:{rh}:{rx}:{ry},boxblur=14:2[b{i}];")
                    outlbl = f"v{i}" if i < n-1 else "vout"
                    parts.append(f"[{cur}][b{i}]overlay={rx}:{ry}[{outlbl}];")
                    cur = outlbl
                fc = "".join(parts).rstrip(";")
                # bo dau map [vout]
                map_v = "[vout]"
                self.log(f"che logo (nhe) vung: {','.join(regions)}")
            else:
                fc = None
                map_v = None

            # cat 2.5s cuoi
            dur = self._probe_duration(ff, path)
            trim_to = max(0.5, dur - 2.5) if dur > 3.0 else dur

            tmp = path + ".proc.mp4"
            cmd = [ff, "-hide_banner", "-loglevel", "error", "-y", "-i", path]
            if fc:
                cmd += ["-filter_complex", fc, "-map", map_v, "-map", "0:a?"]
            if dur > 3.0:
                cmd += ["-t", f"{trim_to:.3f}"]
            # neu co blur phai re-encode video; audio copy
            if fc:
                cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "copy", tmp]
            else:
                cmd += ["-c", "copy", tmp]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=400)
            if r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
                os.replace(tmp, path)
                if dur > 3.0:
                    self.log(f"da cat 2.5s cuoi ({dur:.1f}s -> {trim_to:.1f}s)")
            else:
                if os.path.exists(tmp):
                    os.remove(tmp)
                self.log(f"xu ly video loi: {(r.stderr or '')[:100]}")
        except Exception as e:
            self.log(f"xu ly video loi: {str(e)[:80]}")
        return path


# ============================= APP =============================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Vizard Auto-Clip Tool v{APP_VERSION}")
        self.root.geometry("1000x760")
        self.root.minsize(860, 620)

        self.uiq = queue.Queue()
        self.stop_event = threading.Event()
        self.counter_lock = threading.Lock()
        self.n_ok = self.n_fail = self.n_total = 0

        # config vars
        self.gpm_url_v = tk.StringVar(value="http://127.0.0.1:9495/api/v1")
        self.gpm_status = tk.StringVar(value="Chua ket noi")
        self.input_v = tk.StringVar()
        self.output_v = tk.StringVar()
        self.threads_v = tk.IntVar(value=2)
        self.tabs_v = tk.IntVar(value=1)
        self.ratio_v = tk.StringVar(value="9:16")
        self.clip_len_v = tk.StringVar(value="Any length")
        self.model_v = tk.StringVar(value="v1")
        self.template_v = tk.StringVar(value="Default")
        self.emojis_v = tk.BooleanVar(value=True)
        self.keywords_v = tk.BooleanVar(value=True)
        self.brolls_v = tk.BooleanVar(value=False)
        self.silences_v = tk.BooleanVar(value=False)
        self.censor_v = tk.BooleanVar(value=False)
        self.blur_wm_v = tk.BooleanVar(value=True)
        self.hidden_v = tk.BooleanVar(value=True)
        # YouTube search vars
        self.yt_kw_v = tk.StringVar()
        self.yt_min_v = tk.IntVar(value=0)
        self.yt_max_v = tk.IntVar(value=0)
        self.yt_limit_v = tk.IntVar(value=15)
        self.status_var = tk.StringVar(value="San sang")
        self.progress_var = tk.IntVar(value=0)
        self.stats_var = tk.StringVar(value="Thanh cong: 0 | Loi: 0 | Tong: 0")

        self.build_ui()
        self.load_state()
        self.root.after(200, self.poll_ui)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def build_ui(self):
        outer = ttk.Frame(self.root, padding=8); outer.pack(fill="both", expand=True)

        # GPM row
        top = ttk.Frame(outer); top.pack(fill="x")
        ttk.Label(top, text="GPM API:").pack(side="left")
        ttk.Entry(top, textvariable=self.gpm_url_v, width=32).pack(side="left", padx=4)
        ttk.Button(top, text="Test GPM", command=self.test_gpm).pack(side="left")
        ttk.Button(top, text="Cap nhat", command=self.check_update).pack(side="left", padx=4)
        ttk.Label(top, textvariable=self.gpm_status, foreground="#0a7").pack(side="left", padx=6)
        ttk.Button(top, text="STOP", command=self.stop).pack(side="right", padx=4)
        ttk.Button(top, text="BAT DAU", command=self.start_jobs).pack(side="right")
        ttk.Button(top, text="Reset", command=self.reset).pack(side="right", padx=4)

        # input selection
        inf = ttk.LabelFrame(outer, text="Nguon video", padding=6); inf.pack(fill="x", pady=(8,0))
        row1 = ttk.Frame(inf); row1.pack(fill="x")
        ttk.Entry(row1, textvariable=self.input_v).pack(side="left", fill="x", expand=True, padx=(0,4))
        ttk.Button(row1, text="Chon Folder", command=self.pick_folder).pack(side="left", padx=2)
        ttk.Button(row1, text="Chon File", command=self.pick_files).pack(side="left", padx=2)
        self.selfiles = []  # explicit file list when using "Chon File"

        # output
        outf = ttk.Frame(inf); outf.pack(fill="x", pady=(6,0))
        ttk.Label(outf, text="Output goc:").pack(side="left")
        ttk.Entry(outf, textvariable=self.output_v).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(outf, text="Browse", command=lambda: self.output_v.set(
            filedialog.askdirectory() or self.output_v.get())).pack(side="left")
        ttk.Label(inf, text="(Clip gop theo folder: AI Vizard/<ten-folder-con>/)",
                  foreground="#888").pack(anchor="w", pady=(3,0))

        # ---- YouTube panel ----
        yf = ttk.LabelFrame(outer, text="Tim video YouTube (tuy chon)", padding=6); yf.pack(fill="x", pady=(8,0))
        yr = ttk.Frame(yf); yr.pack(fill="x")
        ttk.Label(yr, text="Tu khoa:").pack(side="left")
        ttk.Entry(yr, textvariable=self.yt_kw_v, width=30).pack(side="left", padx=4)
        ttk.Label(yr, text="Do dai (phut):").pack(side="left", padx=(8,2))
        ttk.Spinbox(yr, from_=0, to=180, textvariable=self.yt_min_v, width=4).pack(side="left")
        ttk.Label(yr, text="-").pack(side="left")
        ttk.Spinbox(yr, from_=0, to=180, textvariable=self.yt_max_v, width=4).pack(side="left")
        ttk.Label(yr, text="So kq:").pack(side="left", padx=(8,2))
        ttk.Spinbox(yr, from_=1, to=50, textvariable=self.yt_limit_v, width=4).pack(side="left")
        ttk.Button(yr, text="Tim", command=self.yt_search).pack(side="left", padx=4)
        ttk.Button(yr, text="Chon tat ca", command=lambda: self._yt_check_all(True)).pack(side="left", padx=2)
        ttk.Button(yr, text="Bo chon", command=lambda: self._yt_check_all(False)).pack(side="left", padx=2)
        # results tree (checkbox gia lap bang cot chon)
        yt_tree_f = ttk.Frame(yf); yt_tree_f.pack(fill="x", pady=(4,0))
        cols = ("pick","title","dur","views")
        self.yt_tree = ttk.Treeview(yt_tree_f, columns=cols, show="headings", height=6, selectmode="none")
        self.yt_tree.heading("pick", text="[v]"); self.yt_tree.column("pick", width=36, anchor="center")
        self.yt_tree.heading("title", text="Tieu de"); self.yt_tree.column("title", width=430)
        self.yt_tree.heading("dur", text="Thoi luong"); self.yt_tree.column("dur", width=80, anchor="center")
        self.yt_tree.heading("views", text="Luot xem"); self.yt_tree.column("views", width=80, anchor="center")
        self.yt_tree.pack(side="left", fill="x", expand=True)
        ysb = ttk.Scrollbar(yt_tree_f, orient="vertical", command=self.yt_tree.yview); ysb.pack(side="right", fill="y")
        self.yt_tree.configure(yscrollcommand=ysb.set)
        self.yt_tree.bind("<Button-1>", self._yt_toggle_row)
        self.yt_rows = {}   # iid -> result dict
        ttk.Label(yf, text="Bam vao dong de tick chon. Chay theo cau hinh ben duoi. Video khong logo thi tat 'Che mo logo'.",
                  foreground="#888").pack(anchor="w", pady=(3,0))

        # config panel
        cf = ttk.LabelFrame(outer, text="Cau hinh Vizard", padding=6); cf.pack(fill="x", pady=(8,0))
        r = ttk.Frame(cf); r.pack(fill="x")
        ttk.Label(r, text="Ratio:").grid(row=0, column=0, sticky="w", padx=4, pady=3)
        ttk.Combobox(r, textvariable=self.ratio_v, values=["9:16","1:1","16:9"], width=8, state="readonly").grid(row=0, column=1, padx=4)
        ttk.Label(r, text="Clip length:").grid(row=0, column=2, sticky="w", padx=4)
        ttk.Combobox(r, textvariable=self.clip_len_v, width=12, state="readonly",
                     values=["Any length","<30s","30s-60s","60s-90s","90s-3mins",">3mins"]).grid(row=0, column=3, padx=4)
        ttk.Label(r, text="Model:").grid(row=0, column=4, sticky="w", padx=4)
        ttk.Combobox(r, textvariable=self.model_v, values=["v1","v2"], width=6, state="readonly").grid(row=0, column=5, padx=4)
        ttk.Label(r, text="Template:").grid(row=0, column=6, sticky="w", padx=4)
        ttk.Combobox(r, textvariable=self.template_v, width=10, state="readonly",
                     values=["Default","Modern","Bouncy","Mr. Beast","Business","Blur","Fit video","Tech"]).grid(row=0, column=7, padx=4)
        ttk.Label(r, text="Profile:").grid(row=0, column=8, sticky="w", padx=4)
        ttk.Spinbox(r, from_=1, to=10, textvariable=self.threads_v, width=4).grid(row=0, column=9, padx=4)
        ttk.Label(r, text="Tab/profile:").grid(row=0, column=10, sticky="w", padx=4)
        ttk.Spinbox(r, from_=1, to=5, textvariable=self.tabs_v, width=4).grid(row=0, column=11, padx=4)

        cbf = ttk.Frame(cf); cbf.pack(fill="x", pady=(6,0))
        ttk.Checkbutton(cbf, text="Add emojis", variable=self.emojis_v).pack(side="left", padx=6)
        ttk.Checkbutton(cbf, text="Highlight keywords", variable=self.keywords_v).pack(side="left", padx=6)
        ttk.Checkbutton(cbf, text="Add B-rolls", variable=self.brolls_v).pack(side="left", padx=6)
        ttk.Checkbutton(cbf, text="Remove silences", variable=self.silences_v).pack(side="left", padx=6)
        ttk.Checkbutton(cbf, text="Auto-censor", variable=self.censor_v).pack(side="left", padx=6)
        ttk.Checkbutton(cbf, text="Che mo logo Vizard", variable=self.blur_wm_v).pack(side="left", padx=6)
        ttk.Label(cbf, text="(Cua so Chrome tu xep luoi 3x2 tren man hinh)", foreground="#888").pack(side="left", padx=6)

        # stats + progress
        st = ttk.Frame(outer); st.pack(fill="x", pady=(8,0))
        ttk.Label(st, textvariable=self.stats_var, font=("Segoe UI", 9, "bold")).pack(side="left")
        ttk.Label(st, textvariable=self.status_var).pack(side="left", padx=12)
        ttk.Progressbar(st, variable=self.progress_var, maximum=100).pack(side="right", fill="x", expand=True, padx=8)

        # log
        lf = ttk.LabelFrame(outer, text="Log", padding=4); lf.pack(fill="both", expand=True, pady=(8,0))
        self.results_log = tk.Text(lf, height=16, state="disabled", wrap="word", font=("Consolas", 9))
        self.results_log.pack(fill="both", expand=True)

    # ---- input pickers ----
    def pick_folder(self):
        d = filedialog.askdirectory()
        if d:
            self.selfiles = []
            self.input_v.set(d)
            if not self.output_v.get():
                self.output_v.set(d)

    def pick_files(self):
        fs = filedialog.askopenfilenames(
            filetypes=[("Video", "*.mp4 *.mov *.mkv *.avi *.3gp *.webm *.m4v *.flv *.wmv")])
        if fs:
            self.selfiles = list(fs)
            self.input_v.set(f"{len(fs)} file da chon")
            if not self.output_v.get():
                self.output_v.set(str(Path(fs[0]).parent))

    def collect_videos(self):
        if self.selfiles:
            return [Path(f) for f in self.selfiles if Path(f).suffix.lower() in VIDEO_EXTS]
        p = self.input_v.get().strip()
        if p and Path(p).is_dir():
            return sorted([f for f in Path(p).iterdir() if f.suffix.lower() in VIDEO_EXTS])
        return []

    # ---- YouTube search ----
    def yt_search(self):
        kw = self.yt_kw_v.get().strip()
        if not kw:
            return messagebox.showwarning("YouTube", "Nhap tu khoa tim kiem")
        self.yt_tree.delete(*self.yt_tree.get_children())
        self.yt_rows = {}
        self.log(f"Tim YouTube: {kw} ...")
        def run():
            try:
                mn = self.yt_min_v.get()*60; mx = self.yt_max_v.get()*60
                res = youtube_search(kw, limit=self.yt_limit_v.get(), min_sec=mn, max_sec=mx)
                self.uiq.put(("yt_results", res))
                self.uiq.put(("log", f"YouTube: tim thay {len(res)} video (loc do dai roi)"))
            except Exception as e:
                self.uiq.put(("log", f"YouTube loi: {e}"))
        threading.Thread(target=run, daemon=True).start()

    def _yt_fill(self, res):
        self.yt_tree.delete(*self.yt_tree.get_children())
        self.yt_rows = {}
        for r in res:
            iid = self.yt_tree.insert("", "end", values=("[ ]", r["title"], r["duration"], r["views"]))
            r["_checked"] = False
            self.yt_rows[iid] = r

    def _yt_toggle_row(self, event):
        row = self.yt_tree.identify_row(event.y)
        if not row or row not in self.yt_rows:
            return
        r = self.yt_rows[row]
        r["_checked"] = not r.get("_checked", False)
        vals = list(self.yt_tree.item(row, "values"))
        vals[0] = "[v]" if r["_checked"] else "[ ]"
        self.yt_tree.item(row, values=vals)

    def _yt_check_all(self, state):
        for iid, r in self.yt_rows.items():
            r["_checked"] = state
            vals = list(self.yt_tree.item(iid, "values"))
            vals[0] = "[v]" if state else "[ ]"
            self.yt_tree.item(iid, values=vals)

    def collect_yt_links(self):
        """Link da tick; neu khong tick gi thi lay TAT CA (theo yeu cau: lay ca tu tren xuong)."""
        checked = [r["url"] for r in self.yt_rows.values() if r.get("_checked")]
        if checked:
            return checked
        return [r["url"] for r in self.yt_rows.values()]

    # ---- logging / ui pump ----
    def log(self, s):
        self.uiq.put(("log", f"{time.strftime('%H:%M:%S')} {s}"))

    def bump(self, ok):
        with self.counter_lock:
            if ok: self.n_ok += 1
            else: self.n_fail += 1
            done = self.n_ok + self.n_fail
            self.uiq.put(("stats", (self.n_ok, self.n_fail, self.n_total)))
            if self.n_total:
                self.uiq.put(("progress", int(done*100/self.n_total)))

    def poll_ui(self):
        try:
            while True:
                k, *rest = self.uiq.get_nowait()
                if k == "log":
                    self.results_log.config(state="normal")
                    self.results_log.insert("end", rest[0] + "\n")
                    self.results_log.see("end")
                    self.results_log.config(state="disabled")
                elif k == "status":
                    self.status_var.set(rest[0])
                elif k == "progress":
                    self.progress_var.set(int(rest[0]))
                elif k == "gpm_status":
                    self.gpm_status.set(rest[0])
                elif k == "stats":
                    ok, fail, tot = rest[0]
                    self.stats_var.set(f"Thanh cong: {ok} | Loi: {fail} | Tong: {tot}")
                elif k == "yt_results":
                    self._yt_fill(rest[0])
                elif k == "update_msg":
                    title, msg = rest[0]
                    messagebox.showinfo(title, msg)
        except queue.Empty:
            pass
        self.root.after(200, self.poll_ui)

    # ---- gpm test ----
    def test_gpm(self):
        def run():
            try:
                gpm = GPMClient(self.gpm_url_v.get().strip())
                tool = gpm.list_tool_profiles()
                self.uiq.put(("gpm_status", f"OK - {len(tool)} profile vizard-tool"))
                self.uiq.put(("log", f"GPM ket noi OK, {len(tool)} profile vizard-tool san co"))
            except Exception as e:
                self.uiq.put(("gpm_status", "Loi"))
                self.uiq.put(("log", f"GPM loi: {e}"))
        threading.Thread(target=run, daemon=True).start()

    def check_update(self):
        """Keo ban moi nhat tu GitHub (git pull). Bao restart neu co thay doi."""
        def run():
            git = shutil.which("git") or "git"
            if not (APP_DIR / ".git").exists():
                self.uiq.put(("log", "Chua phai ban tai tu GitHub (khong co .git) - khong the tu cap nhat."))
                return
            try:
                self.uiq.put(("log", f"Dang kiem tra cap nhat (ban hien tai v{APP_VERSION})..."))
                subprocess.run([git, "fetch"], cwd=str(APP_DIR),
                               capture_output=True, text=True, timeout=60)
                r = subprocess.run([git, "pull", "--ff-only"], cwd=str(APP_DIR),
                                   capture_output=True, text=True, timeout=120)
                out = (r.stdout + r.stderr).strip()
                if r.returncode != 0:
                    self.uiq.put(("log", f"Cap nhat loi: {out}"))
                    self.uiq.put(("update_msg", ("Loi", f"Khong cap nhat duoc:\n{out}")))
                    return
                if "Already up to date" in out or "up-to-date" in out:
                    self.uiq.put(("log", "Da la ban moi nhat."))
                    self.uiq.put(("update_msg", ("Cap nhat", "Ban dang dung phien ban moi nhat.")))
                else:
                    self.uiq.put(("log", f"Da cap nhat:\n{out}"))
                    self.uiq.put(("update_msg", ("Cap nhat xong",
                        "Da tai ban moi. Vui long DONG va MO LAI phan mem de ap dung.")))
            except Exception as e:
                self.uiq.put(("log", f"Cap nhat loi: {e}"))
        threading.Thread(target=run, daemon=True).start()

    # ---- start / stop ----
    def reset(self):
        self.results_log.config(state="normal"); self.results_log.delete("1.0","end"); self.results_log.config(state="disabled")
        self.n_ok = self.n_fail = self.n_total = 0
        self.progress_var.set(0)
        self.stats_var.set("Thanh cong: 0 | Loi: 0 | Tong: 0")
        self.status_var.set("San sang")

    def cfg_dict(self):
        return {
            "ratio": self.ratio_v.get(), "clip_length": self.clip_len_v.get(),
            "model": self.model_v.get(), "template": self.template_v.get(),
            "add_emojis": self.emojis_v.get(), "highlight_keywords": self.keywords_v.get(),
            "add_brolls": self.brolls_v.get(), "remove_silences": self.silences_v.get(),
            "auto_censor": self.censor_v.get(),
            "blur_watermark": self.blur_wm_v.get(), "hidden": self.hidden_v.get(), "timeout": 1800,
        }

    def start_jobs(self):
        # gom viec: file/folder + link YouTube (neu co ket qua)
        jobs = []
        for v in self.collect_videos():
            jobs.append(("file", str(v)))
        yt_links = self.collect_yt_links() if getattr(self, "yt_rows", None) else []
        for url in yt_links:
            jobs.append(("link", url))
        if not jobs:
            return messagebox.showwarning("Video", "Chua chon video (file/folder) hoac tim+chon video YouTube")
        out_root = self.output_v.get().strip()
        if not out_root:
            # neu chi co link ma chua chon output -> hoi
            first_file = next((j[1] for j in jobs if j[0]=="file"), None)
            if first_file:
                out_root = str(Path(first_file).parent)
            else:
                out_root = filedialog.askdirectory(title="Chon thu muc luu clip")
                if not out_root:
                    return
            self.output_v.set(out_root)
        self.reset()
        self.n_total = len(jobs)
        self.uiq.put(("stats", (0, 0, self.n_total)))
        self.stop_event.clear()
        self.save_state()
        nprofiles = max(1, min(10, self.threads_v.get()))
        tabs_per = max(1, min(5, self.tabs_v.get()))
        nf = sum(1 for j in jobs if j[0]=="file"); nl = len(jobs)-nf
        self.log(f"Bat dau: {nf} file + {nl} link YouTube")
        t = threading.Thread(target=self._orchestrate,
                             args=(jobs, Path(out_root), self.cfg_dict(), nprofiles, tabs_per), daemon=True)
        t.start()

    def stop(self):
        self.stop_event.set()
        self.log("Da yeu cau dung...")

    # ---- orchestration ----
    def _orchestrate(self, jobs, out_root, cfg, nprofiles, tabs_per):
        try:
            gpm = GPMClient(self.gpm_url_v.get().strip())
            self.log(f"Chuan bi {nprofiles} profile GPM (x{tabs_per} tab/profile)...")
            pool = gpm.list_tool_profiles()
            self.profile_pool = [p["id"] for p in pool]   # profiles san co (dung + du phong khi het credit)
            # tao them neu chua du
            while len(self.profile_pool) < nprofiles:
                pid = gpm.create_profile(f"vizard_worker_{len(self.profile_pool)+1}")
                if not pid:
                    break
                self.profile_pool.append(pid)
                self.log(f"Tao profile moi: {pid}")
            if not self.profile_pool:
                self.log("Khong co profile GPM nao!"); return
            self.pool_lock = threading.Lock()
            self.pool_idx = 0  # con tro profile tiep theo de cap phat
            self._hidden_flag = bool(cfg.get("hidden", False))

            ai_root = out_root / "AI Vizard"
            ai_root.mkdir(parents=True, exist_ok=True)

            # hang doi cong viec: moi item = (kind, payload, so_lan_da_thu)
            work_q = queue.Queue()
            for kind, payload in jobs:
                work_q.put((kind, payload, 0))

            active = min(nprofiles, len(self.profile_pool))
            self.uiq.put(("status", f"Dang chay {active} profile x {tabs_per} tab / {len(jobs)} video"))
            threads = []
            for wi in range(active):
                th = threading.Thread(target=self._worker_thread,
                                      args=(wi, gpm, work_q, ai_root, cfg, tabs_per), daemon=True)
                th.start(); threads.append(th)
            for th in threads:
                th.join()
            self.uiq.put(("status", f"Xong! Thanh cong {self.n_ok}/{self.n_total}"))
            self.log(f"=== HOAN TAT: {self.n_ok}/{self.n_total} video, {self.n_fail} loi ===")
        except Exception as e:
            self.log(f"Orchestrate loi: {e}")

    def _next_profile(self):
        """Cap phat 1 profile ID chua dung tu pool (cho worker / khi doi profile het credit)."""
        with self.pool_lock:
            if self.pool_idx >= len(self.profile_pool):
                return None
            pid = self.profile_pool[self.pool_idx]
            self.pool_idx += 1
            return pid

    def _worker_thread(self, wi, gpm, work_q, ai_root, cfg, tabs_per):
        try:
            asyncio.run(self._worker_async(wi, gpm, work_q, ai_root, cfg, tabs_per))
        except Exception as e:
            self.log(f"[W{wi+1}] crash: {e}")

    async def _open_profile(self, wi, gpm, pid, tabs_per):
        """Start 1 profile GPM, attach, mo tabs_per tab. Tra (pw, browser, [pages])."""
        self.log(f"[W{wi+1}] start profile {pid}...")
        data = await asyncio.to_thread(gpm.start_profile, pid, False)
        ws = await asyncio.to_thread(GPMClient.ws_from_start, data)
        worker = VizardWorker(self.log)
        pw_obj, browser = await worker.attach(ws)
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        pages = list(ctx.pages)
        while len(pages) < tabs_per:
            pages.append(await ctx.new_page())
        pages = pages[:tabs_per]
        # chay ngam + force bat auto-download
        if self._hidden_flag:
            try:
                await self._hide_window(pages[0])
            except Exception as e:
                self.log(f"[W{wi+1}] khong the an cua so: {str(e)[:60]}")
        # force Chrome auto-download (khong hoi)
        try:
            cdp = await pages[0].context.new_cdp_session(pages[0])
            await cdp.send("Browser.setDownloadBehavior", {
                "behavior": "allow", "downloadPath": str(Path.home() / "Downloads")})
            await cdp.detach()
        except Exception:
            pass
        return pw_obj, browser, pages

    async def _hide_window(self, page):
        """Day cua so Chrome ra ngoai man hinh roi minimize (chay ngam)."""
        cdp = await page.context.new_cdp_session(page)
        try:
            info = await cdp.send("Browser.getWindowForTarget")
            wid = info["windowId"]
            await cdp.send("Browser.setWindowBounds", {
                "windowId": wid,
                "bounds": {"left": -32000, "top": -32000, "width": 1000, "height": 800}})
            await cdp.send("Browser.setWindowBounds", {
                "windowId": wid, "bounds": {"windowState": "minimized"}})
        finally:
            try: await cdp.detach()
            except Exception: pass

    async def _worker_async(self, wi, gpm, work_q, ai_root, cfg, tabs_per):
        worker = VizardWorker(self.log, blur_wm=cfg.get("blur_watermark", False))
        pid = self._next_profile()
        if not pid:
            return
        while pid and not self.stop_event.is_set():
            pw_obj = browser = None
            credit_dead = False
            try:
                pw_obj, browser, pages = await self._open_profile(wi, gpm, pid, tabs_per)
            except Exception as e:
                self.log(f"[W{wi+1}] mo profile {pid} loi: {str(e)[:80]} -> doi profile")
                if pw_obj:
                    try: await pw_obj.stop()
                    except Exception: pass
                pid = self._next_profile()
                continue

            # chay cac tab song song tren cung profile; tab nao gap het-credit se set co
            credit_flag = {"dead": False}
            try:
                await asyncio.gather(*[
                    self._tab_loop(wi, ti, worker, pages[ti], work_q, ai_root, cfg, credit_flag)
                    for ti in range(len(pages))
                ])
            finally:
                try:
                    if browser: await browser.close()
                except Exception: pass
                try:
                    if pw_obj: await pw_obj.stop()
                except Exception: pass
                await asyncio.to_thread(gpm.stop_profile, pid)
                self.log(f"[W{wi+1}] da dong profile {pid}")

            if credit_flag["dead"] and not self.stop_event.is_set():
                # profile het credit -> lay profile khac chay tiep (video da duoc requeue)
                newpid = self._next_profile()
                if newpid:
                    self.log(f"[W{wi+1}] profile {pid} het credit -> chuyen sang {newpid}")
                    pid = newpid
                    continue
                else:
                    self.log(f"[W{wi+1}] het profile du phong, dung.")
                    break
            else:
                break  # het viec binh thuong

    @staticmethod
    def _job_name(kind, payload):
        return Path(payload).name if kind == "file" else payload.split("/")[-1][:40]

    @staticmethod
    def _job_dest(ai_root, kind, payload):
        if kind == "file":
            # gop tat ca clip cua 1 bo phim (nhieu tap) vao 1 folder chung:
            # ai_root / "AI Vizard" / <ten-folder-con-chua-video> / (gop het clip vao day)
            src = Path(payload)
            # ten folder con (bo phim) = folder cha cua video
            series_folder = src.parent.name
            return ai_root / series_folder
        # link: khong co folder nguon -> dung Output goc truc tiep
        vid = payload.rsplit("=", 1)[-1].rsplit("/", 1)[-1][:20]
        return ai_root / f"yt_{vid}"

    async def _tab_loop(self, wi, ti, worker, page, work_q, ai_root, cfg, credit_flag):
        tag = f"W{wi+1}.T{ti+1}"
        while not self.stop_event.is_set() and not credit_flag["dead"]:
            try:
                kind, payload, attempts = work_q.get_nowait()
            except queue.Empty:
                return
            name = self._job_name(kind, payload)
            try:
                dest = self._job_dest(ai_root, kind, payload)
                if kind == "file":
                    files = await worker.process_video(page, payload, cfg, dest, self.stop_event.is_set)
                else:
                    files = await worker.process_link(page, payload, cfg, dest, self.stop_event.is_set)
                if files:
                    self.log(f"[{tag}] OK {name}: {len(files)} clip")
                    self.bump(True)
                else:
                    self._requeue(work_q, kind, payload, attempts, tag, "0 clip")
            except CreditExhausted:
                work_q.put((kind, payload, attempts))
                self.log(f"[{tag}] het credit -> tra {name} ve hang doi, doi profile")
                credit_flag["dead"] = True
                return
            except Exception as e:
                self._requeue(work_q, kind, payload, attempts, tag, str(e)[:80])
            finally:
                work_q.task_done()

    def _requeue(self, work_q, kind, payload, attempts, tag, reason):
        name = self._job_name(kind, payload)
        if attempts + 1 < MAX_ATTEMPTS:
            work_q.put((kind, payload, attempts + 1))
            self.log(f"[{tag}] {name} loi ({reason}) -> thu lai lan {attempts+2}/{MAX_ATTEMPTS}")
        else:
            self.log(f"[{tag}] {name} that bai sau {MAX_ATTEMPTS} lan ({reason})")
            self.bump(False)

    # ---- state ----
    def save_state(self):
        try:
            STATE_FILE.write_text(json.dumps({
                "gpm_url": self.gpm_url_v.get(), "output": self.output_v.get(),
                "threads": self.threads_v.get(), "tabs": self.tabs_v.get(), "ratio": self.ratio_v.get(),
                "clip_length": self.clip_len_v.get(), "model": self.model_v.get(),
                "template": self.template_v.get(),
                "emojis": self.emojis_v.get(), "keywords": self.keywords_v.get(),
                "brolls": self.brolls_v.get(), "silences": self.silences_v.get(),
                "censor": self.censor_v.get(), "blur_wm": self.blur_wm_v.get(),
                "hidden": self.hidden_v.get(),
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def load_state(self):
        if not STATE_FILE.exists(): return
        try:
            d = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            self.gpm_url_v.set(d.get("gpm_url", self.gpm_url_v.get()))
            self.output_v.set(d.get("output", ""))
            self.threads_v.set(d.get("threads", 2))
            self.tabs_v.set(d.get("tabs", 1))
            self.ratio_v.set(d.get("ratio", "9:16"))
            self.clip_len_v.set(d.get("clip_length", "Any length"))
            self.model_v.set(d.get("model", "v1"))
            self.template_v.set(d.get("template", "Default"))
            self.emojis_v.set(d.get("emojis", True))
            self.keywords_v.set(d.get("keywords", True))
            self.brolls_v.set(d.get("brolls", False))
            self.silences_v.set(d.get("silences", False))
            self.censor_v.set(d.get("censor", False))
            self.blur_wm_v.set(d.get("blur_wm", True))
            self.hidden_v.set(d.get("hidden", True))
        except Exception:
            pass

    def on_close(self):
        try:
            self.stop_event.set(); self.save_state()
        except Exception: pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
