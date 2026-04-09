#!/usr/bin/env python3
"""
Photo & Video Organizer  v1.1.0
- Year → Month folder sorting
- Custom rename format builder
- XMP sidecar support
- Safe cancel (keeps progress)
- Remembers last 2 source/dest folders
- Live progress dashboard
- Duplicate detection: size filter → MD5 hash
- Snapchat memories_history.json date import
"""

import os, re, shutil, threading, json, time, hashlib, urllib.request, base64, tempfile, sys
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

# ── Version ───────────────────────────────────────────────────────────────────
APP_VERSION   = "1.1.0"
UPDATE_URL    = "https://raw.githubusercontent.com/Nonflavored/photo-organizer/main/version.json"
DOWNLOAD_PAGE = "https://github.com/Nonflavored/photo-organizer/releases/latest"

# ── Embedded icon (base64 PNG 64x64) ─────────────────────────────────────────
ICON_B64 = ""  # Populated at build time — see build.bat

# ── EXIF ─────────────────────────────────────────────────────────────────────
try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

# ── File types ────────────────────────────────────────────────────────────────
PHOTO_EXTS = {
    ".jpg",".jpeg",".png",".heic",".heif",".tiff",".tif",".bmp",".webp",
    ".raw",".arw",".cr2",".cr3",".nef",".nrw",".orf",".rw2",".pef",".ptx",
    ".srw",".dng",".raf",".3fr",".mef",".erf",".mrw",".x3f",
}
VIDEO_EXTS = {
    ".mp4",".mov",".avi",".mkv",".wmv",".flv",".m4v",
    ".mts",".m2ts",".3gp",".webm",".mxf",".r3d",
}
ALL_MEDIA = PHOTO_EXTS | VIDEO_EXTS

MONTH_NAMES = {
    1:"01 - January",2:"02 - February",3:"03 - March",4:"04 - April",
    5:"05 - May",6:"06 - June",7:"07 - July",8:"08 - August",
    9:"09 - September",10:"10 - October",11:"11 - November",12:"12 - December",
}
MONTH_SHORT = {
    1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
    7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec",
}

CONFIG_PATH = Path(os.path.expanduser("~")) / ".photo_organizer_config.json"

# ── Theme ─────────────────────────────────────────────────────────────────────
BG,BG2,BG3     = "#111418","#1a1e24","#1e2229"
GOLD,GOLD2     = "#f5c842","#d4a800"
FG,FG_DIM      = "#e8e4dc","#8a8880"
GREEN,RED,BLUE = "#8ecf72","#e05c5c","#6ab0e0"
ORANGE,PURPLE  = "#e0923a","#b08ecf"
SNAP_YELLOW    = "#FFFC00"
FONT           = ("Courier New",10)
FONT_SM        = ("Courier New",9)
FONT_HDR       = ("Courier New",18,"bold")
FONT_MED       = ("Courier New",11,"bold")

# ── Config ────────────────────────────────────────────────────────────────────
def load_config():
    try:
        if CONFIG_PATH.exists():
            return json.loads(CONFIG_PATH.read_text())
    except Exception: pass
    return {}

def save_config(cfg):
    try: CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    except Exception: pass

def push_recent(cfg, key, value, limit=2):
    lst = cfg.get(key, [])
    if value in lst: lst.remove(value)
    lst.insert(0, value)
    cfg[key] = lst[:limit]

# ── Auto-update ───────────────────────────────────────────────────────────────
def parse_version(v):
    try: return tuple(int(x) for x in str(v).strip().split("."))
    except: return (0,0,0)

def check_for_update(callback):
    try:
        req = urllib.request.Request(UPDATE_URL, headers={"User-Agent":"PhotoOrganizer"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode())
        latest = data.get("version","0.0.0")
        notes  = data.get("notes","")
        if parse_version(latest) > parse_version(APP_VERSION):
            callback(latest, notes)
    except Exception: pass

# ── Snapchat JSON parser ──────────────────────────────────────────────────────
def load_snapchat_json(json_path: Path) -> dict:
    """
    Parses memories_history.json and returns a dict:
    uuid_lower -> datetime

    Snapchat filename format: 2022-09-30_<UUID>-main.mp4
    JSON entry format: { "Date": "2022-09-30 14:22:17 UTC", "Download Link": "...fsid=<UUID>..." }
    """
    lookup = {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        entries = data.get("Saved Media", [])
        for entry in entries:
            date_str     = entry.get("Date","")
            download_url = entry.get("Download Link","") or entry.get("Media Download Url","")

            # Parse date
            dt = None
            for fmt in ["%Y-%m-%d %H:%M:%S %Z", "%Y-%m-%d %H:%M:%S"]:
                try:
                    dt = datetime.strptime(date_str.replace(" UTC",""), fmt.replace(" %Z",""))
                    break
                except: pass
            if not dt:
                continue

            # Extract UUID from fsid= parameter
            m = re.search(r"fsid=([A-F0-9\-]{30,})", download_url, re.IGNORECASE)
            if m:
                uuid = m.group(1).lower()
                lookup[uuid] = dt

    except Exception as e:
        pass
    return lookup

def snapchat_date(path: Path, snap_lookup: dict):
    """Try to match this file's UUID to the Snapchat lookup table."""
    if not snap_lookup:
        return None
    # Filename pattern: 2022-09-30_<UUID>-main.ext or 2022-09-30_<UUID>.ext
    name = path.stem
    # Remove trailing -main if present
    name = re.sub(r'-main$', '', name, flags=re.IGNORECASE)
    # UUID is after the first underscore
    parts = name.split("_", 1)
    if len(parts) == 2:
        uuid = parts[1].lower()
        if uuid in snap_lookup:
            return snap_lookup[uuid]
    return None

# ── Date extraction ───────────────────────────────────────────────────────────
DATE_PATTERNS = [
    r"(\d{4})[_\-\.](\d{2})[_\-\.](\d{2})",
    r"(\d{4})(\d{2})(\d{2})[_\-]\d{6}",
    r"(\d{4})(\d{2})(\d{2})\d{6}",
    r"IMG[_\-]?(\d{4})(\d{2})(\d{2})",
    r"VID[_\-]?(\d{4})(\d{2})(\d{2})",
    r"(\d{2})[_\-\.](\d{2})[_\-\.](\d{4})",
]

def exif_info(path: Path):
    if not PILLOW_AVAILABLE or path.suffix.lower() not in PHOTO_EXTS:
        return None, None
    try:
        img = Image.open(path)
        raw = img._getexif()
        if not raw: return None, None
        dt, model = None, None
        for tid, val in raw.items():
            tag = TAGS.get(tid, tid)
            if tag in ("DateTimeOriginal","DateTime","DateTimeDigitized") and not dt:
                try: dt = datetime.strptime(val, "%Y:%m:%d %H:%M:%S")
                except: pass
            if tag == "Model" and not model:
                model = str(val).strip().replace(" ","_")
        return dt, model
    except: return None, None

def filename_date(path: Path):
    for pat in DATE_PATTERNS:
        m = re.search(pat, path.stem)
        if m:
            g = m.groups()
            try:
                if len(g[0]) == 4: y,mo,d = int(g[0]),int(g[1]),int(g[2])
                else:              d,mo,y = int(g[0]),int(g[1]),int(g[2])
                if 1900 < y < 2100 and 1 <= mo <= 12 and 1 <= d <= 31:
                    return datetime(y,mo,d)
            except ValueError: pass
    return None

def best_date_and_model(path: Path, snap_lookup: dict):
    # Snapchat JSON first (most precise for snap files)
    dt = snapchat_date(path, snap_lookup)
    if dt: return dt, None, "Snapchat"

    dt, model = exif_info(path)
    if dt: return dt, model, "EXIF"

    dt = filename_date(path)
    if dt: return dt, None, "Filename"

    return datetime.fromtimestamp(path.stat().st_mtime), None, "Modified"

# ── Duplicate detection ───────────────────────────────────────────────────────
HASH_CHUNK = 1024 * 1024

def file_md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(HASH_CHUNK):
            h.update(chunk)
    return h.hexdigest()

def find_duplicates(files: list, log_cb, progress_cb, cancel_flag):
    log_cb("info", f"Duplicate scan — pass 1: grouping {len(files):,} files by size...")
    size_groups = defaultdict(list)
    for p in files:
        try: size_groups[p.stat().st_size].append(p)
        except: pass

    candidates = {s: ps for s, ps in size_groups.items() if len(ps) > 1}
    candidate_count = sum(len(v) for v in candidates.values())
    log_cb("info", f"Pass 1 done — {candidate_count:,} files in {len(candidates):,} size groups need hashing")

    if not candidates:
        log_cb("info", "No size matches — no duplicates.")
        return {}

    log_cb("info", "Pass 2: MD5 hashing size matches...")
    hash_groups = defaultdict(list)
    processed = 0

    for size, paths in candidates.items():
        for p in paths:
            if cancel_flag():
                log_cb("warn", "Duplicate scan cancelled.")
                return {}
            try:
                h = file_md5(p)
                hash_groups[h].append(p)
                processed += 1
                progress_cb(processed, candidate_count, f"Hashing: {p.name}")
            except Exception as e:
                log_cb("err", f"✗ Hash failed {p.name}: {e}")

    dupes = {h: ps for h, ps in hash_groups.items() if len(ps) > 1}
    dupe_count = sum(len(v)-1 for v in dupes.values())
    log_cb("info", f"Pass 2 done — {dupe_count:,} duplicates across {len(dupes):,} groups")
    return dupes

# ── Rename tokens ─────────────────────────────────────────────────────────────
ALL_TOKENS = [
    {"id":"YYYY",  "label":"Year (4-digit)",    "example":"2022"},
    {"id":"YY",    "label":"Year (2-digit)",     "example":"22"},
    {"id":"MM",    "label":"Month (number)",     "example":"09"},
    {"id":"MON",   "label":"Month (short name)", "example":"Sep"},
    {"id":"DD",    "label":"Day",                "example":"15"},
    {"id":"NUM4",  "label":"Photo # (0001)",     "example":"0001"},
    {"id":"NUM",   "label":"Photo # (1)",        "example":"1"},
    {"id":"CAM",   "label":"Camera model",       "example":"ILCE-7RM5"},
    {"id":"ORIG",  "label":"Original filename",  "example":"_DSC0052"},
]
TOKEN_MAP      = {t["id"]: t for t in ALL_TOKENS}
DEFAULT_FORMAT = ["MM","DD","YY","NUM4"]

def render_filename(tokens, sep, dt, number, cam_model, orig_stem, suffix):
    parts = []
    for tok in tokens:
        if tok == "YYYY":   parts.append(str(dt.year))
        elif tok == "YY":   parts.append(f"{dt.year%100:02d}")
        elif tok == "MM":   parts.append(str(dt.month))
        elif tok == "MON":  parts.append(MONTH_SHORT[dt.month])
        elif tok == "DD":   parts.append(f"{dt.day:02d}")
        elif tok == "NUM4": parts.append(f"{number:04d}")
        elif tok == "NUM":  parts.append(str(number))
        elif tok == "CAM":  parts.append(cam_model or "Unknown")
        elif tok == "ORIG": parts.append(orig_stem)
    return sep.join(parts) + suffix.lower()

def fmt_time(s):
    if s < 60:   return f"{int(s)}s"
    if s < 3600: return f"{int(s//60)}m {int(s%60)}s"
    return f"{int(s//3600)}h {int((s%3600)//60)}m"

# ── File collection ───────────────────────────────────────────────────────────
def collect_files(source, recursive, log_cb):
    media, xmps = [], {}
    ext_counts = defaultdict(int)
    try:
        it = source.rglob("*") if recursive else source.iterdir()
        for p in it:
            if p.is_file():
                ext = p.suffix.lower()
                ext_counts[ext] += 1
                if ext in ALL_MEDIA:    media.append(p)
                elif ext == ".xmp":     xmps[(str(p.parent).lower(), p.stem.lower())] = p
    except Exception as e:
        log_cb("err", f"Scan error: {e}")
    if ext_counts:
        top = sorted(ext_counts.items(), key=lambda x:-x[1])[:6]
        log_cb("scan", "Extensions: " + ", ".join(f"{e}({n})" for e,n in top))
    return media, xmps

def safe_move(src, dst):
    if dst.exists():
        stem, suf = dst.stem, dst.suffix
        c = 1
        while dst.exists():
            dst = dst.parent / f"{stem}-x{c}{suf}"
            c += 1
    shutil.move(str(src), str(dst))
    return dst

# ── Core worker ───────────────────────────────────────────────────────────────
def run_job(source, dest, recursive, dry_run, fmt_tokens, fmt_sep,
            check_dupes, snap_json_path, cancel_flag, callbacks):

    log      = callbacks["log"]
    stat_cb  = callbacks["stat"]
    prog_cb  = callbacks["progress"]
    curr_cb  = callbacks["current"]
    done_cb  = callbacks["done"]
    phase_cb = callbacks["phase"]

    source = Path(os.path.normpath(str(source)))
    dest   = Path(os.path.normpath(str(dest)))

    log("scan", f"Scanning {source}...")
    if not source.exists():
        log("err", f"Source not found: {source}")
        done_cb(0,0,0,0,0,"error")
        return

    # ── Load Snapchat JSON if provided ────────────────────────────────────────
    snap_lookup = {}
    if snap_json_path:
        snap_path = Path(os.path.normpath(str(snap_json_path)))
        if snap_path.exists():
            phase_cb("LOADING SNAPCHAT DATA")
            log("info", f"Loading Snapchat data from: {snap_path.name}...")
            snap_lookup = load_snapchat_json(snap_path)
            log("info", f"Snapchat lookup ready — {len(snap_lookup):,} entries loaded")
        else:
            log("warn", f"Snapchat JSON not found: {snap_path}")

    # ── Collect files ─────────────────────────────────────────────────────────
    phase_cb("SCANNING")
    media, xmps = collect_files(source, recursive, log)
    total = len(media)
    if total == 0:
        log("warn", "No media files found.")
        done_cb(0,0,0,0,0,"empty")
        return

    log("info", f"Found {total:,} media files  +  {len(xmps):,} XMP sidecars")

    # ── Duplicate detection ───────────────────────────────────────────────────
    dupe_set = set()
    dupes_moved = 0

    if check_dupes:
        phase_cb("SCANNING DUPLICATES")
        log("divider","")
        log("info", "Starting duplicate detection...")

        dupe_groups = find_duplicates(media, log,
                                       lambda v,t,c="": (prog_cb(v,t,c), curr_cb(c)),
                                       cancel_flag)
        if cancel_flag():
            done_cb(0,0,0,0,0,"cancelled")
            return

        if dupe_groups:
            dupes_folder = dest / "_duplicates"
            if not dry_run:
                dupes_folder.mkdir(parents=True, exist_ok=True)
            log("divider","")
            log("info", f"Moving duplicates to _duplicates/...")
            for h, paths in dupe_groups.items():
                paths_sorted = sorted(paths, key=lambda p: p.stat().st_mtime)
                original = paths_sorted[0]
                log("info", f"  KEEP  {original.name}")
                for dp in paths_sorted[1:]:
                    dst_path = dupes_folder / dp.name
                    if not dry_run: safe_move(dp, dst_path)
                    action = "DRY→" if dry_run else "→"
                    log("warn", f"  DUPE  {dp.name}  {action}  _duplicates/")
                    dupe_set.add(str(dp))
                    dupes_moved += 1
            log("info", f"{dupes_moved:,} duplicates moved to _duplicates/")
        else:
            log("info", "No duplicates found.")
        log("divider","")

    # ── Organize ──────────────────────────────────────────────────────────────
    phase_cb("ORGANIZING")
    log("info", "Sorting files by date...")

    resolved = []
    for p in media:
        if str(p) in dupe_set: continue
        dt, cam, lbl = best_date_and_model(p, snap_lookup)
        resolved.append((p, dt, cam, lbl))
    resolved.sort(key=lambda x: x[1])

    tally = defaultdict(int)
    for _,_,_,lbl in resolved: tally[lbl]+=1
    log("info", "Date sources: " + "  |  ".join(f"{k}: {v:,}" for k,v in sorted(tally.items())))
    log("divider","")

    day_counters = defaultdict(int)
    moved = xmps_moved = errors = 0
    t0 = time.time()
    last_stat = 0
    org_total = len(resolved)

    for i, (src_path, dt, cam_model, src_lbl) in enumerate(resolved):
        if cancel_flag():
            log("warn", f"⚠  Cancelled after {moved:,} files. Progress kept.")
            done_cb(moved, xmps_moved, dupes_moved, errors, time.time()-t0, "cancelled")
            return

        try:
            year_str  = str(dt.year)
            month_str = MONTH_NAMES[dt.month]
            folder    = dest / year_str / month_str
            day_key   = (dt.year, dt.month, dt.day)
            day_counters[day_key] += 1
            number    = day_counters[day_key]

            new_name = render_filename(fmt_tokens, fmt_sep, dt, number,
                                        cam_model, src_path.stem, src_path.suffix)
            dst_path = folder / new_name

            if not dry_run:
                folder.mkdir(parents=True, exist_ok=True)
                safe_move(src_path, dst_path)
            moved += 1

            xmp_key = (str(src_path.parent).lower(), src_path.stem.lower())
            xmp_tag = ""
            if xmp_key in xmps:
                xmp_src  = xmps[xmp_key]
                xmp_stem = new_name.rsplit(".",1)[0]
                xmp_dst  = folder / f"{xmp_stem}.xmp"
                if not dry_run: safe_move(xmp_src, xmp_dst)
                xmps_moved += 1
                xmp_tag = " +xmp"

            src_lbl_display = "Snap" if src_lbl == "Snapchat" else src_lbl
            action = "DRY→" if dry_run else "→"
            curr_cb(f"{src_path.name}  {action}  {year_str}/{month_str}/{new_name}{xmp_tag}")
            log("file", f"[{src_lbl_display:8s}]  {src_path.name}  {action}  {new_name}{xmp_tag}")

        except Exception as e:
            log("err", f"✗ {src_path.name}: {e}")
            errors += 1

        now = time.time()
        elapsed = now - t0
        prog_cb(i+1, org_total)
        if now - last_stat > 0.3 or i == org_total-1:
            rate = (i+1)/elapsed if elapsed > 0 else 0
            rem  = (org_total-(i+1))/rate if rate > 0 else 0
            stat_cb({"done":moved,"xmps":xmps_moved,"dupes":dupes_moved,
                     "errors":errors,"rate":rate,"elapsed":elapsed,"remaining":rem})
            last_stat = now

    log("divider","")
    done_cb(moved, xmps_moved, dupes_moved, errors, time.time()-t0, "done")

# ── GUI Widgets ───────────────────────────────────────────────────────────────
class StatBox(tk.Frame):
    def __init__(self, parent, label, color=FG, **kw):
        super().__init__(parent, bg=BG2, padx=10, pady=8, **kw)
        tk.Label(self, text=label, bg=BG2, fg=FG_DIM, font=FONT_SM).pack(anchor="w")
        self._var = tk.StringVar(value="—")
        tk.Label(self, textvariable=self._var, bg=BG2, fg=color,
                  font=("Courier New",14,"bold")).pack(anchor="w")
    def set(self, v): self._var.set(str(v))

class UpdateBanner(tk.Frame):
    def __init__(self, parent, version, notes):
        super().__init__(parent, bg="#1a2a1a", pady=6, padx=14)
        msg = f"New version {version} available"
        if notes: msg += f"  —  {notes}"
        tk.Label(self, text=msg, bg="#1a2a1a", fg=GREEN, font=FONT_SM).pack(side="left")
        tk.Button(self, text="Download Update", bg=GREEN, fg="#111418",
                   font=FONT_SM, relief="flat", padx=8, pady=2, cursor="hand2",
                   command=lambda: os.startfile(DOWNLOAD_PAGE)).pack(side="left", padx=10)
        tk.Button(self, text="x", bg="#1a2a1a", fg=FG_DIM, font=FONT_SM,
                   relief="flat", padx=4, cursor="hand2",
                   command=self.destroy).pack(side="right")

class RenameBuilder(tk.Toplevel):
    def __init__(self, parent, current_tokens, current_sep, on_apply):
        super().__init__(parent)
        self.title("Rename Format Builder")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()
        self.on_apply = on_apply
        self.tokens   = list(current_tokens)
        self.sep_var  = tk.StringVar(value=current_sep)
        self._build()
        self._refresh()
        self.geometry("+%d+%d" % (parent.winfo_rootx()+60, parent.winfo_rooty()+60))

    def _build(self):
        tk.Label(self, text="RENAME FORMAT BUILDER", bg=BG, fg=GOLD,
                  font=("Courier New",13,"bold")).pack(pady=(14,2), padx=20, anchor="w")
        tk.Label(self, text="Add tokens, reorder with arrows, remove with x. Preview updates live.",
                  bg=BG, fg=FG_DIM, font=FONT_SM).pack(padx=20, anchor="w")

        sep_row = tk.Frame(self, bg=BG)
        sep_row.pack(fill="x", padx=20, pady=(10,4))
        tk.Label(sep_row, text="Separator:", bg=BG, fg=FG, font=FONT).pack(side="left")
        for label, val in [("Dash -","-"),("Underscore _","_"),("Dot .",".")]:
            tk.Radiobutton(sep_row, text=label, variable=self.sep_var, value=val,
                           bg=BG, fg=FG, selectcolor=BG3,
                           activebackground=BG, activeforeground=GOLD,
                           font=FONT, command=self._refresh).pack(side="left", padx=8)

        tk.Label(self, text="YOUR FORMAT:",
                  bg=BG, fg=FG_DIM, font=FONT_SM).pack(padx=20, anchor="w", pady=(8,2))
        self.token_frame = tk.Frame(self, bg=BG2, pady=8, padx=8, height=52)
        self.token_frame.pack(fill="x", padx=20)

        tk.Label(self, text="ADD TOKEN:", bg=BG, fg=FG_DIM,
                  font=FONT_SM).pack(padx=20, anchor="w", pady=(10,2))
        avail = tk.Frame(self, bg=BG)
        avail.pack(fill="x", padx=20)
        row = None
        for idx, tok in enumerate(ALL_TOKENS):
            if idx % 4 == 0:
                row = tk.Frame(avail, bg=BG)
                row.pack(fill="x", pady=1)
            tk.Button(row, text=f"+ {tok['label']}",
                       bg=BG3, fg=FG, font=FONT_SM, relief="flat",
                       padx=8, pady=4, cursor="hand2",
                       command=lambda t=tok["id"]: self._add(t)).pack(side="left", padx=(0,4))

        tk.Label(self, text="PREVIEW:", bg=BG, fg=FG_DIM,
                  font=FONT_SM).pack(padx=20, anchor="w", pady=(12,2))
        self._preview_var = tk.StringVar()
        tk.Label(self, textvariable=self._preview_var, bg=BG2, fg=GOLD,
                  font=("Courier New",12,"bold"), pady=8, padx=14,
                  anchor="w").pack(fill="x", padx=20)

        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(fill="x", padx=20, pady=14)
        tk.Button(btn_row, text="Apply", bg=GOLD, fg="#111418",
                   font=FONT_MED, relief="flat", padx=12, pady=6,
                   cursor="hand2", command=self._apply).pack(side="left")
        tk.Button(btn_row, text="Reset default", bg=BG3, fg=FG,
                   font=FONT, relief="flat", padx=10, pady=6,
                   cursor="hand2", command=self._reset).pack(side="left", padx=8)
        tk.Button(btn_row, text="Cancel", bg=BG3, fg=FG,
                   font=FONT, relief="flat", padx=10, pady=6,
                   cursor="hand2", command=self.destroy).pack(side="left")

    def _refresh(self):
        for w in self.token_frame.winfo_children(): w.destroy()
        for i, tok_id in enumerate(self.tokens):
            tok = TOKEN_MAP.get(tok_id)
            if not tok: continue
            cell = tk.Frame(self.token_frame, bg=BG3, padx=6, pady=4)
            cell.pack(side="left", padx=(0,4))
            tk.Label(cell, text=tok["label"], bg=BG3, fg=FG, font=FONT_SM).pack(side="left")
            nav = tk.Frame(cell, bg=BG3)
            nav.pack(side="left", padx=(4,0))
            if i > 0:
                tk.Button(nav, text="<", bg=BG3, fg=GOLD, font=FONT_SM,
                           relief="flat", cursor="hand2", padx=2,
                           command=lambda x=i: self._move(x,-1)).pack(side="left")
            if i < len(self.tokens)-1:
                tk.Button(nav, text=">", bg=BG3, fg=GOLD, font=FONT_SM,
                           relief="flat", cursor="hand2", padx=2,
                           command=lambda x=i: self._move(x,1)).pack(side="left")
            tk.Button(nav, text="x", bg=BG3, fg=RED, font=FONT_SM,
                       relief="flat", cursor="hand2", padx=2,
                       command=lambda x=i: self._remove(x)).pack(side="left")

        sep    = self.sep_var.get()
        sample = render_filename(self.tokens, sep, datetime(2022,9,15), 1,
                                  "ILCE-7RM5", "_DSC0052", "")
        self._preview_var.set(sample if self.tokens else "(no tokens — add some above)")

    def _add(self, tok_id):    self.tokens.append(tok_id); self._refresh()
    def _remove(self, i):      self.tokens.pop(i); self._refresh()
    def _move(self, i, d):
        j = i+d; self.tokens[i],self.tokens[j] = self.tokens[j],self.tokens[i]; self._refresh()
    def _reset(self):          self.tokens = list(DEFAULT_FORMAT); self._refresh()
    def _apply(self):
        if not self.tokens:
            messagebox.showerror("Error","Add at least one token.",parent=self); return
        self.on_apply(list(self.tokens), self.sep_var.get())
        self.destroy()

# ── Main App ──────────────────────────────────────────────────────────────────
class OrganizerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Photo & Video Organizer  v{APP_VERSION}")
        self.geometry("940x900")
        self.resizable(True, True)
        self.configure(bg=BG)

        # Set window icon
        self._set_icon()

        self.cfg = load_config()
        self._cancel_requested = False
        self._running = False
        self.fmt_tokens = list(self.cfg.get("fmt_tokens", DEFAULT_FORMAT))
        self.fmt_sep    = self.cfg.get("fmt_sep", "-")

        self._build()
        self._load_recent()
        threading.Thread(target=check_for_update,
                          args=(self._on_update_found,), daemon=True).start()

    def _set_icon(self):
        try:
            icon_path = Path(sys.executable).parent / "icon.ico"
            if not icon_path.exists():
                icon_path = Path(__file__).parent / "icon.ico"
            if icon_path.exists():
                self.iconbitmap(str(icon_path))
        except Exception:
            pass

    def _on_update_found(self, version, notes):
        self.after(0, lambda: UpdateBanner(self, version, notes).pack(
            fill="x", padx=0, pady=0, before=self._hdr_frame))

    def _build(self):
        # Header
        self._hdr_frame = tk.Frame(self, bg=BG)
        self._hdr_frame.pack(fill="x", padx=20, pady=(16,4))
        tk.Label(self._hdr_frame, text="PHOTO ORGANIZER", bg=BG, fg=GOLD,
                  font=FONT_HDR).pack(side="left")
        tk.Label(self._hdr_frame, text=f"v{APP_VERSION}", bg=BG, fg=FG_DIM,
                  font=FONT_SM).pack(side="left", padx=8)
        self._phase_var = tk.StringVar(value="READY")
        tk.Label(self._hdr_frame, textvariable=self._phase_var,
                  bg=BG, fg=FG_DIM, font=FONT_SM).pack(side="right")

        tk.Frame(self, bg="#2a2e36", height=1).pack(fill="x", padx=20, pady=4)

        # Folder rows
        self._folder_row("SOURCE FOLDER",  "src_var", "src_recent", self._pick_src)
        self._folder_row("DESTINATION FOLDER  (leave blank = organize in-place)",
                          "dst_var", "dst_recent", self._pick_dst)

        # Snapchat JSON row
        snap_frame = tk.Frame(self, bg=BG)
        snap_frame.pack(fill="x", padx=20, pady=3)
        snap_hdr = tk.Frame(snap_frame, bg=BG)
        snap_hdr.pack(fill="x")
        self.snap_var = tk.BooleanVar(value=False)
        tk.Checkbutton(snap_hdr, text="Snapchat export  (memories_history.json)",
                        variable=self.snap_var, bg=BG, fg=SNAP_YELLOW,
                        selectcolor=BG3, activebackground=BG,
                        activeforeground=SNAP_YELLOW,
                        font=("Courier New",10,"bold"),
                        command=self._toggle_snap).pack(side="left")
        self.snap_row = tk.Frame(snap_frame, bg=BG)
        self.snap_json_var = tk.StringVar()
        self.snap_entry = tk.Entry(self.snap_row, textvariable=self.snap_json_var,
                                    bg=BG3, fg=FG, insertbackground=GOLD,
                                    font=FONT, relief="flat", bd=6)
        self.snap_entry.pack(side="left", fill="x", expand=True)
        tk.Button(self.snap_row, text="Browse", bg=BG3, fg=FG, font=FONT,
                   relief="flat", padx=10, cursor="hand2",
                   command=self._pick_snap).pack(side="left", padx=(4,0))

        # Rename format
        fmt_row = tk.Frame(self, bg=BG)
        fmt_row.pack(fill="x", padx=20, pady=(2,4))
        tk.Label(fmt_row, text="Rename format:", bg=BG, fg=FG_DIM, font=FONT_SM).pack(side="left")
        self._fmt_preview_var = tk.StringVar()
        tk.Label(fmt_row, textvariable=self._fmt_preview_var,
                  bg=BG, fg=GOLD, font=FONT_SM).pack(side="left", padx=8)
        tk.Button(fmt_row, text="Customize", bg=BG3, fg=FG,
                   font=FONT_SM, relief="flat", padx=8, pady=2,
                   cursor="hand2", command=self._open_builder).pack(side="left")
        self._update_fmt_preview()

        # Options
        opt = tk.Frame(self, bg=BG)
        opt.pack(fill="x", padx=20, pady=(0,4))
        self.recursive_var = tk.BooleanVar(value=self.cfg.get("recursive", True))
        self.dryrun_var    = tk.BooleanVar(value=False)
        self.dedup_var     = tk.BooleanVar(value=self.cfg.get("dedup", False))
        for text, var, color in [
            ("Scan subfolders recursively", self.recursive_var, FG),
            ("Dry run  (preview only)", self.dryrun_var, FG),
            ("Find & move duplicates", self.dedup_var, PURPLE),
        ]:
            tk.Checkbutton(opt, text=text, variable=var,
                           bg=BG, fg=color, selectcolor=BG3,
                           activebackground=BG, activeforeground=GOLD,
                           font=FONT).pack(side="left", padx=(0,20))

        # Run / Cancel
        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(fill="x", padx=20, pady=(4,6))
        self.run_btn = tk.Button(btn_row, text="ORGANIZE & RENAME",
                                  bg=GOLD, fg="#111418", font=FONT_MED,
                                  relief="flat", padx=16, pady=7,
                                  cursor="hand2", command=self._run)
        self.run_btn.pack(side="left")
        self.cancel_btn = tk.Button(btn_row, text="CANCEL",
                                     bg=BG3, fg=RED, font=FONT_MED,
                                     relief="flat", padx=12, pady=7,
                                     cursor="hand2", command=self._cancel,
                                     state="disabled")
        self.cancel_btn.pack(side="left", padx=8)

        # Progress
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("G.Horizontal.TProgressbar",
                         background=GOLD, troughcolor=BG3,
                         bordercolor=BG, lightcolor=GOLD, darkcolor=GOLD2)
        style.configure("P.Horizontal.TProgressbar",
                         background=PURPLE, troughcolor=BG3,
                         bordercolor=BG, lightcolor=PURPLE, darkcolor=PURPLE)
        style.configure("S.Horizontal.TProgressbar",
                         background=SNAP_YELLOW, troughcolor=BG3,
                         bordercolor=BG, lightcolor=SNAP_YELLOW, darkcolor=SNAP_YELLOW)
        self.progress = ttk.Progressbar(self, style="G.Horizontal.TProgressbar",
                                         mode="determinate")
        self.progress.pack(fill="x", padx=20, pady=(0,4))

        # Stat boxes
        sb_frame = tk.Frame(self, bg=BG)
        sb_frame.pack(fill="x", padx=20, pady=(0,4))
        self.sb_moved   = StatBox(sb_frame, "FILES MOVED",   color=GREEN)
        self.sb_xmps    = StatBox(sb_frame, "XMPs MOVED",    color=BLUE)
        self.sb_dupes   = StatBox(sb_frame, "DUPES FOUND",   color=PURPLE)
        self.sb_errors  = StatBox(sb_frame, "ERRORS",        color=RED)
        self.sb_rate    = StatBox(sb_frame, "FILES / SEC",   color=FG)
        self.sb_elapsed = StatBox(sb_frame, "ELAPSED",       color=FG)
        self.sb_remain  = StatBox(sb_frame, "REMAINING",     color=GOLD)
        for b in (self.sb_moved,self.sb_xmps,self.sb_dupes,self.sb_errors,
                  self.sb_rate,self.sb_elapsed,self.sb_remain):
            b.pack(side="left", fill="x", expand=True, padx=(0,2))

        # Ticker
        tick = tk.Frame(self, bg=BG2, pady=5, padx=12)
        tick.pack(fill="x", padx=20, pady=(0,4))
        tk.Label(tick, text="NOW:", bg=BG2, fg=FG_DIM, font=FONT_SM).pack(side="left")
        self._curr_var = tk.StringVar(value="—")
        tk.Label(tick, textvariable=self._curr_var, bg=BG2, fg=GREEN,
                  font=FONT_SM, anchor="w").pack(side="left", fill="x", expand=True, padx=6)

        # Log
        log_f = tk.Frame(self, bg=BG)
        log_f.pack(fill="both", expand=True, padx=20, pady=(0,14))
        tk.Label(log_f, text="LOG", bg=BG, fg=FG_DIM, font=FONT_SM).pack(anchor="w")
        self.log = tk.Text(log_f, bg="#0d1014", fg=GREEN, font=FONT_SM,
                            relief="flat", state="disabled", wrap="none")
        sy = ttk.Scrollbar(log_f, orient="vertical",   command=self.log.yview)
        sx = ttk.Scrollbar(log_f, orient="horizontal", command=self.log.xview)
        self.log.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        sy.pack(side="right", fill="y")
        sx.pack(side="bottom", fill="x")
        self.log.pack(fill="both", expand=True)
        for tag,fg_ in [("err",RED),("warn",ORANGE),("info",BLUE),("scan",FG_DIM),
                         ("done",GOLD),("file",GREEN),("divider","#2a2e36"),
                         ("snap",SNAP_YELLOW)]:
            self.log.tag_config(tag, foreground=fg_)

    # ── Snapchat toggle ───────────────────────────────────────────────────────
    def _toggle_snap(self):
        if self.snap_var.get():
            self.snap_row.pack(fill="x", pady=(2,0))
        else:
            self.snap_row.pack_forget()

    def _pick_snap(self):
        f = filedialog.askopenfilename(
            title="Select memories_history.json",
            filetypes=[("JSON files","*.json"),("All files","*.*")]
        )
        if f: self.snap_json_var.set(os.path.normpath(f))

    # ── Folder rows ───────────────────────────────────────────────────────────
    def _folder_row(self, label, var_attr, recent_attr, cmd):
        f = tk.Frame(self, bg=BG)
        f.pack(fill="x", padx=20, pady=3)
        tk.Label(f, text=label, bg=BG, fg=FG, font=FONT).pack(anchor="w")
        row = tk.Frame(f, bg=BG)
        row.pack(fill="x")
        var = tk.StringVar()
        setattr(self, var_attr, var)
        tk.Entry(row, textvariable=var, bg=BG3, fg=FG, insertbackground=GOLD,
                  font=FONT, relief="flat", bd=6).pack(side="left", fill="x", expand=True)
        tk.Button(row, text="Browse", bg=BG3, fg=FG, font=FONT,
                   relief="flat", padx=10, cursor="hand2",
                   command=cmd).pack(side="left", padx=(4,0))
        rb = tk.Menubutton(row, text="Recent", bg=BG3, fg=FG_DIM,
                            font=FONT_SM, relief="flat", padx=6, cursor="hand2")
        rb.pack(side="left", padx=(2,0))
        menu = tk.Menu(rb, tearoff=0, bg=BG2, fg=FG,
                        activebackground=BG3, activeforeground=GOLD, font=FONT_SM)
        rb["menu"] = menu
        setattr(self, recent_attr, (menu, var))

    def _load_recent(self):
        for key, attr in [("recent_src","src_recent"),("recent_dst","dst_recent")]:
            menu, var = getattr(self, attr)
            menu.delete(0,"end")
            for path in self.cfg.get(key, []):
                menu.add_command(label=path, command=lambda p=path, v=var: v.set(p))
        if self.cfg.get("recent_src"): self.src_var.set(self.cfg["recent_src"][0])
        if self.cfg.get("recent_dst"): self.dst_var.set(self.cfg["recent_dst"][0])

    def _save_paths(self):
        src = self.src_var.get().strip()
        dst = self.dst_var.get().strip()
        if src: push_recent(self.cfg, "recent_src", src)
        if dst: push_recent(self.cfg, "recent_dst", dst)
        self.cfg["recursive"]  = self.recursive_var.get()
        self.cfg["fmt_tokens"] = self.fmt_tokens
        self.cfg["fmt_sep"]    = self.fmt_sep
        self.cfg["dedup"]      = self.dedup_var.get()
        save_config(self.cfg)
        self._load_recent()

    def _pick_src(self):
        d = filedialog.askdirectory(title="Select source folder")
        if d: self.src_var.set(os.path.normpath(d))

    def _pick_dst(self):
        d = filedialog.askdirectory(title="Select destination folder")
        if d: self.dst_var.set(os.path.normpath(d))

    def _open_builder(self):
        RenameBuilder(self, self.fmt_tokens, self.fmt_sep, self._apply_format)

    def _apply_format(self, tokens, sep):
        self.fmt_tokens = tokens; self.fmt_sep = sep; self._update_fmt_preview()

    def _update_fmt_preview(self):
        sample = render_filename(self.fmt_tokens, self.fmt_sep,
                                  datetime(2022,9,15), 1, "ILCE-7RM5", "_DSC0052", "")
        self._fmt_preview_var.set(f"->  {sample}")

    # ── Log & stats ───────────────────────────────────────────────────────────
    def _log(self, tag, msg):
        if tag == "divider": msg = "-"*70
        self.log.configure(state="normal")
        self.log.insert("end", msg+"\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0","end")
        self.log.configure(state="disabled")

    def _reset_stats(self):
        for b in (self.sb_moved,self.sb_xmps,self.sb_dupes,self.sb_errors,
                  self.sb_rate,self.sb_elapsed,self.sb_remain):
            b.set("—")
        self._curr_var.set("—")
        self.progress["value"] = 0

    def _on_stat(self, s):
        self.sb_moved.set(f"{s['done']:,}")
        self.sb_xmps.set(f"{s['xmps']:,}")
        self.sb_dupes.set(f"{s['dupes']:,}")
        self.sb_errors.set(f"{s['errors']:,}" if s['errors'] else "0")
        self.sb_rate.set(f"{s['rate']:.1f}")
        self.sb_elapsed.set(fmt_time(s['elapsed']))
        self.sb_remain.set(fmt_time(s['remaining']))

    def _on_progress(self, val, total, curr=""):
        self.progress["maximum"] = max(total,1)
        self.progress["value"]   = val
        if curr: self._curr_var.set(("..."+curr[-87:]) if len(curr)>90 else curr)
        self.update_idletasks()

    def _on_current(self, msg):
        self._curr_var.set(("..."+msg[-87:]) if len(msg)>90 else msg)

    def _on_phase(self, phase):
        self._phase_var.set(f"  {phase}")
        if "DUPLIC" in phase:
            self.progress.configure(style="P.Horizontal.TProgressbar")
        elif "SNAP" in phase:
            self.progress.configure(style="S.Horizontal.TProgressbar")
        else:
            self.progress.configure(style="G.Horizontal.TProgressbar")

    def _on_done(self, moved, xmps, dupes, errors, elapsed, status):
        self._running = False
        self._phase_var.set("DONE" if status=="done" else status.upper())
        self.run_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled", bg=BG3, text="CANCEL")
        dry = " (DRY RUN)" if self.dryrun_var.get() else ""
        if status == "cancelled":
            self._log("warn", f"Cancelled{dry}  —  {moved:,} files kept  +  {xmps:,} XMPs  in {fmt_time(elapsed)}")
            self._curr_var.set("Cancelled — progress kept")
        elif status == "done":
            dupe_note = f"  +  {dupes:,} dupes -> _duplicates/" if dupes else ""
            tag = "done" if errors==0 else "err"
            self._log(tag, f"Complete{dry}  —  {moved:,} files  +  {xmps:,} XMPs{dupe_note}  {errors} errors  in {fmt_time(elapsed)}")
            self._curr_var.set("Complete")
        else:
            self._log("warn", f"Status: {status}")

    def _cancel(self):
        if self._running:
            self._cancel_requested = True
            self.cancel_btn.configure(text="Cancelling...", state="disabled")
            self._log("warn","Cancel requested — finishing current file...")

    # ── Run ───────────────────────────────────────────────────────────────────
    def _run(self):
        src_str = self.src_var.get().strip()
        dst_str = self.dst_var.get().strip()
        if not src_str:
            messagebox.showerror("Error","Please select a source folder."); return
        src = Path(os.path.normpath(src_str))
        if not src.is_dir():
            messagebox.showerror("Error",f"Source folder not found:\n{src}"); return

        dst       = Path(os.path.normpath(dst_str)) if dst_str else src
        dry       = self.dryrun_var.get()
        recursive = self.recursive_var.get()
        dedup     = self.dedup_var.get()
        snap_json = self.snap_json_var.get().strip() if self.snap_var.get() else None

        if not dry and not dst.exists():
            dst.mkdir(parents=True, exist_ok=True)

        self._save_paths()
        self._clear_log()
        self._reset_stats()
        self._cancel_requested = False
        self._running = True

        self.run_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal", bg="#2a1818")

        if not PILLOW_AVAILABLE:
            self._log("warn","Pillow not installed — EXIF unavailable.")

        sample  = render_filename(self.fmt_tokens, self.fmt_sep,
                                   datetime(2022,9,15),1,"CAM","ORIG","")
        dry_lbl = "  [DRY RUN]" if dry else ""
        self._log("info", f"Source    : {src}{dry_lbl}")
        self._log("info", f"Dest      : {dst}")
        self._log("info", f"Recursive : {recursive}  |  Format: {sample}  |  Dedup: {dedup}  |  Snapchat: {bool(snap_json)}")
        self._log("divider","")

        callbacks = {
            "log":      lambda t,m:           self.after(0, self._log, t, m),
            "stat":     lambda s:             self.after(0, self._on_stat, s),
            "progress": lambda v,t,c="":      self.after(0, self._on_progress, v, t, c),
            "current":  lambda m:             self.after(0, self._on_current, m),
            "phase":    lambda p:             self.after(0, self._on_phase, p),
            "done":     lambda m,x,d,e,el,st: self.after(0, self._on_done, m,x,d,e,el,st),
        }

        threading.Thread(
            target=run_job,
            args=(src, dst, recursive, dry, list(self.fmt_tokens), self.fmt_sep,
                  dedup, snap_json, lambda: self._cancel_requested, callbacks),
            daemon=True
        ).start()

if __name__ == "__main__":
    app = OrganizerApp()
    app.mainloop()
