import subprocess
import time
import sys
import re
import json
import shutil
import os
import threading
import base64
import bz2
import hashlib
import csv
import urllib.request
import urllib.error
import zipfile
from pathlib import Path
from datetime import datetime, timedelta

import cv2
import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from vision_stream import VisionStream, AdbTapShell, find_ffmpeg, query_device_size

try:
    import pytesseract
    HAS_PYTESSERACT = True
except ImportError:
    HAS_PYTESSERACT = False

APP_VERSION = "7.2.0"

REFERENCE_W = 1536
REFERENCE_H = 709

# Program files may change on every update.
ROOT = Path(__file__).resolve().parent
TEMPLATE_DIR = ROOT / "templates"

# User files NEVER live inside the version/program folder anymore.
APPDATA_BASE = Path(os.environ.get("APPDATA", str(ROOT)))
PROFILE_DIR = APPDATA_BASE / "TG-BTC-Arena-Companion"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

DODGE_TEMPLATE_DIR = PROFILE_DIR / "owl_samples"
DODGE_TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

SESSION_JSON = PROFILE_DIR / "session.json"
SESSION_LOG = PROFILE_DIR / "arena_log.txt"
STATUS_TXT = PROFILE_DIR / "status.txt"
CSV_LOG = PROFILE_DIR / "match_history.csv"
INTEL_HISTORY_FILE = PROFILE_DIR / "match_intel.json"
HEALTH_EVENTS_FILE = PROFILE_DIR / "health_events.jsonl"
HEALTH_DEBUG_DIR = PROFILE_DIR / "health_debug"
HEALTH_DEBUG_DIR.mkdir(parents=True, exist_ok=True)

# V6.0 Arena Intelligence Suite persistent data.
INTELLIGENCE_SETTINGS_FILE = PROFILE_DIR / "intelligence_settings.json"
HERO_TEMPLATE_DIR = PROFILE_DIR / "hero_templates"
HERO_TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
HERO_LIBRARY_FILE = PROFILE_DIR / "hero_library.json"
MATCH_SNAPSHOT_DIR = PROFILE_DIR / "match_snapshots"
MATCH_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

DODGE_SETTINGS_FILE = PROFILE_DIR / "dodge_settings.json"
UPDATE_SETTINGS_FILE = PROFILE_DIR / "update_settings.json"
OPPONENT_SETTINGS_FILE = PROFILE_DIR / "opponent_settings.json"
UPDATE_CACHE_DIR = PROFILE_DIR / "update_cache"
UPDATE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Enemy side of the battle. Smart Dodge searches ONLY this region.
DODGE_ENEMY_ROI = (430, 35, 1536, 545)

# Owl samples are user-calibrated from an actual battle.
DEFAULT_DODGE_SETTINGS = {
    "enabled": False,
    "dodge_owl": True,
    "disable_at_master_plus": True,
    "owl_threshold": 0.74,
    "quit_ref": None,
    "confirm_ref": None
}

# V5.7.1 opponent identity rule:
#   no Organization line under the opponent username => BOT
#   Organization line present => REAL PERSON
DEFAULT_OPPONENT_SETTINGS = {
    "org_roi": None,
    "username_roi": None,
}

# V7.0 Full Game Assistant foundation — modular daily collectors.
DAILY_SETTINGS_FILE = PROFILE_DIR / "daily_modules.json"
DAILY_RUN_LOG_FILE = PROFILE_DIR / "daily_runs.jsonl"
DEFAULT_DAILY_SETTINGS = {
    "routes": {
        # Coordinates are normalized to REFERENCE_W x REFERENCE_H and were
        # derived from the user's recorded tap flows. They can be re-taught
        # from the Daily Assistant page if a future UI update moves them.
        "Mail": [[296, 142]],
        "Events": [[208, 598]],
        "Shop": [[102, 598], [152, 190]],
        "Recruit": [[1406, 380], [155, 280]],
        "Quest Pass": [[102, 598], [155, 555], [600, 660]],
        "Idle Rewards": [[1365, 590], [170, 145]],
        # Rotating login/sign-in event locations change between seasons.
        # Teach this route once for the currently active sign-in event.
        "Login": [],
    },
    "module_words": {
        "Mail": ["CLAIM ALL", "CLAIM"],
        "Events": ["CLAIM ALL", "CLAIM", "FREE"],
        "Shop": ["CLAIM ALL", "CLAIM", "FREE"],
        "Recruit": ["FREE"],
        "Quest Pass": ["CLAIM ALL", "CLAIM"],
        "Idle Rewards": ["CLAIM ALL", "CLAIM"],
        "Login": ["CLAIM ALL", "CLAIM", "FREE"],
        "Current Screen": ["CLAIM ALL", "CLAIM", "FREE"],
    },
}

# V7.1 visual route verification. Header anchors use OCR only on small stable
# title regions. HOME uses a compact perceptual hash because the Home screen
# does not expose a reliable title label to OCR.
DAILY_HOME_PHASH = 0x95CE4C994E8C99DC
DAILY_IDLE_POPUP_PHASH = 0xE4163759B3C6CC31
DAILY_ROUTE_EXPECTATIONS = {
    "Mail": ["MAIL"],
    "Events": ["EVENT"],
    "Shop": ["SHOP", "SHOP"],
    "Recruit": ["RECRUIT", "REGULAR_RECRUIT"],
    "Quest Pass": ["SHOP", "QUEST", "QUEST"],
    "Idle Rewards": ["CHAIN", "IDLE_POPUP"],
    "Login": [],
}
DAILY_FINAL_ANCHOR = {
    "Mail": "MAIL",
    "Events": "EVENT",
    "Shop": "SHOP",
    "Recruit": "REGULAR_RECRUIT",
    "Quest Pass": "QUEST",
    "Idle Rewards": "IDLE_POPUP",
}
DAILY_RUN_ALL_ORDER = ["Mail", "Shop", "Quest Pass", "Events", "Idle Rewards", "Login", "Recruit"]
DAILY_HOME_REF = (382, 40)
# V7.1.2 Turbo Daily: OCR at half reference size is ~2-3x faster on the
# recorded screens while preserving CLAIM / CLAIM ALL detection. Coordinates
# are mapped back to the 1536x709 reference canvas before any tap.
DAILY_OCR_SCALE = 0.60
DAILY_ROUTE_CHANGE_TIMEOUT = 0.85
DAILY_HOME_VERIFY_TIMEOUT = 0.80
# Known safe navigation tabs inside already-verified screens. These taps only
# switch pages; the collector still clicks content only when OCR reads an
# explicit CLAIM / CLAIM ALL / FREE action.
DAILY_SHOP_SCAN_TABS = [
    ("Daily Deal", (152, 190)),
    ("Event Pack", (152, 260)),
    ("Carnival Pass", (152, 328)),
    ("Monthly Login", (152, 388)),
    ("Growth Fund", (152, 526)),
]
DAILY_QUEST_SCAN_TABS = [
    ("Daily Quest", (470, 220)),
    ("Weekly", (470, 340)),
    ("Pass Reward", (470, 660)),
]

# V7.2 Vision-First Assistant. Stable recorded-screen fingerprints make route
# verification effectively instant. Safe-action recognition first uses OpenCV
# to isolate likely button regions, then performs one compact OCR confirmation
# pass. BUY / EXCHANGE / USE / SWEEP / START / GO NOW are never action targets.
VISION_SCREEN_SIGNATURES = {
    "HOME": {"rois": [(1160,220,1320,310),(0,0,320,95)], "hashes": [0x95CE4C9D4E8C995C, 0xC639394C86D6396D], "max_avg": 13.0},
    "MAIL": {"rois": [(55,0,320,90),(90,70,560,160)], "hashes": [0x8458A75F94D86557, 0x846E957B7B8161B1], "max_avg": 13.0},
    "SHOP": {"rois": [(55,0,320,90),(70,120,320,235)], "hashes": [0xC848B73FC8C07673, 0x902F2FC4E42FD6D0], "max_avg": 12.0},
    "QUEST": {"rois": [(55,0,320,90),(350,155,690,260),(80,555,350,705)], "hashes": [0xC8C0373FC8C83773, 0xB64D1F49C8493BA6, 0x88A8AA3E3EB6D1D1], "max_avg": 12.5},
    "EVENT": {"rois": [(55,0,320,90),(600,60,980,170)], "hashes": [0xC8C0373FD9C86627, 0x934B6E94B16B8A56], "max_avg": 13.0},
    "RECRUIT": {"rois": [(55,0,320,90),(70,300,430,440)], "hashes": [0xDA40A53FD8C06767, 0x9A263FB1E10CCE1B], "max_avg": 13.5},
    "CHAIN": {"rois": [(55,0,360,90),(40,90,450,220)], "hashes": [0xC8D0373FCCC83333, 0x9393346D4F6C3C64], "max_avg": 13.5},
    "IDLE_POPUP": {"rois": [(430,150,840,270)], "hashes": [0xCA35B2CDBD1A25C2], "max_avg": 14.0},
    "REWARD_OVERLAY": {"rois": [(450,110,1090,405)], "hashes": [0x87F88F6E708306F1], "max_avg": 14.0},
}

# Screen-aware OCR fallback regions. Coordinates are on the normalized
# 1536x709 reference canvas and deliberately exclude most navigation chrome.
VISION_ACTION_ROIS = {
    "MAIL": (430, 90, 1510, 690),
    "SHOP": (300, 70, 1510, 700),
    "QUEST": (300, 130, 1510, 705),
    "EVENT": (300, 70, 1510, 700),
    "RECRUIT": (760, 180, 1525, 705),
    "UNKNOWN": (250, 60, 1525, 705),
}
VISION_LIVE_INTERVAL_MS = 180
VISION_CANDIDATE_LIMIT = 12
VISION_OCR_SCALE = 0.72


def load_daily_settings():
    data = json.loads(json.dumps(DEFAULT_DAILY_SETTINGS))
    try:
        if DAILY_SETTINGS_FILE.exists():
            saved = json.loads(DAILY_SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                if isinstance(saved.get("routes"), dict):
                    data["routes"].update(saved["routes"])
                if isinstance(saved.get("module_words"), dict):
                    data["module_words"].update(saved["module_words"])
    except Exception:
        pass
    return data

daily_settings = load_daily_settings()
daily_settings_lock = threading.RLock()

def save_daily_settings():
    with daily_settings_lock:
        tmp = DAILY_SETTINGS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(daily_settings, indent=2), encoding="utf-8")
        os.replace(tmp, DAILY_SETTINGS_FILE)

def get_daily_settings():
    with daily_settings_lock:
        return json.loads(json.dumps(daily_settings))

def normalize_daily_word(text):
    return re.sub(r"[^A-Z ]", "", str(text or "").upper()).strip()

def daily_ocr_data(ref_screen):
    """Fast OCR for safe-action labels.

    Tesseract is by far the slowest part of Daily Assistant.  Running the
    whole 1536x709 frame cost ~1-2 seconds on typical PCs.  V7.1.2 OCRs a
    half-size frame and maps every word box back to reference coordinates.
    """
    if not HAS_TESSERACT:
        return [], ""
    try:
        src_h, src_w = ref_screen.shape[:2]
        scale = float(DAILY_OCR_SCALE)
        if scale < 0.99:
            small_w = max(320, int(round(src_w * scale)))
            small_h = max(180, int(round(src_h * scale)))
            ocr_img = cv2.resize(ref_screen, (small_w, small_h), interpolation=cv2.INTER_AREA)
        else:
            ocr_img = ref_screen
        oh, ow = ocr_img.shape[:2]
        sx = float(src_w) / float(max(1, ow))
        sy = float(src_h) / float(max(1, oh))
        data = pytesseract.image_to_data(
            ocr_img, config="--psm 11", output_type=pytesseract.Output.DICT
        )
    except Exception:
        return [], ""
    words = []
    full = []
    n = len(data.get("text", []))
    for i in range(n):
        raw = str(data.get("text", [""])[i] or "").strip()
        if not raw:
            continue
        try: conf = float(data.get("conf", [-1])[i])
        except Exception: conf = -1.0
        x = int(round(int(data.get("left", [0])[i]) * sx))
        y = int(round(int(data.get("top", [0])[i]) * sy))
        w = int(round(int(data.get("width", [0])[i]) * sx))
        h = int(round(int(data.get("height", [0])[i]) * sy))
        norm = normalize_daily_word(raw)
        if norm:
            full.append(norm)
        words.append({
            "raw": raw, "norm": norm, "conf": conf, "x": x, "y": y,
            "w": w, "h": h,
            "block": int(data.get("block_num", [0])[i]),
            "par": int(data.get("par_num", [0])[i]),
            "line": int(data.get("line_num", [0])[i]),
        })
    return words, " ".join(full)

def _daily_button_candidate(word):
    # Recorded actionable labels are compact button text. This deliberately
    # rejects large event titles such as "FREE MONTHLY PASS".
    if word.get("conf", -1) < 52:
        return False
    if word.get("y", 0) < 55:
        return False
    h = int(word.get("h", 0)); w = int(word.get("w", 0))
    if not (7 <= h <= 38 and 12 <= w <= 230):
        return False
    return True

def find_daily_safe_actions(ref_screen, allowed):
    words, full_text = daily_ocr_data(ref_screen)
    allowed = [normalize_daily_word(x) for x in allowed]
    actions = []

    # Reward overlays are not spending actions. They are dismissed separately.
    reward_overlay = (
        "REWARDS OBTAINED" in full_text
        or "REWARD OBTAINED" in full_text
        or "TITLE OBTAINED" in full_text
        or "TAP TO CONTINUE" in full_text
    )

    # Group by OCR line so CLAIM ALL can be reconstructed from two tokens and
    # FREE can be rejected when it appears inside a long product title.
    lines = {}
    for word in words:
        key=(word["block"],word["par"],word["line"])
        lines.setdefault(key,[]).append(word)
    for line_words in lines.values():
        line_words.sort(key=lambda z:z["x"])
        norms=[x["norm"] for x in line_words if x["norm"]]
        line_text=" ".join(norms)
        if "CLAIM ALL" in allowed:
            for i,w in enumerate(line_words[:-1]):
                n=line_words[i+1]
                if w["norm"]=="CLAIM" and n["norm"]=="ALL" and _daily_button_candidate(w) and _daily_button_candidate(n):
                    if abs((w["y"]+w["h"]/2)-(n["y"]+n["h"]/2)) < 18 and n["x"]-(w["x"]+w["w"]) < 45:
                        x1=min(w["x"],n["x"]); y1=min(w["y"],n["y"]); x2=max(w["x"]+w["w"],n["x"]+n["w"]); y2=max(w["y"]+w["h"],n["y"]+n["h"])
                        actions.append({"label":"CLAIM ALL","x":(x1+x2)//2,"y":(y1+y2)//2,"conf":min(w["conf"],n["conf"])})
        for w in line_words:
            if not _daily_button_candidate(w):
                continue
            if w["norm"]=="CLAIM" and "CLAIM" in allowed:
                # CLAIM in CLAIM ALL is handled above; avoid duplicate click.
                if "CLAIM ALL" in line_text:
                    continue
                actions.append({"label":"CLAIM","x":w["x"]+w["w"]//2,"y":w["y"]+w["h"]//2,"conf":w["conf"]})
            elif w["norm"]=="FREE" and "FREE" in allowed:
                # A button normally contains FREE alone; reject marketing titles.
                meaningful=[z for z in norms if z]
                if len(meaningful) <= 2:
                    actions.append({"label":"FREE","x":w["x"]+w["w"]//2,"y":w["y"]+w["h"]//2,"conf":w["conf"]})

    # Prefer Claim All, then Claim, then Free; then higher OCR confidence.
    priority={"CLAIM ALL":0,"CLAIM":1,"FREE":2}
    actions.sort(key=lambda a:(priority.get(a["label"],9), -a.get("conf",0), a["y"], a["x"]))
    # De-duplicate nearby OCR fragments.
    dedup=[]
    for a in actions:
        if any(abs(a["x"]-b["x"])<30 and abs(a["y"]-b["y"])<20 for b in dedup):
            continue
        dedup.append(a)
    return dedup, reward_overlay, full_text


# V4.4: ADB screenshot capture itself is the expensive operation.
# Do not add another ~450ms delay after every capture.
POLL_FAST_SECONDS = 0.008
POLL_BATTLE_ON_SECONDS = 0.008
POLL_ERROR_SECONDS = 1.0

RESULT_CLICK_COOLDOWN = 0.70
START_CLICK_COOLDOWN = 0.70
AUTO_LOCKOUT_SECONDS = 2.0
AUTO_STATE_MARGIN = 0.040

THRESHOLDS = {
    "try_again": 0.78,
    "start_matching": 0.80,
    "victory": 0.73,
    "auto_off": 0.72,
    "auto_on": 0.72,
    "pause": 0.72,
}

SEARCH_ROIS = {
    "auto":           (220,   0, 370, 105),
    "try_again":      (760, 475, 1120, 660),
    "start_matching": (980, 500, 1536, 709),
    "victory":        (0,    20,  520, 260),
    "pause":          (25,    0,  175, 110),
}

ARENA_STATUS_ROI = (1040, 55, 1518, 280)
RESULT_RANK_ROI   = (250, 215, 680, 475)
RESULT_POINTS_ROI = (745, 250, 1365, 405)

MASTER_V_POINTS = 2500

RANK_NAMES = [
    "Bronze V", "Bronze IV", "Bronze III", "Bronze II", "Bronze I",
    "Silver V", "Silver IV", "Silver III", "Silver II", "Silver I",
    "Gold V", "Gold IV", "Gold III", "Gold II", "Gold I",
    "Platinum V", "Platinum IV", "Platinum III", "Platinum II", "Platinum I",
    "Diamond V", "Diamond IV", "Diamond III", "Diamond II", "Diamond I",
    "Master V", "Master IV", "Master III", "Master II", "Master I",
    "Legendary"
]

DEFAULT_UPDATE_SETTINGS = {
    "github_repo": "Ultimate99/Break-The-Chains-Helper",
    "auto_check": True,
}

def load_update_settings():
    data = dict(DEFAULT_UPDATE_SETTINGS)
    try:
        if UPDATE_SETTINGS_FILE.exists():
            saved = json.loads(UPDATE_SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                data.update(saved)
    except Exception:
        pass
    # V5.4 has an official update source. Older profiles may have saved an
    # empty repo before it existed, so repair that automatically.
    if not data.get("github_repo"):
        data["github_repo"] = "Ultimate99/Break-The-Chains-Helper"
    return data

update_settings = load_update_settings()
update_settings_lock = threading.Lock()

def save_update_settings():
    with update_settings_lock:
        UPDATE_SETTINGS_FILE.write_text(
            json.dumps(update_settings, indent=2),
            encoding="utf-8"
        )

def normalize_github_repo(value):
    value = (value or "").strip()
    value = value.rstrip("/")

    for prefix in (
        "https://github.com/",
        "http://github.com/",
        "github.com/",
    ):
        if value.lower().startswith(prefix):
            value = value[len(prefix):]

    if value.endswith(".git"):
        value = value[:-4]

    parts = [x for x in value.split("/") if x]
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return ""

def version_tuple(value):
    value = str(value or "").strip().lower().lstrip("v")
    nums = re.findall(r"\d+", value)
    return tuple(int(x) for x in nums[:4]) or (0,)

def _github_text(url, timeout=6):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"TG-BTC-Game-Assistant/{APP_VERSION}",
            "Accept": "application/vnd.github.raw+json",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")

def check_github_latest(repo):
    """Check both GitHub Releases and repository main.

    Releases can lag behind a pushed build.  V7.1.2 therefore treats VERSION
    on main as authoritative and can reconstruct a checksum-verified full source payload from the current source manifest.
    A normal Release asset is still preferred when it is equally new.
    """
    repo = normalize_github_repo(repo)
    if not repo:
        raise RuntimeError("Update source is not configured.")

    release_info = None
    release_error = None
    release_url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(
        release_url,
        headers={
            "User-Agent": f"TG-BTC-Game-Assistant/{APP_VERSION}",
            "Accept": "application/vnd.github+json",
            "Cache-Control": "no-cache",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            release = json.loads(resp.read().decode("utf-8"))
        tag = release.get("tag_name") or release.get("name") or "0"
        assets = release.get("assets") or []
        zip_assets = [a for a in assets if str(a.get("name", "")).lower().endswith(".zip")]
        preferred = [
            a for a in zip_assets
            if "tg_btc_arena_companion" in str(a.get("name", "")).lower()
            or "tg-btc-arena-companion" in str(a.get("name", "")).lower()
            or "tg_btc_game_assistant" in str(a.get("name", "")).lower()
        ]
        chosen = (preferred or zip_assets)
        asset = chosen[0] if chosen else None
        if asset:
            release_info = {
                "version": str(tag).lstrip("vV"),
                "tag": tag,
                "name": release.get("name") or str(tag),
                "notes": release.get("body") or "",
                "published_at": release.get("published_at"),
                "asset_name": asset.get("name"),
                "download_url": asset.get("browser_download_url"),
                "download_kind": "zip",
                "html_url": release.get("html_url"),
                "source": "release",
            }
    except Exception as e:
        release_error = str(e)

    main_info = None
    main_error = None
    try:
        raw_base = f"https://raw.githubusercontent.com/{repo}/main"
        main_version = _github_text(f"{raw_base}/VERSION", timeout=5).strip().lstrip("vV")
        if not main_version:
            raise RuntimeError("main/VERSION is empty")
        try:
            notes = _github_text(f"{raw_base}/RELEASE_NOTES.md", timeout=5).strip()
        except Exception:
            notes = ""
        manifest_url = f"{raw_base}/release_payload/current_source_manifest.json"
        manifest = json.loads(_github_text(manifest_url, timeout=4))
        manifest_version = str(manifest.get("version") or "").strip().lstrip("vV")
        if version_tuple(manifest_version) != version_tuple(main_version):
            raise RuntimeError(f"main manifest is v{manifest_version or '?'}, VERSION is v{main_version}")
        main_info = {
            "version": main_version,
            "tag": f"main/{main_version}",
            "name": f"v{main_version} (GitHub main)",
            "notes": notes,
            "published_at": None,
            "asset_name": "current_source_manifest.json",
            "download_url": manifest_url,
            "download_kind": "source_parts",
            "html_url": f"https://github.com/{repo}/tree/main",
            "source": "main",
        }
    except Exception as e:
        main_error = str(e)

    if main_info and (not release_info or version_tuple(main_info["version"]) > version_tuple(release_info["version"])):
        return main_info
    if release_info:
        return release_info
    if main_info:
        return main_info
    raise RuntimeError(f"GitHub update check failed. Release: {release_error or '?'} | main: {main_error or '?'}")

def download_update(url, version, kind="zip"):
    if not url:
        raise RuntimeError("Update source has no download URL.")

    UPDATE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPDATE_CACHE_DIR / f"TG_BTC_update_{version}.zip"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"TG-BTC-Game-Assistant/{APP_VERSION}",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = resp.read()

    if str(kind or "zip").lower() == "source_parts":
        try:
            manifest = json.loads(payload.decode("utf-8"))
        except Exception as e:
            raise RuntimeError(f"GitHub main source manifest is invalid: {e}")
        manifest_version = str(manifest.get("version") or "").strip().lstrip("vV")
        if version_tuple(manifest_version) != version_tuple(version):
            raise RuntimeError(f"GitHub main manifest is v{manifest_version or '?'}, expected v{version}.")
        parts = list(manifest.get("parts") or [])
        if not parts:
            raise RuntimeError("GitHub main source manifest has no parts.")
        base_url = url.rsplit("/", 1)[0]
        encoded_chunks = []
        for rel in parts:
            rel = str(rel or "").strip().lstrip("/")
            if not rel:
                continue
            encoded_chunks.append(_github_text(f"{base_url}/{rel}", timeout=20).strip())
        encoded = "".join(encoded_chunks)
        try:
            raw = bz2.decompress(base64.b64decode(encoded))
        except Exception as e:
            raise RuntimeError(f"Could not reconstruct GitHub main source: {e}")
        expected_sha = str(manifest.get("sha256") or "").strip().lower()
        got_sha = hashlib.sha256(raw).hexdigest()
        if expected_sha and got_sha != expected_sha:
            raise RuntimeError(f"GitHub main source checksum mismatch: {got_sha}")
        try:
            text = raw.decode("utf-8")
            compile(text, "tg_arena_bot.py", "exec")
        except Exception as e:
            raise RuntimeError(f"GitHub main source failed syntax validation: {e}")
        if f'APP_VERSION = "{version}"' not in text and f"APP_VERSION = '{version}'" not in text:
            raise RuntimeError("GitHub main source version does not match main/VERSION.")
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"TG_BTC_Arena_Companion_v{version}/tg_arena_bot.py", raw)
    else:
        dest.write_bytes(payload)

    if not dest.exists() or dest.stat().st_size < 1000:
        raise RuntimeError("Downloaded update ZIP is invalid.")
    return dest

def arena_close_time(now=None):
    now = now or datetime.now()
    # Local-time schedule based on the screenshots / current setup.
    # Arena windows: 11:00-13:00 and 18:00-20:00.
    today = now.date()
    windows = [
        (datetime.combine(today, datetime.min.time()).replace(hour=11),
         datetime.combine(today, datetime.min.time()).replace(hour=13)),
        (datetime.combine(today, datetime.min.time()).replace(hour=18),
         datetime.combine(today, datetime.min.time()).replace(hour=20)),
    ]

    for start, end in windows:
        if start <= now < end:
            return end

    # Next upcoming window
    for start, end in windows:
        if now < start:
            return start

    tomorrow = today + timedelta(days=1)
    return datetime.combine(tomorrow, datetime.min.time()).replace(hour=11)

def new_session():
    return {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "matches": 0,
        "wins": 0,
        "losses": 0,
        "current_streak_type": None,
        "current_streak": 0,
        "best_win_streak": 0,
        "consecutive_losses": 0,
        "rank": None,
        "points": None,
        "starting_points": None,
        "net_points": 0,
        "known_point_changes": [],
        "last_result": None,
        "expected_next_opponent": "Real Opponent",
        "status": "Idle",
        "auto": "Unknown",
        "last_action": None,
        "updated_at": None,
        "current_opponent_type": None,
        "current_opponent_org": None,
        "current_opponent_source": None,
        "current_opponent_username": None,
        "current_identity_confidence": None,
        "current_detected_heroes": [],
        "current_hero_scores": {},
        "current_threat_score": None,
        "current_threat_label": None,
        "current_decision": None,
        "current_decision_reason": None,
        "current_profile": None,
        "current_opening_snapshot": None,
        "current_battle_strategy": None,

        # Smart Dodge
        "dodges": 0,
        "owl_detections": 0,
        "last_owl_score": None,
        "last_dodge_reason": None,
        "last_owl_sample": None,
        "played_losses": 0,
        "dodge_losses": 0,
        "played_loss_durations": [],
        "dodge_durations": [],
    }

def load_persistent_session():
    base = new_session()
    try:
        if SESSION_JSON.exists():
            saved = json.loads(SESSION_JSON.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                base.update(saved)
                # Runtime state must always restart safely.
                base["status"] = "Idle"
                base["auto"] = "Unknown"
                base["current_opponent_type"] = None
                base["current_opponent_org"] = None
                base["current_opponent_source"] = None
                base["current_opponent_username"] = None
                base["current_identity_confidence"] = None
                base["current_detected_heroes"] = []
                base["current_hero_scores"] = {}
                base["current_threat_score"] = None
                base["current_threat_label"] = None
                base["current_decision"] = None
                base["current_decision_reason"] = None
                base["current_profile"] = None
                base["current_opening_snapshot"] = None
                base["current_battle_strategy"] = None
                return base
    except Exception:
        pass
    return base


session = load_persistent_session()
session_lock = threading.Lock()

settings_lock = threading.Lock()
opponent_settings_lock = threading.Lock()

def load_opponent_settings():
    data = dict(DEFAULT_OPPONENT_SETTINGS)
    try:
        if OPPONENT_SETTINGS_FILE.exists():
            saved = json.loads(OPPONENT_SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                data.update(saved)
    except Exception:
        pass
    return data

opponent_settings = load_opponent_settings()

def save_opponent_settings():
    with opponent_settings_lock:
        OPPONENT_SETTINGS_FILE.write_text(
            json.dumps(opponent_settings, indent=2),
            encoding="utf-8"
        )

def get_opponent_settings():
    with opponent_settings_lock:
        return dict(opponent_settings)

def update_opponent_setting(key, value):
    with opponent_settings_lock:
        opponent_settings[key] = value
    save_opponent_settings()

def opponent_org_roi():
    roi = get_opponent_settings().get("org_roi")
    if not isinstance(roi, (list, tuple)) or len(roi) != 4:
        return None
    try:
        x1, y1, x2, y2 = [int(round(float(v))) for v in roi]
    except Exception:
        return None
    x1 = max(0, min(REFERENCE_W - 1, x1))
    y1 = max(0, min(REFERENCE_H - 1, y1))
    x2 = max(x1 + 1, min(REFERENCE_W, x2))
    y2 = max(y1 + 1, min(REFERENCE_H, y2))
    if x2 - x1 < 12 or y2 - y1 < 8:
        return None
    return (x1, y1, x2, y2)

def classify_opponent_by_organization(ref_screen):
    """
    Authoritative V5.7.1 identity rule:
      Organization text present -> REAL
      Organization line blank -> BOT
    """
    roi = opponent_org_roi()
    if roi is None:
        return None, None, "not_calibrated", ""

    region = crop(ref_screen, roi)
    if region is None or region.size == 0:
        return None, None, "bad_roi", ""

    raw = ""
    best_conf = -1.0
    if HAS_TESSERACT:
        try:
            prep = prep_ocr(region)
            data = pytesseract.image_to_data(
                prep,
                config="--psm 7",
                output_type=pytesseract.Output.DICT,
            )
            pieces = []
            for piece, conf in zip(data.get("text", []), data.get("conf", [])):
                piece = str(piece or "").strip()
                if not piece:
                    continue
                try:
                    c = float(conf)
                except Exception:
                    c = -1.0
                best_conf = max(best_conf, c)
                if c >= 45:
                    pieces.append(piece)
            raw = " ".join(pieces)
        except Exception:
            raw = ""

    clean = " ".join(str(raw or "").replace("\n", " ").split())
    alnum = re.sub(r"[^0-9A-Za-zÀ-ÿ]", "", clean)
    if len(alnum) >= 2 and best_conf >= 45:
        return "REAL", clean[:80], "organization_ocr", f"{clean} conf={best_conf:.0f}"

    # Visual fallback. Because the calibrated rectangle contains only the
    # organization line, several text-sized components means the line exists.
    try:
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        bw = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 31, 9
        )
        contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        textish = 0
        h_total, w_total = bw.shape[:2]
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = cv2.contourArea(cnt)
            if (
                5 <= h <= max(12, int(h_total * 0.75))
                and 2 <= w <= max(12, int(w_total * 0.55))
                and area >= 10
                and (w * h) <= (w_total * h_total * 0.25)
            ):
                textish += 1
        if textish >= 3:
            return "REAL", clean or "(organization visible)", "organization_visual", f"components={textish}"
        if textish <= 1:
            return "BOT", None, "organization_blank", f"components={textish}"
        return None, None, "organization_uncertain", f"components={textish}"
    except Exception:
        if HAS_TESSERACT:
            return "BOT", None, "organization_blank", clean
        return None, None, "detector_unavailable", clean

def migrate_previous_calibration():
    """
    One-time migration into %APPDATA%\\TG-BTC-Arena-Companion.

    Searches the current install folder and nearby older TG:BTC Companion
    folders. Once data is in PROFILE_DIR, future versions never need to
    migrate it again.
    """
    imported_from = None

    try:
        # If profile already contains meaningful Smart Dodge data, leave it.
        profile_has_settings = DODGE_SETTINGS_FILE.exists()
        profile_has_samples = any(DODGE_TEMPLATE_DIR.glob("owl_*.png"))

        candidates = []

        # Current installation may itself be an upgraded/copied old build.
        candidates.append(ROOT)

        try:
            for d in ROOT.parent.iterdir():
                if not d.is_dir() or d.resolve() == ROOT.resolve():
                    continue
                name = d.name.lower()
                if "tg" in name and ("arena" in name or "btc" in name):
                    candidates.append(d)
        except Exception:
            pass

        best = None
        for d in candidates:
            settings = d / "dodge_settings.json"
            sample_locations = [
                d / "templates" / "dodge",
                d / "owl_samples",
            ]
            samples_dir = next((x for x in sample_locations if x.exists()), None)

            mtimes = []
            if settings.exists():
                mtimes.append(settings.stat().st_mtime)
            if samples_dir:
                try:
                    mtimes.extend(p.stat().st_mtime for p in samples_dir.glob("owl_*.png"))
                except Exception:
                    pass

            if mtimes:
                candidate = (max(mtimes), d, settings, samples_dir)
                if best is None or candidate[0] > best[0]:
                    best = candidate

        if best:
            _, old_root, settings, samples_dir = best
            imported = False

            if not profile_has_settings and settings.exists():
                shutil.copy2(settings, DODGE_SETTINGS_FILE)
                imported = True

            if not profile_has_samples and samples_dir:
                for p in samples_dir.glob("owl_*.png"):
                    shutil.copy2(p, DODGE_TEMPLATE_DIR / p.name)
                    imported = True

            if imported:
                imported_from = str(old_root)

        # Also migrate session/log data from current/nearby folders if the
        # profile has never had it.
        for filename, destination in [
            ("session.json", SESSION_JSON),
            ("arena_log.txt", SESSION_LOG),
            ("match_history.csv", CSV_LOG),
        ]:
            if destination.exists():
                continue

            found = []
            for d in candidates:
                p = d / filename
                if p.exists():
                    found.append(p)

            if found:
                newest = max(found, key=lambda p: p.stat().st_mtime)
                shutil.copy2(newest, destination)

    except Exception:
        pass

    return imported_from


MIGRATED_FROM = migrate_previous_calibration()


def load_dodge_settings():
    data = dict(DEFAULT_DODGE_SETTINGS)
    try:
        if DODGE_SETTINGS_FILE.exists():
            saved = json.loads(DODGE_SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                data.update(saved)
    except Exception:
        pass
    return data

dodge_settings = load_dodge_settings()

def save_dodge_settings():
    with settings_lock:
        DODGE_SETTINGS_FILE.write_text(
            json.dumps(dodge_settings, indent=2),
            encoding="utf-8"
        )

def get_dodge_settings():
    with settings_lock:
        return dict(dodge_settings)

def update_dodge_setting(key, value):
    with settings_lock:
        dodge_settings[key] = value
    save_dodge_settings()

def rank_is_master_plus(rank):
    if not rank:
        return False
    return rank.startswith("Master ") or rank == "Legendary"

def smart_dodge_allowed():
    cfg = get_dodge_settings()
    if not smart_dodge_base_allowed():
        return False
    if current_profile_name() == "No Dodge":
        return False
    if not cfg.get("dodge_owl"):
        return False
    return True

def load_owl_samples():
    DODGE_TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    samples = []
    for path in sorted(DODGE_TEMPLATE_DIR.glob("owl_*.png")):
        img = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if img is not None and img.shape[0] >= 12 and img.shape[1] >= 12:
            samples.append((path.name, img))
    return samples

def detect_owl(ref_screen, samples):
    """
    Return (best_score, sample_name) using only the enemy side.
    Samples are actual in-battle Owl crops captured by the user.
    """
    if not samples:
        return 0.0, None

    x1, y1, x2, y2 = DODGE_ENEMY_ROI
    enemy = ref_screen[y1:y2, x1:x2]
    enemy_gray = cv2.cvtColor(enemy, cv2.COLOR_BGR2GRAY)

    best_score = 0.0
    best_name = None

    for name, sample in samples:
        sh, sw = sample.shape[:2]
        eh, ew = enemy.shape[:2]
        if sw > ew or sh > eh:
            continue

        sample_gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(
            enemy_gray,
            sample_gray,
            cv2.TM_CCOEFF_NORMED
        )
        _, score, _, _ = cv2.minMaxLoc(result)

        if float(score) > best_score:
            best_score = float(score)
            best_name = name

    return best_score, best_name



# ==============================================================
# V5.8 DIAGNOSTICS + SELF-HEALING
# ==============================================================
HEALTH_STALE_FRAME_MS = 2500
HEALTH_ADB_PROBE_SECONDS = 10.0
HEALTH_WATCHDOG_SECONDS = 1.0
HEALTH_STUCK_STATE_SECONDS = 90.0
HEALTH_RECOVERY_COOLDOWN_SECONDS = 12.0


def _hidden_process_kwargs():
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        "startupinfo": startupinfo,
    }


def probe_adb_device(device, timeout=2.5):
    """Cheap health probe that cannot hang the watchdog forever."""
    if not device:
        return False, None, "no device selected"
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            ["adb", "-s", str(device), "get-state"],
            capture_output=True,
            timeout=float(timeout),
            check=False,
            **_hidden_process_kwargs(),
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        text = (proc.stdout or b"").decode(errors="ignore").strip().lower()
        if proc.returncode == 0 and "device" in text:
            return True, latency_ms, "device"
        err = (proc.stderr or b"").decode(errors="ignore").strip()
        return False, latency_ms, err or text or f"exit {proc.returncode}"
    except subprocess.TimeoutExpired:
        return False, int((time.perf_counter() - started) * 1000), "probe timeout"
    except Exception as exc:
        return False, None, str(exc)


def append_health_event(component, status, detail="", action=""):
    try:
        payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "component": str(component),
            "status": str(status),
            "detail": str(detail or ""),
            "action": str(action or ""),
        }
        with HEALTH_EVENTS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\\n")
    except Exception:
        pass


def load_recent_health_events(limit=80):
    try:
        if not HEALTH_EVENTS_FILE.exists():
            return []
        lines = HEALTH_EVENTS_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
        out = []
        for line in lines[-max(1, int(limit)):]:
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    out.append(row)
            except Exception:
                pass
        return out
    except Exception:
        return []

def adb(args):
    # When the GUI is launched via pythonw on Windows, adb.exe is still a
    # console application. Without CREATE_NO_WINDOW, Windows flashes a black
    # console window for every screenshot/tap/device check.
    creationflags = 0
    startupinfo = None

    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0

    try:
        return subprocess.run(
            ["adb"] + args,
            capture_output=True,
            check=True,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )
    except FileNotFoundError:
        raise RuntimeError("adb.exe is not in PATH.")
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode(errors="ignore") if e.stderr else str(e)
        raise RuntimeError(f"ADB failed: {err}")

def get_device():
    out = adb(["devices"]).stdout.decode(errors="ignore")
    devices = [
        line.split("\t")[0]
        for line in out.splitlines()[1:]
        if "\tdevice" in line
    ]
    return devices[0] if devices else None

def capture_screen():
    raw = adb(["exec-out", "screencap", "-p"]).stdout
    arr = np.frombuffer(raw, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("Could not decode phone screenshot.")
    return image

def resize_reference(screen):
    return cv2.resize(screen, (REFERENCE_W, REFERENCE_H), interpolation=cv2.INTER_AREA)

def load_templates():
    result = {}
    for name in ("auto_off", "auto_on", "try_again", "start_matching", "victory", "pause"):
        path = TEMPLATE_DIR / f"{name}.png"
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(f"Missing template: {path}")
        result[name] = image
    return result

def template_score(roi, template):
    if template.shape[1] > roi.shape[1] or template.shape[0] > roi.shape[0]:
        return -1.0, (0, 0)
    roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    tpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    result = cv2.matchTemplate(roi_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(result)
    return float(score), loc

def find_template(ref_screen, template, roi_name, threshold_name=None):
    x1, y1, x2, y2 = SEARCH_ROIS[roi_name]
    roi = ref_screen[y1:y2, x1:x2]
    score, loc = template_score(roi, template)
    threshold_key = threshold_name or roi_name
    if score < THRESHOLDS[threshold_key]:
        return None
    h, w = template.shape[:2]
    cx = x1 + loc[0] + w // 2
    cy = y1 + loc[1] + h // 2
    return score, cx, cy

def detect_auto_state(ref_screen, templates):
    x1, y1, x2, y2 = SEARCH_ROIS["auto"]
    roi = ref_screen[y1:y2, x1:x2]

    off_score, off_loc = template_score(roi, templates["auto_off"])
    on_score, on_loc = template_score(roi, templates["auto_on"])

    if off_score >= THRESHOLDS["auto_off"] and off_score >= on_score + AUTO_STATE_MARGIN:
        h, w = templates["auto_off"].shape[:2]
        return "OFF", off_score, on_score, x1 + off_loc[0] + w // 2, y1 + off_loc[1] + h // 2

    if on_score >= THRESHOLDS["auto_on"] and on_score >= off_score + AUTO_STATE_MARGIN:
        h, w = templates["auto_on"].shape[:2]
        return "ON", off_score, on_score, x1 + on_loc[0] + w // 2, y1 + on_loc[1] + h // 2

    return "AMBIGUOUS", off_score, on_score, None, None

def tap_reference(ref_x, ref_y, actual_w, actual_h):
    x = round(ref_x * actual_w / REFERENCE_W)
    y = round(ref_y * actual_h / REFERENCE_H)
    adb(["shell", "input", "tap", str(x), str(y)])

def find_tesseract():
    if not HAS_PYTESSERACT:
        return False
    candidates = [
        shutil.which("tesseract"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            return True
    return False

HAS_TESSERACT = find_tesseract()

def tesseract_path_text():
    if not HAS_PYTESSERACT:
        return "pytesseract Python package missing"
    if HAS_TESSERACT:
        try:
            return str(pytesseract.pytesseract.tesseract_cmd)
        except Exception:
            return "Tesseract ready"
    return "tesseract.exe missing"

def refresh_tesseract():
    global HAS_TESSERACT
    HAS_TESSERACT = find_tesseract()
    return HAS_TESSERACT


def crop(img, box):
    x1, y1, x2, y2 = box
    return img[y1:y2, x1:x2]

def prep_ocr(img, scale=2.4):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    return gray

def ocr(img, psm=6):
    if not HAS_TESSERACT:
        return ""
    try:
        return pytesseract.image_to_string(prep_ocr(img), config=f"--psm {psm}")
    except Exception:
        return ""

def normalize_rank(text):
    text = re.sub(r"[^A-Za-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()

    for rank in RANK_NAMES:
        if rank.lower() in text:
            return rank

    family = None
    for fam in ("bronze", "silver", "gold", "platinum", "diamond", "master", "legendary"):
        if fam in text:
            family = fam.title()
            break

    if family == "Legendary":
        return "Legendary"

    if family:
        tokens = text.upper().replace("1", "I").replace("L", "I").split()
        for token in tokens:
            token = re.sub(r"[^IVX]", "", token)
            candidate = f"{family} {token}"
            if candidate in RANK_NAMES:
                return candidate
    return None

def extract_current_points(text):
    m = re.search(r"\b(\d{3,4})\s*/\s*(\d{3,4})\b", text)
    if m:
        return int(m.group(1))
    nums = [int(n) for n in re.findall(r"\b\d{3,4}\b", text)]
    nums = [n for n in nums if 100 <= n <= 9999]
    return max(nums) if nums else None

def extract_result_delta(text):
    candidates = re.findall(r"[\[\(]?\s*([+-]\s*\d{1,3})\s*[\]\)]?", text)
    for raw in candidates:
        try:
            return int(raw.replace(" ", ""))
        except ValueError:
            pass
    return None

def read_arena_status(ref):
    if not HAS_TESSERACT:
        return None, None
    text = ocr(crop(ref, ARENA_STATUS_ROI), psm=11)
    return normalize_rank(text), extract_current_points(text)

def read_result_status(ref):
    if not HAS_TESSERACT:
        return None, None, None
    rank_text = ocr(crop(ref, RESULT_RANK_ROI), psm=11)
    point_text = ocr(crop(ref, RESULT_POINTS_ROI), psm=11)
    return normalize_rank(rank_text), extract_current_points(point_text), extract_result_delta(point_text)

def set_manual_rank_points(rank, points):
    """
    Reliable fallback when OCR is unavailable.
    Once the current score is seeded manually, result OCR/deltas can continue
    updating it later when OCR becomes available.
    """
    with session_lock:
        changed = update_rank_points(rank, points)
    save_session()
    return changed


def expected_opponent():
    losses = session["consecutive_losses"]
    if losses <= 0:
        return "Real Opponent"
    if losses == 1:
        return "Strong Bot"
    return "Weak Bot"

def update_rank_points(rank=None, points=None):
    changed = False
    if rank and rank != session["rank"]:
        session["rank"] = rank
        changed = True

    if points is not None:
        if session["starting_points"] is None:
            session["starting_points"] = points
        if points != session["points"]:
            session["points"] = points
            session["net_points"] = points - session["starting_points"]
            changed = True
    return changed

def register_result(is_win, rank=None, points=None, delta=None, was_dodge=False, duration=None):
    # Capture the queue state BEFORE this result changes the loss streak.
    # This is the opponent class the just-finished match was predicted to be.
    predicted_opponent = session.get("expected_next_opponent") or expected_opponent()
    direct_type = session.get("current_opponent_type")
    direct_org = session.get("current_opponent_org")
    direct_source = session.get("current_opponent_source")
    opponent_username = session.get("current_opponent_username")
    identity_confidence = session.get("current_identity_confidence")
    detected_heroes = list(session.get("current_detected_heroes") or [])
    hero_scores = dict(session.get("current_hero_scores") or {})
    threat_score_value = session.get("current_threat_score")
    threat_label_value = session.get("current_threat_label")
    decision = session.get("current_decision")
    decision_reason = session.get("current_decision_reason")
    active_profile = session.get("current_profile")
    opening_snapshot = session.get("current_opening_snapshot")
    battle_strategy = session.get("current_battle_strategy")
    rank_before = session.get("rank")
    points_before = session.get("points")
    session_started_at = session.get("started_at") or "unknown"

    session["matches"] += 1

    if is_win:
        session["wins"] += 1
        session["last_result"] = "WIN"
        session["consecutive_losses"] = 0
        if session["current_streak_type"] == "W":
            session["current_streak"] += 1
        else:
            session["current_streak_type"] = "W"
            session["current_streak"] = 1
        session["best_win_streak"] = max(session["best_win_streak"], session["current_streak"])
    else:
        session["losses"] += 1
        session["last_result"] = "LOSS"
        session["consecutive_losses"] += 1

        if was_dodge:
            session["dodge_losses"] = session.get("dodge_losses", 0) + 1
            if duration is not None:
                session["dodge_durations"].append(float(duration))
                session["dodge_durations"] = session["dodge_durations"][-100:]
        else:
            session["played_losses"] = session.get("played_losses", 0) + 1
            if duration is not None:
                session["played_loss_durations"].append(float(duration))
                session["played_loss_durations"] = session["played_loss_durations"][-100:]
        if session["current_streak_type"] == "L":
            session["current_streak"] += 1
        else:
            session["current_streak_type"] = "L"
            session["current_streak"] = 1

    old_points = session["points"]
    update_rank_points(rank, points)

    if delta is None and points is not None and old_points is not None:
        delta = points - old_points

    if delta is not None:
        session["known_point_changes"].append(delta)
        session["known_point_changes"] = session["known_point_changes"][-500:]

    session["expected_next_opponent"] = expected_opponent()
    match_no = session["matches"]

    # Rich V5.7 record. Result registration remains immediate; OCR can enrich
    # rank/points/delta later by matching session_started_at + match number.
    # Write this BEFORE the legacy CSV row so first-run migration cannot
    # accidentally import the same match twice.
    append_intel_match({
        "id": f"{session_started_at}#{match_no}",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "session_started_at": session_started_at,
        "match": match_no,
        "result": session["last_result"],
        "predicted_opponent": predicted_opponent,
        "opponent_type": direct_type,
        "organization": direct_org,
        "classification_source": direct_source,
        "opponent_username": opponent_username,
        "identity_confidence": identity_confidence,
        "detected_heroes": detected_heroes,
        "hero_scores": hero_scores,
        "threat_score": threat_score_value,
        "threat_label": threat_label_value,
        "decision": decision,
        "decision_reason": decision_reason,
        "active_profile": active_profile,
        "opening_snapshot": opening_snapshot,
        "battle_strategy": battle_strategy,
        "dodge_reason": session.get("last_dodge_reason") if was_dodge else None,
        "next_opponent": session["expected_next_opponent"],
        "rank_before": rank_before,
        "rank_after": session.get("rank"),
        "points_before": points_before,
        "points_after": session.get("points"),
        "delta": delta,
        "was_dodge": bool(was_dodge),
        "duration_s": round(float(duration), 2) if duration is not None else None,
        "owl_score": (
            round(float(session.get("last_owl_score")), 3)
            if was_dodge and session.get("last_owl_score") is not None else None
        ),
        "owl_sample": session.get("last_owl_sample") if was_dodge else None,
        "source": "v5.7",
    })

    append_match_csv(
        match_no,
        session["last_result"],
        session["rank"],
        session["points"],
        delta,
        session["expected_next_opponent"]
    )

    identity_log = ""
    if direct_type == "REAL":
        identity_log = f" identity=REAL org={direct_org or '?'}"
    elif direct_type == "BOT":
        identity_log = " identity=BOT org=NONE"

    log_line(
        f"RESULT={session['last_result']} queue={predicted_opponent}"
        f"{identity_log} "
        f"rank={session['rank'] or '?'} "
        f"points={session['points'] if session['points'] is not None else '?'} "
        f"delta={delta if delta is not None else '?'} "
        f"next={session['expected_next_opponent']}"
    )
    session["current_opponent_type"] = None
    session["current_opponent_org"] = None
    session["current_opponent_source"] = None
    session["current_opponent_username"] = None
    session["current_identity_confidence"] = None
    session["current_detected_heroes"] = []
    session["current_hero_scores"] = {}
    session["current_threat_score"] = None
    session["current_threat_label"] = None
    session["current_decision"] = None
    session["current_decision_reason"] = None
    session["current_profile"] = None
    session["current_opening_snapshot"] = None
    session["current_battle_strategy"] = None
    return match_no

def win_rate():
    return (100.0 * session["wins"] / session["matches"]) if session["matches"] else 0.0

def elapsed_seconds():
    try:
        started = datetime.fromisoformat(session["started_at"])
        return max(0.0, (datetime.now() - started).total_seconds())
    except Exception:
        return 0.0

def matches_per_hour():
    elapsed = elapsed_seconds()
    if elapsed <= 0:
        return 0.0
    return session["matches"] * 3600.0 / elapsed

def avg_points_per_match():
    vals = session["known_point_changes"]
    if vals:
        return sum(vals) / len(vals)
    if session["matches"] and session["starting_points"] is not None and session["points"] is not None:
        return (session["points"] - session["starting_points"]) / session["matches"]
    return None

def points_per_hour():
    elapsed = elapsed_seconds()
    if elapsed <= 0:
        return None
    return session["net_points"] * 3600.0 / elapsed

def master_progress():
    points = session["points"]
    if points is None:
        return None, None
    remaining = max(0, MASTER_V_POINTS - points)
    avg = avg_points_per_match()
    estimate = None
    if remaining == 0:
        estimate = 0
    elif avg is not None and avg > 0:
        estimate = int(np.ceil(remaining / avg))
    return remaining, estimate

def projected_points_by_close():
    if session["points"] is None:
        return None

    now = datetime.now()
    close = arena_close_time(now)

    # If close is actually the next opening, don't project.
    if close.hour in (11, 18) and close > now:
        return None

    pph = points_per_hour()
    if pph is None:
        return None

    hours_left = max(0.0, (close - now).total_seconds() / 3600.0)
    return round(session["points"] + pph * hours_left)

def current_streak_text():
    kind = session["current_streak_type"]
    count = session["current_streak"]
    return f"{kind}{count}" if kind and count else "-"

def format_duration(seconds):
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def arena_countdown_text():
    now = datetime.now()
    target = arena_close_time(now)
    delta = target - now
    if target.hour in (13, 20) and delta.total_seconds() >= 0:
        return f"Closes in {format_duration(delta.total_seconds())}"
    return f"Next opens in {format_duration(delta.total_seconds())}"

def estimated_dodge_time_saved():
    played = session.get("played_loss_durations", [])
    dodged = session.get("dodge_durations", [])
    if not played or not dodged:
        return None
    normal_avg = sum(played) / len(played)
    dodge_avg = sum(dodged) / len(dodged)
    return max(0.0, (normal_avg - dodge_avg) * len(dodged))


def save_session():
    session["updated_at"] = datetime.now().isoformat(timespec="seconds")
    SESSION_JSON.write_text(json.dumps(session, indent=2), encoding="utf-8")

    remaining, est = master_progress()
    avg = avg_points_per_match()
    pph = points_per_hour()

    lines = [
        f"Status: {session['status']}",
        f"AUTO: {session['auto']}",
        f"Rank: {session['rank'] or '?'}",
        f"Points: {session['points'] if session['points'] is not None else '?'}",
        f"Matches: {session['matches']}",
        f"Wins: {session['wins']}",
        f"Losses: {session['losses']}",
        f"Win rate: {win_rate():.1f}%",
        f"Streak: {current_streak_text()}",
        f"Next opponent: {session['expected_next_opponent']}",
        f"Net points: {session['net_points']:+d}",
        f"Matches/hour: {matches_per_hour():.1f}",
        f"Points/hour: {pph:+.1f}" if pph is not None else "Points/hour: ?",
        f"Avg points/match: {avg:+.2f}" if avg is not None else "Avg points/match: ?",
        f"Master V remaining: {remaining}" if remaining is not None else "Master V remaining: ?",
        f"Estimated matches to Master V: {est}" if est is not None else "Estimated matches to Master V: ?",
        f"Arena: {arena_countdown_text()}",
        f"Smart Dodge: {'ON' if get_dodge_settings().get('enabled') else 'OFF'}",
        f"Dodges: {session.get('dodges', 0)}",
        f"Last Owl score: {session.get('last_owl_score') if session.get('last_owl_score') is not None else '?'}",
        f"Last Owl sample: {session.get('last_owl_sample') or '?'}",
        f"Played losses: {session.get('played_losses', 0)}",
        f"Dodge losses: {session.get('dodge_losses', 0)}",
        f"Estimated dodge time saved: {estimated_dodge_time_saved() if estimated_dodge_time_saved() is not None else '?'}",
        f"Updated: {session['updated_at']}",
    ]
    STATUS_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

def log_line(text):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with SESSION_LOG.open("a", encoding="utf-8") as f:
        f.write(f"{stamp} | {text}\n")

def append_match_csv(match_no, result, rank, points, delta, next_opp):
    new_file = not CSV_LOG.exists()
    with CSV_LOG.open("a", encoding="utf-8", newline="") as f:
        if new_file:
            f.write("timestamp,match,result,rank,points,delta,next_opponent\n")
        def q(v):
            s = "" if v is None else str(v)
            return '"' + s.replace('"', '""') + '"'
        f.write(",".join([
            q(datetime.now().isoformat(timespec="seconds")),
            q(match_no), q(result), q(rank), q(points), q(delta), q(next_opp)
        ]) + "\n")


# ==============================================================
# V5.7 PERSISTENT MATCH INTELLIGENCE
# ==============================================================
# The original CSV remains untouched for backward compatibility.  V5.7 adds
# a richer JSON history beside it so results can be enriched after the
# background OCR pass finishes without delaying Try Again.
_intel_history_lock = threading.Lock()


def _safe_int(value):
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except Exception:
        return None


def _safe_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _legacy_intel_records():
    """Best-effort import of pre-v5.7 match_history.csv rows."""
    if not CSV_LOG.exists():
        return []

    rows = []
    previous_next = "Real Opponent"
    try:
        with CSV_LOG.open("r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            for item in reader:
                if not isinstance(item, dict):
                    continue
                result = str(item.get("result") or "").upper()
                if result not in ("WIN", "LOSS"):
                    continue
                match_no = _safe_int(item.get("match")) or (len(rows) + 1)
                points_after = _safe_int(item.get("points"))
                delta = _safe_int(item.get("delta"))
                rank_after = item.get("rank") or None
                next_opp = item.get("next_opponent") or "Real Opponent"
                points_before = None
                if points_after is not None and delta is not None:
                    points_before = points_after - delta
                rows.append({
                    "id": f"legacy#{match_no}#{item.get('timestamp') or len(rows)}",
                    "timestamp": item.get("timestamp") or "",
                    "session_started_at": "legacy",
                    "match": match_no,
                    "result": result,
                    "predicted_opponent": previous_next,
                    "next_opponent": next_opp,
                    "rank_before": None,
                    "rank_after": rank_after,
                    "points_before": points_before,
                    "points_after": points_after,
                    "delta": delta,
                    "was_dodge": False,
                    "duration_s": None,
                    "owl_score": None,
                    "owl_sample": None,
                    "source": "legacy_csv",
                })
                previous_next = next_opp
    except Exception:
        return []
    return rows


def load_intel_history():
    with _intel_history_lock:
        try:
            if INTEL_HISTORY_FILE.exists():
                data = json.loads(INTEL_HISTORY_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return [x for x in data if isinstance(x, dict)]
        except Exception:
            pass
    return _legacy_intel_records()


def save_intel_history(records):
    records = [x for x in records if isinstance(x, dict)][-5000:]
    tmp = INTEL_HISTORY_FILE.with_suffix(".tmp")
    with _intel_history_lock:
        tmp.write_text(json.dumps(records, indent=2), encoding="utf-8")
        os.replace(tmp, INTEL_HISTORY_FILE)


def append_intel_match(record):
    records = load_intel_history()
    # When the first V5.7 result arrives, persist any legacy rows too so the
    # History page remains continuous across upgrades.
    records.append(record)
    save_intel_history(records)


def enrich_intel_match(session_started_at, match_no, *, rank=None, points=None, delta=None):
    records = load_intel_history()
    changed = False
    target_id = f"{session_started_at}#{match_no}"
    for record in reversed(records):
        if record.get("id") == target_id:
            if rank:
                record["rank_after"] = rank
                changed = True
            if points is not None:
                record["points_after"] = int(points)
                changed = True
                if record.get("points_before") is None and delta is not None:
                    record["points_before"] = int(points) - int(delta)
            if delta is not None:
                record["delta"] = int(delta)
                changed = True
            record["ocr_enriched_at"] = datetime.now().isoformat(timespec="seconds")
            changed = True
            break
    if changed:
        save_intel_history(records)
    return changed


def opponent_bucket_stats(records=None):
    records = load_intel_history() if records is None else records
    names = ("Real Opponent", "Strong Bot", "Weak Bot")
    stats = {
        name: {"matches": 0, "played": 0, "wins": 0, "losses": 0, "dodges": 0}
        for name in names
    }
    for row in records:
        name = row.get("predicted_opponent")
        if name not in stats:
            continue
        bucket = stats[name]
        bucket["matches"] += 1
        if bool(row.get("was_dodge")):
            bucket["dodges"] += 1
            continue
        bucket["played"] += 1
        if str(row.get("result") or "").upper() == "WIN":
            bucket["wins"] += 1
        else:
            bucket["losses"] += 1
    for bucket in stats.values():
        bucket["win_rate"] = (
            100.0 * bucket["wins"] / bucket["played"] if bucket["played"] else None
        )
    return stats


def opponent_intel_text(records=None):
    records = load_intel_history() if records is None else records

    direct_type = session.get("current_opponent_type")
    if direct_type == "REAL":
        org = session.get("current_opponent_org") or "organization detected"
        return f"REAL PERSON  •  {org}"
    if direct_type == "BOT":
        return "BOT  •  no organization under username"

    predicted = session.get("expected_next_opponent") or expected_opponent()
    bucket = opponent_bucket_stats(records).get(predicted, {})
    played = int(bucket.get("played") or 0)
    wr = bucket.get("win_rate")
    suffix = "  •  ORG detector not calibrated" if opponent_org_roi() is None else ""
    if played >= 3 and wr is not None:
        return f"{predicted}  •  {wr:.0f}% historical WR  •  {played} played{suffix}"
    if played:
        return f"{predicted}  •  learning ({played} played){suffix}"
    return f"{predicted}  •  learning matchup{suffix}"

def opponent_identity_summary(records=None):
    records = load_intel_history() if records is None else records
    real = 0
    bots = 0
    unknown = 0
    for row in records:
        kind = str(row.get("opponent_type") or "").upper()
        if kind == "REAL":
            real += 1
        elif kind == "BOT":
            bots += 1
        else:
            unknown += 1
    calibrated = opponent_org_roi() is not None
    if real or bots:
        return f"ORG detector  •  {real} real  •  {bots} bot" + (f"  •  {unknown} legacy" if unknown else "")
    return "ORG detector calibrated — learning" if calibrated else "ORG detector not calibrated"

def last_ten_summary(records=None):
    records = load_intel_history() if records is None else records
    recent = records[-10:]
    if not recent:
        return "No history yet"
    wins = sum(1 for r in recent if str(r.get("result") or "").upper() == "WIN")
    losses = len(recent) - wins
    dodges = sum(1 for r in recent if bool(r.get("was_dodge")))
    suffix = f"  •  {dodges} dodge" + ("s" if dodges != 1 else "") if dodges else ""
    return f"Last {len(recent)}: {wins}W / {losses}L{suffix}"


def persistent_history_summary(records=None):
    records = load_intel_history() if records is None else records
    deltas = [_safe_int(r.get("delta")) for r in records]
    deltas = [x for x in deltas if x is not None]
    net = sum(deltas) if deltas else 0
    dodges = sum(1 for r in records if bool(r.get("was_dodge")))
    scores = [_safe_float(r.get("owl_score")) for r in records if bool(r.get("was_dodge"))]
    scores = [x for x in scores if x is not None]
    durations = [_safe_float(r.get("duration_s")) for r in records if bool(r.get("was_dodge"))]
    durations = [x for x in durations if x is not None]
    return {
        "matches": len(records),
        "net": net,
        "dodges": dodges,
        "owl_avg": (sum(scores) / len(scores)) if scores else None,
        "dodge_avg": (sum(durations) / len(durations)) if durations else None,
    }


def rank_journey(records=None):
    records = load_intel_history() if records is None else records
    journey = []
    for row in records:
        rank = row.get("rank_after")
        if rank and (not journey or journey[-1] != rank):
            journey.append(rank)
    return journey


def history_point_series(records=None):
    records = load_intel_history() if records is None else records
    out = []
    for row in records:
        points = _safe_int(row.get("points_after"))
        if points is not None:
            out.append((row.get("timestamp") or "", points))
    return out


def debug_ocr_current_screen():
    if not refresh_tesseract():
        return {
            "ok": False,
            "message": (
                "Tesseract OCR engine was not found.\n\n"
                "pytesseract is only the Python wrapper. Rank/Points also need "
                "tesseract.exe installed on Windows.\n\n"
                "Common path:\nC:\\Program Files\\Tesseract-OCR\\tesseract.exe"
            )
        }

    screen = capture_screen()
    ref = resize_reference(screen)

    arena_raw = ocr(crop(ref, ARENA_STATUS_ROI), psm=11)
    result_rank_raw = ocr(crop(ref, RESULT_RANK_ROI), psm=11)
    result_points_raw = ocr(crop(ref, RESULT_POINTS_ROI), psm=11)

    return {
        "ok": True,
        "arena_raw": arena_raw,
        "arena_rank": normalize_rank(arena_raw),
        "arena_points": extract_current_points(arena_raw),
        "result_rank_raw": result_rank_raw,
        "result_points_raw": result_points_raw,
        "result_rank": normalize_rank(result_rank_raw),
        "result_points": extract_current_points(result_points_raw),
        "result_delta": extract_result_delta(result_points_raw),
    }



# ==============================================================
# V6.0 ARENA INTELLIGENCE SUITE
# ==============================================================
# V6.0 combines the planned 5.9 opponent-intelligence work with the first
# battle-strategy engine.  Everything remains calibration-based and safe by
# default: no unknown screen is tapped and battle scripts are disabled until
# the user explicitly enables them and calibrates action points.

DEFAULT_INTELLIGENCE_SETTINGS = {
    "scanner_enabled": True,
    "hero_threshold": 0.72,
    "decision_engine_enabled": True,
    "active_profile": "Safe Climb",
    "save_match_snapshots": True,
    "notifications": {
        "master_reached": True,
        "arena_close": True,
        "critical_health": True,
        "goal_complete": True,
    },
    "goal": {
        "enabled": True,
        "type": "points",
        "target": MASTER_V_POINTS,
    },
    "threat_weights": {
        "Owl of Readiness": 40,
    },
    "custom_rules": [],
    "strategy_engine": {
        "enabled": False,
        "allow_auto": True,
        "action_points": {},
        "steps": [],
    },
}

INTELLIGENCE_PROFILES = {
    "Safe Climb": {
        "real_threat_dodge": 72,
        "bot_threat_dodge": 96,
        "always_dodge_heroes": ["Owl of Readiness"],
        "disable_dodge_at_master_plus": True,
    },
    "Maximum Matches": {
        "real_threat_dodge": 101,
        "bot_threat_dodge": 101,
        "always_dodge_heroes": [],
        "disable_dodge_at_master_plus": False,
    },
    "Master Push": {
        "real_threat_dodge": 62,
        "bot_threat_dodge": 94,
        "always_dodge_heroes": ["Owl of Readiness"],
        "disable_dodge_at_master_plus": False,
    },
    "No Dodge": {
        "real_threat_dodge": 101,
        "bot_threat_dodge": 101,
        "always_dodge_heroes": [],
        "disable_dodge_at_master_plus": False,
    },
}

_intelligence_lock = threading.RLock()
_hero_library_lock = threading.RLock()


def _deep_merge(base, saved):
    out = dict(base)
    if not isinstance(saved, dict):
        return out
    for key, value in saved.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_intelligence_settings():
    data = dict(DEFAULT_INTELLIGENCE_SETTINGS)
    data["notifications"] = dict(DEFAULT_INTELLIGENCE_SETTINGS["notifications"])
    data["goal"] = dict(DEFAULT_INTELLIGENCE_SETTINGS["goal"])
    data["threat_weights"] = dict(DEFAULT_INTELLIGENCE_SETTINGS["threat_weights"])
    data["strategy_engine"] = {
        "enabled": False,
        "allow_auto": True,
        "action_points": {},
        "steps": [],
    }
    try:
        if INTELLIGENCE_SETTINGS_FILE.exists():
            saved = json.loads(INTELLIGENCE_SETTINGS_FILE.read_text(encoding="utf-8"))
            data = _deep_merge(data, saved)
    except Exception:
        pass
    if data.get("active_profile") not in INTELLIGENCE_PROFILES:
        data["active_profile"] = "Safe Climb"
    return data


intelligence_settings = load_intelligence_settings()


def save_intelligence_settings():
    with _intelligence_lock:
        tmp = INTELLIGENCE_SETTINGS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(intelligence_settings, indent=2), encoding="utf-8")
        os.replace(tmp, INTELLIGENCE_SETTINGS_FILE)


def get_intelligence_settings():
    with _intelligence_lock:
        # round-trip gives callers a detached nested copy without importing copy.
        return json.loads(json.dumps(intelligence_settings))


def update_intelligence_setting(key, value):
    with _intelligence_lock:
        intelligence_settings[key] = value
    save_intelligence_settings()


def current_profile_name():
    name = get_intelligence_settings().get("active_profile") or "Safe Climb"
    return name if name in INTELLIGENCE_PROFILES else "Safe Climb"


def current_profile():
    return dict(INTELLIGENCE_PROFILES.get(current_profile_name(), INTELLIGENCE_PROFILES["Safe Climb"]))


def _safe_slug(value):
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "hero").strip()).strip("._-")
    return value[:60] or "hero"


def load_hero_library_meta():
    with _hero_library_lock:
        try:
            if HERO_LIBRARY_FILE.exists():
                data = json.loads(HERO_LIBRARY_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


def save_hero_library_meta(data):
    with _hero_library_lock:
        tmp = HERO_LIBRARY_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, HERO_LIBRARY_FILE)


def hero_library_summary():
    meta = load_hero_library_meta()
    out = []
    for slug, item in sorted(meta.items(), key=lambda kv: str(kv[1].get("label", kv[0])).lower()):
        folder = HERO_TEMPLATE_DIR / slug
        count = len(list(folder.glob("*.png"))) if folder.exists() else 0
        out.append({
            "slug": slug,
            "label": item.get("label") or slug,
            "samples": count,
            "threat": int(item.get("threat", get_intelligence_settings().get("threat_weights", {}).get(item.get("label") or slug, 20))),
        })
    owl_count = len(load_owl_samples())
    if owl_count and not any(x["label"].lower() == "owl of readiness" for x in out):
        out.insert(0, {"slug": "legacy_owl", "label": "Owl of Readiness", "samples": owl_count, "threat": 40})
    return out


def load_hero_templates():
    meta = load_hero_library_meta()
    library = {}
    for slug, item in meta.items():
        label = str(item.get("label") or slug)
        folder = HERO_TEMPLATE_DIR / slug
        samples = []
        if folder.exists():
            for p in sorted(folder.glob("*.png")):
                img = cv2.imread(str(p), cv2.IMREAD_COLOR)
                if img is not None and min(img.shape[:2]) >= 12:
                    samples.append((p.name, img))
        if samples:
            library[label] = samples
    owl = load_owl_samples()
    if owl:
        library.setdefault("Owl of Readiness", owl)
    return library


def scan_enemy_heroes(ref_screen, threshold=None):
    cfg = get_intelligence_settings()
    if not cfg.get("scanner_enabled", True):
        return [], {}
    threshold = float(threshold if threshold is not None else cfg.get("hero_threshold", 0.72))
    library = load_hero_templates()
    if not library:
        return [], {}
    x1, y1, x2, y2 = DODGE_ENEMY_ROI
    enemy = ref_screen[y1:y2, x1:x2]
    if enemy is None or enemy.size == 0:
        return [], {}
    enemy_gray = cv2.cvtColor(enemy, cv2.COLOR_BGR2GRAY)
    found = []
    scores = {}
    for label, samples in library.items():
        best = 0.0
        for _name, sample in samples[:8]:
            sh, sw = sample.shape[:2]
            if sh > enemy.shape[0] or sw > enemy.shape[1]:
                continue
            sg = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
            result = cv2.matchTemplate(enemy_gray, sg, cv2.TM_CCOEFF_NORMED)
            _, score, _, _ = cv2.minMaxLoc(result)
            best = max(best, float(score))
        scores[label] = round(best, 3)
        if best >= threshold:
            found.append(label)
    found.sort(key=lambda name: scores.get(name, 0.0), reverse=True)
    return found, scores


def opponent_username_roi():
    roi = get_opponent_settings().get("username_roi")
    if not isinstance(roi, (list, tuple)) or len(roi) != 4:
        return None
    try:
        x1, y1, x2, y2 = [int(round(float(v))) for v in roi]
    except Exception:
        return None
    x1 = max(0, min(REFERENCE_W - 1, x1))
    y1 = max(0, min(REFERENCE_H - 1, y1))
    x2 = max(x1 + 1, min(REFERENCE_W, x2))
    y2 = max(y1 + 1, min(REFERENCE_H, y2))
    return (x1, y1, x2, y2) if x2 - x1 >= 20 and y2 - y1 >= 8 else None


def read_opponent_username(ref_screen):
    roi = opponent_username_roi()
    if roi is None or not HAS_TESSERACT:
        return None, None
    try:
        region = crop(ref_screen, roi)
        prep = prep_ocr(region, scale=2.8)
        data = pytesseract.image_to_data(prep, config="--psm 7", output_type=pytesseract.Output.DICT)
        pieces, confs = [], []
        for piece, conf in zip(data.get("text", []), data.get("conf", [])):
            piece = str(piece or "").strip()
            if not piece:
                continue
            try:
                c = float(conf)
            except Exception:
                c = -1
            if c >= 35:
                pieces.append(piece)
                confs.append(c)
        text = " ".join(pieces).strip()
        text = re.sub(r"\s+", " ", text)[:80]
        if len(re.sub(r"\W", "", text)) >= 2:
            return text, (sum(confs) / len(confs) if confs else 35.0)
    except Exception:
        pass
    return None, None


def fused_identity(direct_type, source, predicted_queue):
    kind = str(direct_type or "").upper()
    source = str(source or "")
    if kind == "REAL":
        conf = 99 if source == "organization_ocr" else 94
        return "REAL", conf, source or "organization"
    if kind == "BOT":
        return "BOT", 98, source or "organization_blank"
    if predicted_queue == "Weak Bot":
        return "BOT", 92, "queue_model"
    if predicted_queue == "Strong Bot":
        return "BOT", 80, "queue_model"
    return "REAL", 68, "queue_model"


def opponent_memory_stats(username, records=None):
    username = str(username or "").strip().lower()
    if not username:
        return {"matches": 0, "wins": 0, "losses": 0, "dodges": 0, "win_rate": None, "last_seen": None}
    records = load_intel_history() if records is None else records
    rows = [r for r in records if str(r.get("opponent_username") or "").strip().lower() == username]
    played = [r for r in rows if not bool(r.get("was_dodge"))]
    wins = sum(1 for r in played if str(r.get("result") or "").upper() == "WIN")
    losses = sum(1 for r in played if str(r.get("result") or "").upper() == "LOSS")
    dodges = sum(1 for r in rows if bool(r.get("was_dodge")))
    wr = (100.0 * wins / len(played)) if played else None
    return {
        "matches": len(rows), "wins": wins, "losses": losses, "dodges": dodges,
        "win_rate": wr, "last_seen": (rows[-1].get("timestamp") if rows else None),
    }


def hero_matchup_stats(records=None):
    records = load_intel_history() if records is None else records
    out = {}
    for row in records:
        if bool(row.get("was_dodge")):
            continue
        result = str(row.get("result") or "").upper()
        for hero in row.get("detected_heroes") or []:
            bucket = out.setdefault(hero, {"matches": 0, "wins": 0, "losses": 0})
            bucket["matches"] += 1
            if result == "WIN":
                bucket["wins"] += 1
            elif result == "LOSS":
                bucket["losses"] += 1
    for bucket in out.values():
        bucket["win_rate"] = 100.0 * bucket["wins"] / bucket["matches"] if bucket["matches"] else None
    return out


def combo_matchup_stats(records=None):
    records = load_intel_history() if records is None else records
    out = {}
    for row in records:
        if bool(row.get("was_dodge")):
            continue
        heroes = tuple(sorted(set(row.get("detected_heroes") or [])))
        if not heroes:
            continue
        key = " + ".join(heroes)
        bucket = out.setdefault(key, {"matches": 0, "wins": 0, "losses": 0})
        bucket["matches"] += 1
        result = str(row.get("result") or "").upper()
        if result == "WIN": bucket["wins"] += 1
        elif result == "LOSS": bucket["losses"] += 1
    for bucket in out.values():
        bucket["win_rate"] = 100.0 * bucket["wins"] / bucket["matches"] if bucket["matches"] else None
    return out


def compute_threat_score(identity, predicted_queue, heroes, username=None, records=None):
    cfg = get_intelligence_settings()
    weights = cfg.get("threat_weights") or {}
    score = 8.0
    if identity == "REAL":
        score += 22
    elif identity == "BOT":
        score += 3
    if predicted_queue == "Strong Bot":
        score += 12
    elif predicted_queue == "Weak Bot":
        score -= 4
    for hero in heroes or []:
        score += float(weights.get(hero, 20))
    records = load_intel_history() if records is None else records
    mem = opponent_memory_stats(username, records)
    if mem["matches"] >= 2 and mem["win_rate"] is not None:
        score += max(0.0, (50.0 - mem["win_rate"]) * 0.45)
    if heroes:
        combo = combo_matchup_stats(records).get(" + ".join(sorted(set(heroes))))
        if combo and combo["matches"] >= 2 and combo["win_rate"] is not None:
            score += max(0.0, (50.0 - combo["win_rate"]) * 0.30)
    return int(round(max(0.0, min(100.0, score))))


def threat_label(score):
    score = int(score or 0)
    if score >= 80: return "NIGHTMARE"
    if score >= 60: return "HIGH"
    if score >= 35: return "MEDIUM"
    return "LOW"


def _custom_rule_matches(rule, identity, heroes, threat, rank):
    if not isinstance(rule, dict) or not rule.get("enabled", True):
        return False
    wanted_identity = str(rule.get("identity") or "ANY").upper()
    if wanted_identity not in ("ANY", "") and wanted_identity != str(identity or "").upper():
        return False
    required = [str(x).strip().lower() for x in rule.get("heroes", []) if str(x).strip()]
    have = {str(x).lower() for x in heroes or []}
    if required and not all(x in have for x in required):
        return False
    if int(threat or 0) < int(rule.get("min_threat") or 0):
        return False
    if rule.get("below_master_only") and rank_is_master_plus(rank):
        return False
    return True


def evaluate_decision(identity, heroes, threat, rank, predicted_queue):
    cfg = get_intelligence_settings()
    profile_name = current_profile_name()
    if not cfg.get("decision_engine_enabled", True):
        return "PLAY", "Decision Engine disabled", profile_name
    for rule in cfg.get("custom_rules") or []:
        if _custom_rule_matches(rule, identity, heroes, threat, rank):
            action = str(rule.get("action") or "PLAY").upper()
            return action, str(rule.get("name") or "Custom rule"), profile_name
    profile = current_profile()
    if profile.get("disable_dodge_at_master_plus") and rank_is_master_plus(rank):
        return "PLAY", "Profile plays everything at Master+", profile_name
    hero_set = {str(x).lower() for x in heroes or []}
    for hero in profile.get("always_dodge_heroes") or []:
        if str(hero).lower() in hero_set:
            return "DODGE", f"{profile_name}: {hero} detected", profile_name
    limit = int(profile.get("real_threat_dodge", 101) if identity == "REAL" else profile.get("bot_threat_dodge", 101))
    if int(threat or 0) >= limit:
        return "DODGE", f"{profile_name}: threat {int(threat)} ≥ {limit}", profile_name
    return "PLAY", f"{profile_name}: threat acceptable", profile_name


def collect_opponent_intelligence(ref_screen):
    with session_lock:
        predicted = session.get("expected_next_opponent") or expected_opponent()
        rank = session.get("rank")
    direct_type = direct_org = direct_source = debug = None
    if opponent_org_roi() is not None:
        direct_type, direct_org, direct_source, debug = classify_opponent_by_organization(ref_screen)
    username, username_conf = read_opponent_username(ref_screen)
    heroes, hero_scores = scan_enemy_heroes(ref_screen)
    identity, identity_conf, fused_source = fused_identity(direct_type, direct_source, predicted)
    records = load_intel_history()
    threat = compute_threat_score(identity, predicted, heroes, username, records)
    label = threat_label(threat)
    decision, reason, profile = evaluate_decision(identity, heroes, threat, rank, predicted)
    memory = opponent_memory_stats(username, records)
    return {
        "identity": identity,
        "identity_confidence": identity_conf,
        "organization": direct_org,
        "classification_source": direct_source or fused_source,
        "username": username,
        "username_confidence": username_conf,
        "heroes": heroes,
        "hero_scores": hero_scores,
        "threat": threat,
        "threat_label": label,
        "decision": decision,
        "decision_reason": reason,
        "profile": profile,
        "memory": memory,
        "debug": debug,
    }


def smart_dodge_base_allowed():
    cfg = get_dodge_settings()
    if not cfg.get("enabled"):
        return False
    if cfg.get("disable_at_master_plus") and rank_is_master_plus(session.get("rank")):
        return False
    if not cfg.get("quit_ref") or not cfg.get("confirm_ref"):
        return False
    return True


def intelligence_dodge_ready():
    return smart_dodge_base_allowed() and bool(get_intelligence_settings().get("decision_engine_enabled", True))


def save_match_snapshot(ref_screen):
    if not get_intelligence_settings().get("save_match_snapshots", True):
        return None
    try:
        MATCH_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = MATCH_SNAPSHOT_DIR / f"match_{stamp}.jpg"
        cv2.imwrite(str(path), ref_screen, [int(cv2.IMWRITE_JPEG_QUALITY), 78])
        files = sorted(MATCH_SNAPSHOT_DIR.glob("match_*.jpg"), key=lambda p: p.stat().st_mtime)
        for old in files[:-100]:
            try: old.unlink()
            except Exception: pass
        return path.name
    except Exception:
        return None


def match_snapshot_path(name):
    if not name:
        return None
    path = MATCH_SNAPSHOT_DIR / str(name)
    return path if path.exists() else None


def goal_status():
    cfg = get_intelligence_settings().get("goal") or {}
    if not cfg.get("enabled", True):
        return {"enabled": False, "text": "No active goal", "progress": 0.0, "complete": False}
    gtype = str(cfg.get("type") or "points")
    target = max(1, int(cfg.get("target") or MASTER_V_POINTS))
    with session_lock:
        if gtype == "matches":
            current = int(session.get("matches") or 0)
            label = f"{current}/{target} matches"
        elif gtype == "net":
            current = int(session.get("net_points") or 0)
            label = f"{current:+d}/{target:+d} net pts"
        else:
            current = int(session.get("points") or 0)
            label = f"{current}/{target} pts"
    complete = current >= target
    return {
        "enabled": True, "type": gtype, "target": target, "current": current,
        "progress": max(0.0, min(1.0, current / target)), "complete": complete,
        "text": ("GOAL COMPLETE • " if complete else "GOAL • ") + label,
    }


def _xml_escape(value):
    return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('\"', "&quot;").replace("'", "&apos;")


def send_windows_toast(title, message):
    if os.name != "nt":
        return False
    title = _xml_escape(title)[:120]
    message = _xml_escape(message)[:500]
    script = (
        "$ErrorActionPreference='SilentlyContinue';"
        "$xml=New-Object Windows.Data.Xml.Dom.XmlDocument;"
        f"$xml.LoadXml('<toast><visual><binding template=\"ToastGeneric\"><text>{title}</text><text>{message}</text></binding></visual></toast>');"
        "$toast=[Windows.UI.Notifications.ToastNotification]::new($xml);"
        "$notifier=[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('TG BTC Arena Companion');"
        "$notifier.Show($toast);"
    )
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        )
        return True
    except Exception:
        return False


def strategy_settings():
    cfg = get_intelligence_settings().get("strategy_engine") or {}
    cfg.setdefault("enabled", False)
    cfg.setdefault("allow_auto", True)
    cfg.setdefault("action_points", {})
    cfg.setdefault("steps", [])
    return cfg


def strategy_step_matches(step, identity, heroes, threat):
    if not isinstance(step, dict) or not step.get("enabled", True):
        return False
    wanted = str(step.get("identity") or "ANY").upper()
    if wanted not in ("ANY", "") and wanted != str(identity or "").upper():
        return False
    required = str(step.get("hero") or "").strip().lower()
    if required and required not in {str(x).lower() for x in heroes or []}:
        return False
    if int(threat or 0) < int(step.get("min_threat") or 0):
        return False
    return True


def replay_analysis_lines(records=None, limit=5):
    records = load_intel_history() if records is None else records
    hero_stats = hero_matchup_stats(records)
    ranked = []
    for name, st in hero_stats.items():
        if st["matches"] < 2:
            continue
        ranked.append((st.get("win_rate") if st.get("win_rate") is not None else 100.0, -st["matches"], name, st))
    ranked.sort()
    lines = []
    for wr, _neg, name, st in ranked[:limit]:
        lines.append(f"{name}: {st['wins']}W {st['losses']}L • {wr:.0f}% WR")
    combos = combo_matchup_stats(records)
    combo_ranked = []
    for name, st in combos.items():
        if st["matches"] >= 2:
            combo_ranked.append((st.get("win_rate") if st.get("win_rate") is not None else 100.0, -st["matches"], name, st))
    combo_ranked.sort()
    if combo_ranked:
        wr, _n, name, st = combo_ranked[0]
        lines.append(f"Worst combo: {name} • {st['wins']}W {st['losses']}L • {wr:.0f}% WR")
    return lines or ["Need at least 2 played matches with scanned heroes to analyze matchups."]


class ArenaBotEngine:
    def __init__(self, on_update=None, on_log=None):
        self.on_update = on_update
        self.on_log = on_log
        self.running = False
        self.thread = None
        self.templates = None
        self.device = None

        self._ocr_busy = False
        self._ocr_lock = threading.Lock()
        self._opponent_ocr_busy = False
        self._opponent_ocr_lock = threading.Lock()

        self.last_capture_ms = 0
        self.last_loop_ms = 0

        self.owl_samples = []
        self.dodge_in_progress = False

        # V5.2 Fast Vision
        self.vision = None
        self.vision_mode = "STOPPED"
        self.vision_fps = 0.0
        self.frame_age_ms = 0
        self.last_recognition_ms = 0
        self.last_reaction_ms = 0
        self.tap_mode = "ADB"
        self.actual_w = REFERENCE_W
        self.actual_h = REFERENCE_H
        self.tap_shell = None
        self.match_started_at = None

        # V6.0 live intelligence / battle strategy state.
        self._strategy_executed = set()
        self._strategy_missing_logged = set()

        # V5.8 health telemetry / watchdog.
        self.health_lock = threading.RLock()
        self.health = {}
        self.health_thread = None
        self.health_recovery_count = 0
        self.last_recovery_text = "None yet"
        self.last_recovery_at = 0.0
        self.last_loop_progress_at = time.monotonic()
        self.last_loop_error = None
        self.last_ocr_attempt_at = 0.0
        self.last_ocr_success_at = 0.0
        self.ocr_busy_since = 0.0
        self._adb_failures = 0
        self._last_adb_probe_at = 0.0
        self._last_template_diag_at = 0.0
        self._state_since = time.monotonic()
        self._last_state = "IDLE"
        self._recovery_lock = threading.Lock()
        self._health_check_requested = False
        self.template_diagnostics = {}
        self._init_health()

    def _init_health(self):
        now = time.time()
        defaults = {
            "engine": ("IDLE", "Grinder stopped"),
            "adb": ("IDLE", "Not probed"),
            "vision": ("IDLE", "Stream stopped"),
            "tap": ("IDLE", "Tap shell stopped"),
            "ocr": ("READY" if HAS_TESSERACT else "MISSING", tesseract_path_text()),
            "templates": ("READY", "Waiting for first frame"),
            "dodge": ("OFF", "Smart Dodge disabled"),
            "intel": ("READY", f"Decision profile: {current_profile_name()}"),
            "strategy": ("OFF", "Battle script engine disabled"),
        }
        with self.health_lock:
            for key, (status, detail) in defaults.items():
                self.health[key] = {
                    "status": status,
                    "detail": detail,
                    "updated_at": now,
                    "latency_ms": None,
                }

    def _health_set(self, component, status, detail="", latency_ms=None, *, event=False, action=""):
        component = str(component)
        status = str(status).upper()
        changed = False
        with self.health_lock:
            old = self.health.get(component) or {}
            changed = old.get("status") != status or old.get("detail") != str(detail or "")
            self.health[component] = {
                "status": status,
                "detail": str(detail or ""),
                "updated_at": time.time(),
                "latency_ms": latency_ms,
            }
        if event and changed:
            append_health_event(component, status, detail, action)

    def health_snapshot(self):
        with self.health_lock:
            components = {k: dict(v) for k, v in self.health.items()}
        statuses = [str(v.get("status") or "").upper() for v in components.values()]
        if any(x in ("ERROR", "FAILED") for x in statuses):
            overall = "ISSUE"
        elif any(x in ("RECOVERING", "DEGRADED", "STALE", "CHECK", "NOT READY", "MISSING") for x in statuses):
            overall = "ATTENTION"
        elif self.running:
            overall = "HEALTHY"
        else:
            overall = "IDLE"
        return {
            "overall": overall,
            "components": components,
            "recovery_count": self.health_recovery_count,
            "last_recovery": self.last_recovery_text,
            "last_error": self.last_loop_error,
        }

    def _mark_recovery(self, component, detail):
        self.health_recovery_count += 1
        self.last_recovery_at = time.time()
        self.last_recovery_text = f"{component}: {detail}"
        append_health_event(component, "RECOVERED", detail, "automatic recovery")
        self.emit_log(f"SELF-HEAL: {component} recovered — {detail}")

    def _validate_dodge_health(self):
        cfg = get_dodge_settings()
        if not cfg.get("enabled"):
            self._health_set("dodge", "OFF", "Smart Dodge disabled")
            return
        if cfg.get("disable_at_master_plus") and rank_is_master_plus(session.get("rank")):
            self._health_set("dodge", "PAUSED", "Disabled at Master+")
            return
        missing = []
        if not cfg.get("quit_ref"):
            missing.append("Quit point")
        if not cfg.get("confirm_ref"):
            missing.append("Confirm point")
        if not self.owl_samples:
            missing.append("Owl samples")
        if missing:
            self._health_set("dodge", "NOT READY", "Missing: " + ", ".join(missing))
            return
        self._health_set("dodge", "READY", f"{len(self.owl_samples)} Owl sample(s) • threshold {float(cfg.get('owl_threshold', 0.74)):.2f}")

    def _validate_intelligence_health(self):
        cfg = get_intelligence_settings()
        library = hero_library_summary()
        parts = [f"profile {current_profile_name()}"]
        if cfg.get("scanner_enabled", True):
            parts.append(f"{len(library)} hero template(s)")
        if opponent_org_roi() is None:
            parts.append("ORG fallback=model")
        if opponent_username_roi() is None:
            parts.append("username not calibrated")
        self._health_set("intel", "READY", " • ".join(parts))

        strat = cfg.get("strategy_engine") or {}
        if not strat.get("enabled"):
            self._health_set("strategy", "OFF", "Battle script engine disabled")
            return
        points = strat.get("action_points") or {}
        steps = strat.get("steps") or []
        missing = sorted({str(step.get("action") or "") for step in steps if step.get("action") and step.get("action") not in points})
        if missing:
            self._health_set("strategy", "NOT READY", "Missing actions: " + ", ".join(missing))
        elif not steps:
            self._health_set("strategy", "DEGRADED", "Enabled but no script steps")
        else:
            self._health_set("strategy", "READY", f"{len(steps)} step(s) • AUTO {'ON' if strat.get('allow_auto', True) else 'OFF'}")

    def _recover_tap_shell(self, reason="tap shell stopped"):
        if not self.running:
            return False
        self._health_set("tap", "RECOVERING", reason, event=True, action="restart persistent shell")
        try:
            if self.tap_shell:
                self.tap_shell.stop()
            self.tap_shell = AdbTapShell(self.device)
            if self.tap_shell.start():
                self.tap_mode = "PERSISTENT SHELL"
                self._health_set("tap", "HEALTHY", "Persistent ADB shell active", event=True)
                self._mark_recovery("Tap shell", "persistent shell restarted")
                return True
            self.tap_mode = "ADB PROCESS"
            self._health_set("tap", "DEGRADED", "Persistent shell unavailable; process fallback")
        except Exception as exc:
            self._health_set("tap", "ERROR", str(exc), event=True)
        return False

    def _recover_vision(self, reason="stale frames"):
        if not self.running:
            return False
        if not self._recovery_lock.acquire(blocking=False):
            return False
        try:
            self._health_set("vision", "RECOVERING", reason, event=True, action="restart Fast Vision")
            self.vision_mode = "RECOVERING"
            old = self.vision
            if old:
                try:
                    old.stop()
                except Exception:
                    pass
            self.vision = VisionStream(
                self.device, REFERENCE_W, REFERENCE_H, target_fps=12,
                on_status=self.emit_log
            )
            if self.vision.start(wait_seconds=4.0):
                self.vision_mode = "STREAM"
                self._health_set("vision", "HEALTHY", "Fast Vision stream restarted", event=True)
                self._mark_recovery("Vision", "fresh frames restored")
                return True
            why = self.vision.last_error or "stream produced no frame"
            self.vision.stop()
            self.vision_mode = "FALLBACK SCREENSHOT"
            self._health_set("vision", "DEGRADED", f"Using screencap fallback: {why}", event=True)
            return False
        except Exception as exc:
            self.vision_mode = "FALLBACK SCREENSHOT"
            self._health_set("vision", "ERROR", str(exc), event=True)
            return False
        finally:
            self._recovery_lock.release()

    def _recover_adb(self, reason="ADB probe failed"):
        if not self.running:
            return False
        if time.time() - self.last_recovery_at < HEALTH_RECOVERY_COOLDOWN_SECONDS:
            return False
        if not self._recovery_lock.acquire(blocking=False):
            return False
        try:
            self._health_set("adb", "RECOVERING", reason, event=True, action="adb reconnect")
            self.emit_log(f"SELF-HEAL: reconnecting ADB ({reason})")
            commands = [["adb", "reconnect"]]
            if self.device and ":" in str(self.device):
                commands.append(["adb", "connect", str(self.device)])
            for cmd in commands:
                try:
                    subprocess.run(cmd, capture_output=True, timeout=4.0, check=False, **_hidden_process_kwargs())
                except Exception:
                    pass
            time.sleep(0.6)
            new_device = get_device()
            if new_device:
                changed_device = new_device != self.device
                self.device = new_device
                self._adb_failures = 0
                ok, latency, detail = probe_adb_device(self.device)
                if ok:
                    self._health_set("adb", "HEALTHY", f"{self.device} • {latency} ms", latency, event=True)
                    # Device/shell recovery also refreshes the two ADB-dependent workers.
                    if self.tap_shell:
                        try: self.tap_shell.stop()
                        except Exception: pass
                    self.tap_shell = AdbTapShell(self.device)
                    if self.tap_shell.start():
                        self.tap_mode = "PERSISTENT SHELL"
                        self._health_set("tap", "HEALTHY", "Persistent ADB shell active")
                    else:
                        self.tap_mode = "ADB PROCESS"
                        self._health_set("tap", "DEGRADED", "Process fallback")
                    self._mark_recovery("ADB", "reconnected" + (" to new device" if changed_device else ""))
                    # Vision is tied to the ADB transport; recycle it after reconnect.
                    def delayed_vision_recover():
                        time.sleep(0.25)
                        self._recover_vision("ADB transport recovered")
                    threading.Thread(target=delayed_vision_recover, daemon=True).start()
                    return True
            self._health_set("adb", "ERROR", "Reconnect did not find an online device", event=True)
            return False
        except Exception as exc:
            self._health_set("adb", "ERROR", str(exc), event=True)
            return False
        finally:
            self._recovery_lock.release()

    def _diagnose_templates(self, ref):
        try:
            scores = {}
            for name, roi_name in (("try_again", "try_again"), ("start_matching", "start_matching"), ("victory", "victory")):
                x1, y1, x2, y2 = SEARCH_ROIS[roi_name]
                score, _ = template_score(ref[y1:y2, x1:x2], self.templates[name])
                scores[name] = round(float(score), 3)
            x1, y1, x2, y2 = SEARCH_ROIS["auto"]
            roi = ref[y1:y2, x1:x2]
            off_score, _ = template_score(roi, self.templates["auto_off"])
            on_score, _ = template_score(roi, self.templates["auto_on"])
            scores["auto_off"] = round(float(off_score), 3)
            scores["auto_on"] = round(float(on_score), 3)
            self.template_diagnostics = scores
            best_name, best_score = max(scores.items(), key=lambda item: item[1])
            if best_score >= 0.70:
                self._health_set("templates", "HEALTHY", f"Best {best_name} {best_score:.3f}")
            else:
                detail = " • ".join(f"{k} {v:.2f}" for k, v in sorted(scores.items(), key=lambda x: -x[1])[:3])
                # Save one annotated evidence frame whenever a stuck-state diagnostic
                # finds weak recognition. This makes future template repair concrete.
                try:
                    annotated = ref.copy()
                    for roi_name, box in SEARCH_ROIS.items():
                        x1, y1, x2, y2 = box
                        cv2.rectangle(annotated, (x1, y1), (x2, y2), (255, 255, 255), 1)
                        cv2.putText(annotated, roi_name, (x1 + 4, min(y2 - 4, y1 + 16)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    debug_path = HEALTH_DEBUG_DIR / f"template_low_{stamp}.png"
                    cv2.imwrite(str(debug_path), annotated)
                    detail += f" • saved {debug_path.name}"
                    # Bound the folder so unattended runs never fill the disk.
                    old_files = sorted(HEALTH_DEBUG_DIR.glob("template_low_*.png"), key=lambda x: x.stat().st_mtime)
                    for old_file in old_files[:-20]:
                        try: old_file.unlink()
                        except Exception: pass
                except Exception:
                    pass
                self._health_set("templates", "CHECK", f"Low confidence: {detail}", event=True)
        except Exception as exc:
            self._health_set("templates", "ERROR", str(exc))

    def request_health_check(self):
        self._health_check_requested = True

    def recover_vision_manual(self):
        threading.Thread(target=self._recover_vision, args=("manual restart",), daemon=True).start()

    def recover_adb_manual(self):
        # Manual recovery bypasses the normal cooldown.
        self.last_recovery_at = 0.0
        threading.Thread(target=self._recover_adb, args=("manual reconnect",), daemon=True).start()

    def recover_tap_manual(self):
        threading.Thread(target=self._recover_tap_shell, args=("manual restart",), daemon=True).start()

    def _watchdog_loop(self):
        while self.running:
            try:
                now_mono = time.monotonic()
                now = time.time()
                self._health_set("engine", "HEALTHY", "Recognition loop running")
                self._validate_dodge_health()
                self._validate_intelligence_health()

                # Persistent shell health is cheap to inspect locally.
                tap_ok = bool(self.tap_shell and self.tap_shell.proc and self.tap_shell.proc.poll() is None)
                if tap_ok:
                    self._health_set("tap", "HEALTHY", "Persistent ADB shell active")
                elif self.tap_mode == "ADB PROCESS":
                    self._health_set("tap", "DEGRADED", "Using one-shot ADB process fallback")
                else:
                    self._recover_tap_shell("persistent shell exited")

                # Fast Vision should always be fresh while STREAM is selected.
                if self.vision_mode == "STREAM" and self.vision:
                    _, age_ms, _ = self.vision.get_latest()
                    if age_ms is None:
                        self._health_set("vision", "STALE", "No frame received yet")
                    elif age_ms > HEALTH_STALE_FRAME_MS:
                        self._health_set("vision", "STALE", f"Frame age {int(age_ms)} ms", event=True)
                        if now - self.last_recovery_at >= HEALTH_RECOVERY_COOLDOWN_SECONDS:
                            self._recover_vision(f"frame stalled at {int(age_ms)} ms")
                    else:
                        self._health_set("vision", "HEALTHY", f"{self.vision.fps:.1f} FPS • {int(age_ms)} ms frame age")
                elif self.vision_mode == "FALLBACK SCREENSHOT":
                    self._health_set("vision", "DEGRADED", "Fast Vision unavailable • screencap fallback")
                elif self.vision_mode == "RECOVERING":
                    self._health_set("vision", "RECOVERING", "Restart in progress")

                # ADB probe is deliberately infrequent so it never competes with Arena taps.
                if self._health_check_requested or now - self._last_adb_probe_at >= HEALTH_ADB_PROBE_SECONDS:
                    self._health_check_requested = False
                    self._last_adb_probe_at = now
                    ok, latency, detail = probe_adb_device(self.device)
                    if ok:
                        self._adb_failures = 0
                        self._health_set("adb", "HEALTHY", f"{self.device} • {latency} ms", latency)
                    else:
                        self._adb_failures += 1
                        self._health_set("adb", "CHECK", f"Probe {self._adb_failures}/2 failed: {detail}", latency)
                        if self._adb_failures >= 2:
                            self._recover_adb(detail)

                # OCR workers are asynchronous. Detect a genuinely wedged worker.
                if not HAS_TESSERACT:
                    self._health_set("ocr", "MISSING", tesseract_path_text())
                elif self._ocr_busy:
                    busy_for = now_mono - self.ocr_busy_since if self.ocr_busy_since else 0.0
                    if busy_for > 15.0:
                        self._health_set("ocr", "STALE", f"OCR worker busy {busy_for:.0f}s", event=True)
                        # We cannot safely kill pytesseract's current thread; release the gate so the next
                        # result can recover naturally while logging the stale worker.
                        with self._ocr_lock:
                            self._ocr_busy = False
                            self.ocr_busy_since = 0.0
                        self._mark_recovery("OCR", "released stale worker gate")
                    else:
                        self._health_set("ocr", "BUSY", f"Background OCR {busy_for:.1f}s")
                else:
                    suffix = ""
                    if self.last_ocr_success_at:
                        suffix = f" • last success {int(now - self.last_ocr_success_at)}s ago"
                    self._health_set("ocr", "READY", "Tesseract ready" + suffix)

                # If the app remains in an unrecognized state too long, run one low-frequency
                # diagnostic scoring pass. We diagnose rather than tapping blindly.
                with session_lock:
                    state = str(session.get("status") or "")
                if state != self._last_state:
                    self._last_state = state
                    self._state_since = now_mono
                stuck_for = now_mono - self._state_since
                if state == "MATCHING / LOADING" and stuck_for >= HEALTH_STUCK_STATE_SECONDS:
                    self._health_set("engine", "CHECK", f"Same state for {int(stuck_for)}s")
                    if now - self._last_template_diag_at >= 15.0:
                        self._last_template_diag_at = now
                        ref = None
                        if self.vision_mode == "STREAM" and self.vision:
                            ref, _, _ = self.vision.get_latest()
                        if ref is not None:
                            self._diagnose_templates(ref)
                else:
                    # Keep template status calm unless a stuck-state probe found a problem.
                    current = self.health_snapshot()["components"].get("templates", {})
                    if current.get("status") in ("READY", "CHECK") and stuck_for < HEALTH_STUCK_STATE_SECONDS:
                        self._health_set("templates", "HEALTHY", "UI recognition active")

            except Exception as exc:
                self._health_set("engine", "ERROR", f"Watchdog: {exc}", event=True)
            time.sleep(HEALTH_WATCHDOG_SECONDS)

    def emit_log(self, text):
        log_line(text)
        if self.on_log:
            self.on_log(text)

    def emit_update(self):
        save_session()
        if self.on_update:
            self.on_update()

    def start(self):
        if self.running:
            return

        self.device = get_device()
        if not self.device:
            raise RuntimeError("No ADB device connected.")

        self.templates = load_templates()
        self.reload_dodge_samples()

        size = query_device_size(self.device)
        if size:
            w, h = size
            # wm size is commonly reported in the device's natural portrait
            # orientation even while TG:BTC is landscape.
            if w < h:
                w, h = h, w
            self.actual_w, self.actual_h = w, h

        self.tap_shell = AdbTapShell(self.device)
        if self.tap_shell.start():
            self.tap_mode = "PERSISTENT SHELL"
        else:
            self.tap_mode = "ADB PROCESS"

        # Start continuous H.264 -> ffmpeg vision. If unavailable/unsupported,
        # the old screencap path remains as an automatic fallback.
        self.vision = VisionStream(
            self.device, REFERENCE_W, REFERENCE_H, target_fps=12,
            on_status=self.emit_log
        )
        if self.vision.start(wait_seconds=5.0):
            self.vision_mode = "STREAM"
            self.emit_log("FAST VISION ready — continuous Android stream active")
        else:
            self.vision_mode = "FALLBACK SCREENSHOT"
            why = self.vision.last_error or "stream did not produce a frame"
            self.emit_log(f"FAST VISION unavailable ({why}) — using screencap fallback")
            self.vision.stop()

        self.running = True
        self._health_set("engine", "HEALTHY", "Recognition loop starting")
        self._health_set("adb", "HEALTHY", f"{self.device} • connected")
        self._health_set("tap", "HEALTHY" if self.tap_mode == "PERSISTENT SHELL" else "DEGRADED", self.tap_mode)
        if self.vision_mode == "STREAM":
            self._health_set("vision", "HEALTHY", "Fast Vision stream active")
        else:
            self._health_set("vision", "DEGRADED", "Screenshot fallback active")
        self._validate_dodge_health()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        self.health_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self.health_thread.start()
        self.emit_log(f"Started on {self.device}")

    def stop(self):
        self.running = False
        if self.vision:
            self.vision.stop()
        if self.tap_shell:
            self.tap_shell.stop()
        self.vision_mode = "STOPPED"
        self._health_set("engine", "IDLE", "Grinder stopped")
        self._health_set("vision", "IDLE", "Stream stopped")
        self._health_set("tap", "IDLE", "Tap shell stopped")
        self._health_set("adb", "IDLE", "Not probing while stopped")
        self._validate_dodge_health()
        with session_lock:
            session["status"] = "Stopped"
            session["auto"] = "N/A"
        self.emit_update()
        self.emit_log("Stopped by user")

    def reload_dodge_samples(self):
        self.owl_samples = load_owl_samples()

    def _tap_reference(self, ref_x, ref_y, actual_w=None, actual_h=None):
        actual_w = actual_w or self.actual_w
        actual_h = actual_h or self.actual_h
        x = round(float(ref_x) * actual_w / REFERENCE_W)
        y = round(float(ref_y) * actual_h / REFERENCE_H)
        started = time.perf_counter()
        ok = False
        if self.tap_shell:
            ok = self.tap_shell.tap(x, y)
        if not ok:
            tap_reference(ref_x, ref_y, actual_w, actual_h)
        return (time.perf_counter() - started) * 1000.0

    def _perform_dodge(self, ref_screen, actual_w, actual_h, score=0.0, sample_name=None, reason="Owl of Readiness"):
        cfg = get_dodge_settings()

        quit_ref = cfg.get("quit_ref")
        confirm_ref = cfg.get("confirm_ref")

        if not quit_ref or not confirm_ref:
            self.emit_log(
                "OWL DETECTED but Dodge is not calibrated: "
                "set Quit + Confirm points in Smart Dodge panel."
            )
            return False

        # Find and press PAUSE using the supplied battle UI template.
        pause = find_template(
            ref_screen,
            self.templates["pause"],
            "pause"
        )

        if pause:
            _, px, py = pause
        else:
            # Safe fallback to the known top-left Pause location.
            px, py = 95, 48

        self.dodge_in_progress = True

        with session_lock:
            session["status"] = "DODGING"
            session["auto"] = "N/A"
            session["dodges"] = session.get("dodges", 0) + 1
            if str(reason).lower().startswith("owl"):
                session["owl_detections"] = session.get("owl_detections", 0) + 1
                session["last_owl_score"] = round(float(score or 0.0), 3)
                session["last_owl_sample"] = sample_name
            session["last_dodge_reason"] = str(reason or "Decision Engine")

        self.emit_update()
        self.emit_log(
            f"SMART DODGE: {reason} -> quitting match" + (f" ({float(score):.3f})" if score else "")
        )

        # Pause -> Quit -> Confirm.
        self._tap_reference(px, py, actual_w, actual_h)
        time.sleep(0.30)

        self._tap_reference(
            float(quit_ref[0]),
            float(quit_ref[1]),
            actual_w,
            actual_h
        )
        time.sleep(0.35)

        self._tap_reference(
            float(confirm_ref[0]),
            float(confirm_ref[1]),
            actual_w,
            actual_h
        )

        self.emit_log("SMART DODGE: quit + confirm taps sent")
        return True

    # --------------------------
    # BACKGROUND OPPONENT INTELLIGENCE
    # --------------------------
    def _start_opponent_identity_check(self, ref_snapshot):
        cfg = get_intelligence_settings()
        configured = (
            opponent_org_roi() is not None
            or opponent_username_roi() is not None
            or bool(load_hero_templates())
            or cfg.get("decision_engine_enabled", True)
        )
        if not configured:
            return False
        with self._opponent_ocr_lock:
            if self._opponent_ocr_busy:
                return False
            self._opponent_ocr_busy = True
        snapshot = ref_snapshot.copy()

        def worker():
            try:
                intel = collect_opponent_intelligence(snapshot)
                snap_name = save_match_snapshot(snapshot)
                with session_lock:
                    session["current_opponent_type"] = intel.get("identity")
                    session["current_opponent_org"] = intel.get("organization")
                    session["current_opponent_source"] = intel.get("classification_source")
                    session["current_opponent_username"] = intel.get("username")
                    session["current_identity_confidence"] = intel.get("identity_confidence")
                    session["current_detected_heroes"] = list(intel.get("heroes") or [])
                    session["current_hero_scores"] = dict(intel.get("hero_scores") or {})
                    session["current_threat_score"] = intel.get("threat")
                    session["current_threat_label"] = intel.get("threat_label")
                    session["current_decision"] = intel.get("decision")
                    session["current_decision_reason"] = intel.get("decision_reason")
                    session["current_profile"] = intel.get("profile")
                    session["current_opening_snapshot"] = snap_name
                hero_text = ", ".join(intel.get("heroes") or []) or "none recognized"
                user_text = intel.get("username") or "unknown"
                mem = intel.get("memory") or {}
                mem_text = ""
                if mem.get("matches"):
                    wr = mem.get("win_rate")
                    mem_text = f" | seen {mem['matches']}x" + (f" • {wr:.0f}% WR" if wr is not None else "")
                self.emit_log(
                    f"OPPONENT INTEL: {intel.get('identity')} {intel.get('identity_confidence')}% | "
                    f"{user_text}{mem_text} | heroes={hero_text} | "
                    f"threat={intel.get('threat_label')} {intel.get('threat')} | "
                    f"decision={intel.get('decision')}"
                )
                self.emit_update()
            except Exception as e:
                self.emit_log(f"Opponent intelligence error: {e}")
            finally:
                with self._opponent_ocr_lock:
                    self._opponent_ocr_busy = False

        threading.Thread(target=worker, daemon=True).start()
        return True

    def _run_strategy_steps(self, now, actual_w, actual_h):
        cfg = strategy_settings()
        if not cfg.get("enabled") or self.match_started_at is None or self.dodge_in_progress:
            return
        elapsed_ms = int((time.monotonic() - self.match_started_at) * 1000)
        with session_lock:
            identity = session.get("current_opponent_type")
            heroes = list(session.get("current_detected_heroes") or [])
            threat = int(session.get("current_threat_score") or 0)
        points = cfg.get("action_points") or {}
        steps = cfg.get("steps") or []
        for idx, step in enumerate(steps):
            if idx in self._strategy_executed:
                continue
            if elapsed_ms < int(step.get("at_ms") or 0):
                continue
            if not strategy_step_matches(step, identity, heroes, threat):
                # Conditional steps wait briefly for the opening intelligence scan.
                with session_lock:
                    intel_ready = session.get("current_decision") is not None
                if not intel_ready and elapsed_ms < 5000 and (step.get("hero") or str(step.get("identity") or "ANY").upper() != "ANY" or int(step.get("min_threat") or 0) > 0):
                    continue
                self._strategy_executed.add(idx)
                continue
            action = str(step.get("action") or "").strip()
            point = points.get(action)
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                if action and action not in self._strategy_missing_logged:
                    self.emit_log(f"STRATEGY: action '{action}' is not calibrated — step skipped")
                    self._strategy_missing_logged.add(action)
                self._strategy_executed.add(idx)
                continue
            self._tap_reference(float(point[0]), float(point[1]), actual_w, actual_h)
            self._strategy_executed.add(idx)
            with session_lock:
                session["current_battle_strategy"] = "SCRIPT"
            self.emit_log(f"STRATEGY: {action} at {elapsed_ms}ms")

    # --------------------------
    # BACKGROUND OCR
    # --------------------------
    def _start_arena_ocr(self, ref_snapshot):
        if not HAS_TESSERACT:
            return
        with self._ocr_lock:
            if self._ocr_busy:
                return
            self._ocr_busy = True
            self.last_ocr_attempt_at = time.time()
            self.ocr_busy_since = time.monotonic()

        # Copy only once because the main loop immediately continues.
        snapshot = ref_snapshot.copy()

        def worker():
            try:
                rank, points = read_arena_status(snapshot)
                if rank is not None or points is not None:
                    self.last_ocr_success_at = time.time()
                with session_lock:
                    old_points = session.get("points")
                    current_match = int(session.get("matches") or 0)
                    current_session_id = session.get("started_at") or "unknown"
                    changed = update_rank_points(rank, points)
                    inferred_delta = None
                    if points is not None and old_points is not None and points != old_points:
                        inferred_delta = int(points) - int(old_points)
                        session["known_point_changes"].append(inferred_delta)
                        session["known_point_changes"] = session["known_point_changes"][-500:]
                if changed:
                    if current_match > 0:
                        enrich_intel_match(
                            current_session_id,
                            current_match,
                            rank=rank,
                            points=points,
                            delta=inferred_delta,
                        )
                    self.emit_log(
                        f"OCR Arena: {rank or '?'} | "
                        f"{points if points is not None else '?'} pts"
                    )
                    self.emit_update()
            except Exception as e:
                self.emit_log(f"OCR Arena error: {e}")
            finally:
                with self._ocr_lock:
                    self._ocr_busy = False
                    self.ocr_busy_since = 0.0

        threading.Thread(target=worker, daemon=True).start()

    def _start_result_ocr(self, ref_snapshot, is_win, match_no):
        # Result itself is registered immediately. OCR only enriches rank/points.
        if not HAS_TESSERACT:
            return

        with self._ocr_lock:
            if self._ocr_busy:
                return
            self._ocr_busy = True
            self.last_ocr_attempt_at = time.time()
            self.ocr_busy_since = time.monotonic()

        snapshot = ref_snapshot.copy()
        with session_lock:
            result_session_started_at = session.get("started_at") or "unknown"

        def worker():
            try:
                rank, points, delta = read_result_status(snapshot)
                if rank is not None or points is not None or delta is not None:
                    self.last_ocr_success_at = time.time()

                with session_lock:
                    old_points = session["points"]
                    changed = update_rank_points(rank, points)

                    if (
                        delta is None
                        and points is not None
                        and old_points is not None
                    ):
                        delta = points - old_points

                    if delta is not None:
                        # Attach OCR delta to analytics without counting another match.
                        session["known_point_changes"].append(delta)
                        session["known_point_changes"] = session["known_point_changes"][-500:]

                enrich_intel_match(
                    result_session_started_at,
                    match_no,
                    rank=rank,
                    points=points,
                    delta=delta,
                )

                self.emit_log(
                    f"OCR Result: {rank or '?'} | "
                    f"{points if points is not None else '?'} pts | "
                    f"delta {delta if delta is not None else '?'}"
                )
                self.emit_update()

            except Exception as e:
                self.emit_log(f"OCR Result error: {e}")
            finally:
                with self._ocr_lock:
                    self._ocr_busy = False
                    self.ocr_busy_since = 0.0

        threading.Thread(target=worker, daemon=True).start()

    def _loop(self):
        last_action = None
        last_action_at = 0.0
        auto_lockout_until = 0.0
        result_screen_counted = False

        # Smart Dodge checks only the opening seconds of each fight.
        dodge_checked = False
        dodge_check_until = 0.0
        owl_confirm_hits = 0
        owl_best_score = 0.0
        owl_best_sample = None
        opponent_identity_checked = False
        last_stream_frame_id = None

        while self.running:
            loop_started = time.perf_counter()
            self.last_loop_progress_at = time.monotonic()

            try:
                # V5.2: consume the newest continuously-streamed frame.
                # No new adb screencap process per recognition cycle.
                ref = None
                frame_id = None

                if self.vision_mode == "STREAM" and self.vision:
                    ref, age_ms, frame_id = self.vision.get_latest()
                    self.vision_fps = self.vision.fps
                    if ref is not None:
                        self.frame_age_ms = int(age_ms or 0)
                        self.last_capture_ms = self.frame_age_ms

                    # If the stream is temporarily restarting, wait for a fresh
                    # frame rather than launching a multi-second screencap.
                    if ref is None or (age_ms is not None and age_ms > 1800):
                        time.sleep(0.02)
                        continue
                else:
                    capture_started = time.perf_counter()
                    screen = capture_screen()
                    self.last_capture_ms = int(
                        (time.perf_counter() - capture_started) * 1000
                    )
                    actual_h0, actual_w0 = screen.shape[:2]
                    self.actual_w, self.actual_h = actual_w0, actual_h0
                    ref = resize_reference(screen)
                    self.frame_age_ms = self.last_capture_ms
                    self.vision_fps = 0.0

                actual_w, actual_h = self.actual_w, self.actual_h
                now = time.time()
                recognition_started = time.perf_counter()

                if frame_id is not None:
                    if frame_id == last_stream_frame_id:
                        time.sleep(0.003)
                        continue
                    last_stream_frame_id = frame_id

                # ====================================================
                # RESULT: CLICK FIRST. OCR AFTERWARD.
                # ====================================================
                try_again = find_template(
                    ref,
                    self.templates["try_again"],
                    "try_again"
                )

                if try_again:
                    was_dodge = self.dodge_in_progress
                    match_duration = (time.monotonic() - self.match_started_at) if self.match_started_at else None
                    self.dodge_in_progress = False
                    self.match_started_at = None
                    dodge_checked = False
                    dodge_check_until = 0.0
                    owl_confirm_hits = 0
                    owl_best_score = 0.0
                    owl_best_sample = None
                    opponent_identity_checked = False
                    self._strategy_executed.clear()
                    self._strategy_missing_logged.clear()

                    with session_lock:
                        session["status"] = "RESULT"
                        session["auto"] = "N/A"

                    victory = find_template(
                        ref,
                        self.templates["victory"],
                        "victory"
                    )
                    is_win = victory is not None

                    score, x, y = try_again

                    # TOP PRIORITY: get into next match immediately.
                    if (
                        last_action != "TRY_AGAIN"
                        or now - last_action_at >= RESULT_CLICK_COOLDOWN
                    ):
                        tap_ms = self._tap_reference(x, y, actual_w, actual_h)
                        self.last_reaction_ms = int(self.frame_age_ms + (time.perf_counter() - recognition_started) * 1000 + tap_ms)
                        last_action = "TRY_AGAIN"
                        last_action_at = now

                    if not result_screen_counted:
                        # Register result instantly, WITHOUT OCR.
                        with session_lock:
                            recorded_match_no = register_result(
                                is_win=is_win,
                                rank=None,
                                points=None,
                                delta=None,
                                was_dodge=was_dodge,
                                duration=match_duration
                            )
                        result_screen_counted = True
                        self.emit_update()
                        self.emit_log(
                            f"{'WIN' if is_win else 'LOSS'} recorded — next match clicked"
                        )

                        # OCR now runs separately and cannot delay Try Again.
                        self._start_result_ocr(ref, is_win, recorded_match_no)

                    self.last_loop_ms = int(
                        (time.perf_counter() - loop_started) * 1000
                    )
                    time.sleep(POLL_FAST_SECONDS)
                    continue

                result_screen_counted = False

                # ====================================================
                # ARENA: CLICK START FIRST. OCR AFTERWARD.
                # ====================================================
                start = find_template(
                    ref,
                    self.templates["start_matching"],
                    "start_matching"
                )

                if start:
                    self.dodge_in_progress = False
                    dodge_checked = False
                    dodge_check_until = 0.0
                    owl_confirm_hits = 0
                    owl_best_score = 0.0
                    owl_best_sample = None
                    opponent_identity_checked = False
                    self._strategy_executed.clear()
                    self._strategy_missing_logged.clear()

                    with session_lock:
                        session["status"] = "QUEUEING"
                        session["current_opponent_type"] = None
                        session["current_opponent_org"] = None
                        session["current_opponent_source"] = None
                        session["current_opponent_username"] = None
                        session["current_identity_confidence"] = None
                        session["current_detected_heroes"] = []
                        session["current_hero_scores"] = {}
                        session["current_threat_score"] = None
                        session["current_threat_label"] = None
                        session["current_decision"] = None
                        session["current_decision_reason"] = None
                        session["current_profile"] = None
                        session["current_opening_snapshot"] = None
                        session["current_battle_strategy"] = None
                        session["auto"] = "N/A"

                    score, x, y = start

                    if (
                        last_action != "START_MATCHING"
                        or now - last_action_at >= START_CLICK_COOLDOWN
                    ):
                        tap_ms = self._tap_reference(x, y, actual_w, actual_h)
                        self.last_reaction_ms = int(self.frame_age_ms + (time.perf_counter() - recognition_started) * 1000 + tap_ms)
                        last_action = "START_MATCHING"
                        last_action_at = now
                        self.emit_log("Start Matching clicked")

                        # OCR from the screenshot we already have,
                        # after the tap was sent.
                        self._start_arena_ocr(ref)

                    self.last_loop_ms = int(
                        (time.perf_counter() - loop_started) * 1000
                    )
                    time.sleep(POLL_FAST_SECONDS)
                    continue

                # ====================================================
                # BATTLE: AUTO HAS PRIORITY
                # ====================================================
                auto_state, off_score, on_score, x, y = detect_auto_state(
                    ref,
                    self.templates
                )

                if auto_state in ("OFF", "ON"):
                    with session_lock:
                        session["status"] = "IN BATTLE"

                    # ------------------------------------------------
                    # SMART DODGE — CHECK BEFORE/WHILE AUTO STARTS
                    # ------------------------------------------------
                    if self.match_started_at is None:
                        self.match_started_at = time.monotonic()

                    # One async identity read per battle. It never blocks the
                    # AUTO / Smart Dodge hot path.
                    if not opponent_identity_checked:
                        if self._start_opponent_identity_check(ref):
                            opponent_identity_checked = True

                    # Decision Engine can request a calibrated surrender based on
                    # identity, scanned heroes, threat and active profile.
                    if not self.dodge_in_progress and not dodge_checked and intelligence_dodge_ready():
                        with session_lock:
                            intel_decision = session.get("current_decision")
                            intel_reason = session.get("current_decision_reason")
                            intel_threat = session.get("current_threat_score")
                        if intel_decision == "DODGE":
                            if self._perform_dodge(
                                ref, actual_w, actual_h,
                                score=0.0, sample_name=None,
                                reason=intel_reason or f"Threat {intel_threat}"
                            ):
                                dodge_checked = True
                                self.last_recognition_ms = int((time.perf_counter() - recognition_started) * 1000)
                                self.last_loop_ms = int((time.perf_counter() - loop_started) * 1000)
                                time.sleep(POLL_FAST_SECONDS)
                                continue

                    if not dodge_checked and dodge_check_until == 0.0:
                        # Continuous stream lets us cheaply inspect several real
                        # frames. Require 2 confirmations within 3.5 seconds.
                        dodge_check_until = now + 3.5

                    if (
                        not self.dodge_in_progress
                        and not dodge_checked
                        and now <= dodge_check_until
                        and smart_dodge_allowed()
                        and self.owl_samples
                    ):
                        owl_score, owl_sample = detect_owl(
                            ref,
                            self.owl_samples
                        )

                        if owl_score > owl_best_score:
                            owl_best_score = owl_score
                            owl_best_sample = owl_sample

                        with session_lock:
                            session["last_owl_score"] = round(owl_score, 3)
                            session["last_owl_sample"] = owl_sample

                        cfg = get_dodge_settings()
                        threshold = float(cfg.get("owl_threshold", 0.74))

                        if owl_score >= threshold:
                            owl_confirm_hits += 1
                        else:
                            owl_confirm_hits = 0

                        # Two distinct streamed frames must agree before surrender.
                        if owl_confirm_hits >= 2:
                            if self._perform_dodge(
                                ref,
                                actual_w,
                                actual_h,
                                owl_best_score,
                                owl_best_sample
                            ):
                                dodge_checked = True
                                self.last_recognition_ms = int(
                                    (time.perf_counter() - recognition_started) * 1000
                                )
                                self.last_loop_ms = int(
                                    (time.perf_counter() - loop_started) * 1000
                                )
                                time.sleep(POLL_FAST_SECONDS)
                                continue

                    if now > dodge_check_until:
                        dodge_checked = True

                    if self.dodge_in_progress:
                        # Let the quit/result UI take over; never enable AUTO.
                        time.sleep(POLL_FAST_SECONDS)
                        continue

                    self._run_strategy_steps(now, actual_w, actual_h)
                    strategy_cfg = strategy_settings()
                    if strategy_cfg.get("enabled") and not strategy_cfg.get("allow_auto", True):
                        with session_lock:
                            session["auto"] = "STRATEGY"
                            session["current_battle_strategy"] = "SCRIPT"
                        self.last_loop_ms = int((time.perf_counter() - loop_started) * 1000)
                        time.sleep(POLL_BATTLE_ON_SECONDS)
                        continue

                    if now < auto_lockout_until:
                        with session_lock:
                            session["auto"] = "ENABLING"
                        self.last_loop_ms = int(
                            (time.perf_counter() - loop_started) * 1000
                        )
                        time.sleep(POLL_FAST_SECONDS)
                        continue

                    if auto_state == "OFF":
                        # Tap immediately.
                        tap_ms = self._tap_reference(x, y, actual_w, actual_h)
                        self.last_reaction_ms = int(self.frame_age_ms + (time.perf_counter() - recognition_started) * 1000 + tap_ms)
                        auto_lockout_until = now + AUTO_LOCKOUT_SECONDS

                        with session_lock:
                            session["auto"] = "ENABLING"
                            session["last_action"] = "ENABLE_AUTO"

                        self.emit_log(
                            f"AUTO clicked immediately | "
                            f"OFF={off_score:.3f} ON={on_score:.3f} | "
                            f"capture={self.last_capture_ms}ms"
                        )
                        self.emit_update()
                        last_action = "ENABLE_AUTO"
                        last_action_at = now

                        self.last_loop_ms = int(
                            (time.perf_counter() - loop_started) * 1000
                        )
                        time.sleep(POLL_FAST_SECONDS)
                        continue

                    # AUTO ON: no need to hammer ADB as fast during the fight.
                    changed = False
                    with session_lock:
                        if session["auto"] != "ON":
                            session["auto"] = "ON"
                            session["last_action"] = "WAIT_BATTLE"
                            changed = True
                    if changed:
                        self.emit_update()

                    last_action = "BATTLE_WAIT"
                    self.last_loop_ms = int(
                        (time.perf_counter() - loop_started) * 1000
                    )
                    time.sleep(POLL_BATTLE_ON_SECONDS)
                    continue

                # ====================================================
                # MATCHING / LOADING / ARENA CLOSED
                # ====================================================
                changed = False
                with session_lock:
                    if session["status"] != "MATCHING / LOADING":
                        session["status"] = "MATCHING / LOADING"
                        session["auto"] = "N/A"
                        changed = True

                if changed:
                    self.emit_update()

                self.last_loop_ms = int(
                    (time.perf_counter() - loop_started) * 1000
                )
                time.sleep(POLL_FAST_SECONDS)

            except Exception as e:
                self.last_loop_error = str(e)
                self._health_set("engine", "ERROR", str(e), event=True)
                with session_lock:
                    session["status"] = "ADB / BOT ERROR"
                self.emit_update()
                self.emit_log(f"ERROR: {e}")
                # The watchdog handles transport/stream repair; avoid spawning
                # competing recovery processes from the hot recognition loop.
                time.sleep(POLL_ERROR_SECONDS)


# ==============================================================
# V5.5 FIGMA-BASED DESKTOP UI
# ==============================================================
UI_BG = "#0B111A"
UI_SIDEBAR = "#101722"
UI_CARD = "#111A27"
UI_TILE = "#16202E"
UI_BORDER = "#263244"
UI_TEXT = "#F4F7FB"
UI_MUTED = "#99A6B8"
UI_MUTED_2 = "#738096"
UI_ACCENT = "#FF4D6D"
UI_ACCENT_DARK = "#2A1820"
UI_BLUE = "#67A0FF"
UI_BLUE_DARK = "#142846"
UI_GREEN = "#40D9A3"
UI_GREEN_DARK = "#123B31"
UI_GOLD = "#FFD45E"
UI_AMBER = "#F4B942"
UI_RED = "#FF657D"


class ToggleSwitch(tk.Canvas):
    """Small dependency-free switch used by the V5.5 dashboard."""

    def __init__(self, master, variable, command=None, *, width=38, height=22,
                 bg=UI_CARD, on_color=UI_ACCENT, off_color="#344154"):
        super().__init__(
            master,
            width=width,
            height=height,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.variable = variable
        self.command = command
        self.w = width
        self.h = height
        self.on_color = on_color
        self.off_color = off_color
        self.bind("<Button-1>", self._toggle)
        try:
            self.variable.trace_add("write", lambda *_: self._draw())
        except Exception:
            pass
        self._draw()

    def _toggle(self, _event=None):
        self.variable.set(not bool(self.variable.get()))
        if self.command:
            self.command()
        self._draw()

    def _draw(self):
        self.delete("all")
        active = bool(self.variable.get())
        color = self.on_color if active else self.off_color
        r = self.h / 2
        self.create_rectangle(r, 1, self.w - r, self.h - 1, fill=color, outline=color)
        self.create_oval(1, 1, self.h - 1, self.h - 1, fill=color, outline=color)
        self.create_oval(self.w - self.h + 1, 1, self.w - 1, self.h - 1, fill=color, outline=color)
        knob_x = self.w - r if active else r
        kr = r - 4
        self.create_oval(
            knob_x - kr, r - kr, knob_x + kr, r + kr,
            fill="#FFFFFF", outline="#FFFFFF"
        )


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(f"TG:BTC Game Assistant v{APP_VERSION} — Daily Assistant")
        self.root.geometry("1180x856")
        self.root.minsize(1020, 756)

        # V5.6: draw our own dark title bar instead of the bright native
        # Windows caption.  This keeps the dashboard visually continuous.
        self._maximized = False
        self._restore_geometry = None
        self._drag_dx = 0
        self._drag_dy = 0
        self._resize_state = None
        try:
            self.root.overrideredirect(True)
        except Exception:
            pass

        self.engine = ArenaBotEngine(
            on_update=lambda: self.root.after(0, self.refresh),
            on_log=lambda t: self.root.after(0, lambda: self.add_log(t))
        )

        self.vars = {}
        self.latest_release = None
        self.update_available = False
        self._build_ui()
        self.refresh()

        if MIGRATED_FROM:
            self.add_log(f"Imported Smart Dodge calibration from: {MIGRATED_FROM}")

        if not refresh_tesseract():
            self.add_log(
                "Rank/Points unavailable: Tesseract OCR engine is missing. "
                "Click INSTALL OCR."
            )

        repo = update_settings.get("github_repo", "")
        self.version_var.set(f"v{APP_VERSION}")
        self.update_status_var.set(
            f"Update source: {repo}" if repo else "Updates not configured"
        )
        self.set_update_indicator("idle")

        self.root.after(1000, self.tick)
        self.root.after(1800, self.auto_check_updates)

    def _var(self, name, default="-"):
        v = tk.StringVar(value=default)
        self.vars[name] = v
        return v

    # ==========================================================
    # V5.6 CUSTOM WINDOW CHROME
    # ==========================================================
    def _native_hwnd(self):
        """Best-effort HWND for taskbar/minimize behavior on Windows."""
        if os.name != "nt":
            return None
        try:
            import ctypes
            hwnd = int(self.root.winfo_id())
            parent = int(ctypes.windll.user32.GetParent(hwnd) or 0)
            return parent or hwnd
        except Exception:
            return None

    def _ensure_taskbar_presence(self):
        # overrideredirect windows can be classified as tool windows by
        # Windows.  Flip the extended style back to APPWINDOW so the normal
        # taskbar button and Alt-Tab entry remain available.
        if os.name != "nt":
            return
        try:
            import ctypes
            hwnd = self._native_hwnd()
            if not hwnd:
                return
            user32 = ctypes.windll.user32
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW = 0x00040000
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass

    def _title_press(self, event):
        # Dragging a maximized window restores it first, matching normal
        # Windows behavior closely enough for a custom Tk window.
        if self._maximized:
            pointer_x = self.root.winfo_pointerx()
            ratio = 0.5
            try:
                ratio = max(0.15, min(0.85, event.x / max(1, self.root.winfo_width())))
            except Exception:
                pass
            self._restore_window()
            self.root.update_idletasks()
            new_x = int(pointer_x - self.root.winfo_width() * ratio)
            self.root.geometry(f"+{new_x}+{max(0, self.root.winfo_pointery() - 16)}")

        self._drag_dx = event.x_root - self.root.winfo_x()
        self._drag_dy = event.y_root - self.root.winfo_y()

    def _title_drag(self, event):
        if self._maximized:
            return
        x = event.x_root - self._drag_dx
        y = event.y_root - self._drag_dy
        self.root.geometry(f"+{x}+{y}")

    def _work_area(self):
        if os.name == "nt":
            try:
                import ctypes

                class RECT(ctypes.Structure):
                    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

                class MONITORINFO(ctypes.Structure):
                    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT),
                                ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]

                user32 = ctypes.windll.user32
                hwnd = self._native_hwnd()
                monitor = user32.MonitorFromWindow(hwnd, 2)  # nearest
                info = MONITORINFO()
                info.cbSize = ctypes.sizeof(MONITORINFO)
                if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                    r = info.rcWork
                    return r.left, r.top, r.right - r.left, r.bottom - r.top
            except Exception:
                pass
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def _maximize_window(self):
        if self._maximized:
            return
        self._restore_geometry = self.root.geometry()
        x, y, w, h = self._work_area()
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self._maximized = True
        if hasattr(self, "chrome_max_btn"):
            self.chrome_max_btn.config(text="❐")

    def _restore_window(self):
        if not self._maximized:
            return
        self.root.geometry(self._restore_geometry or "1180x856")
        self._maximized = False
        if hasattr(self, "chrome_max_btn"):
            self.chrome_max_btn.config(text="□")

    def _toggle_maximize(self, event=None):
        if self._maximized:
            self._restore_window()
        else:
            self._maximize_window()

    def _minimize_window(self):
        # Do NOT call ShowWindow() on a guessed Tk parent HWND.  With Tk's
        # borderless wrapper that can target the hidden interpreter window
        # instead of the visible toplevel and make the app appear to close.
        # Temporarily restore the native frame, let Tk perform a normal
        # iconify, then re-apply our custom chrome when Windows maps it again.
        try:
            self._minimize_pending = True
            self.root.overrideredirect(False)
            self.root.update_idletasks()
            self.root.iconify()
        except Exception:
            self._minimize_pending = False

    def _on_window_map(self, event=None):
        try:
            if self.root.state() == "normal":
                self.root.overrideredirect(True)
                self._minimize_pending = False
                self.root.after(25, self._ensure_taskbar_presence)
        except Exception:
            pass

    def close_window(self):
        try:
            try:
                self._daily_shutdown_transport()
            except Exception:
                pass
            if self.engine.running:
                self.engine.stop()
        finally:
            self.root.destroy()

    def _chrome_button(self, parent, text, command, *, close=False):
        normal = UI_BG
        hover = "#C42B1C" if close else UI_TILE
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=normal,
            fg=UI_TEXT,
            activebackground=hover,
            activeforeground="white",
            relief="flat",
            bd=0,
            highlightthickness=0,
            cursor="hand2",
            font=("Segoe UI Symbol", 10, "normal"),
        )
        btn.bind("<Enter>", lambda e: btn.config(bg=hover))
        btn.bind("<Leave>", lambda e: btn.config(bg=normal))
        return btn

    def _begin_resize(self, event, edge):
        if self._maximized:
            return
        self._resize_state = (
            edge, event.x_root, event.y_root,
            self.root.winfo_x(), self.root.winfo_y(),
            self.root.winfo_width(), self.root.winfo_height(),
        )

    def _resize_drag(self, event):
        if not self._resize_state or self._maximized:
            return
        edge, sx, sy, x, y, w, h = self._resize_state
        dx = event.x_root - sx
        dy = event.y_root - sy
        min_w, min_h = 1020, 756
        nx, ny, nw, nh = x, y, w, h

        if "e" in edge:
            nw = max(min_w, w + dx)
        if "s" in edge:
            nh = max(min_h, h + dy)
        if "w" in edge:
            proposed = max(min_w, w - dx)
            nx = x + (w - proposed)
            nw = proposed

        self.root.geometry(f"{int(nw)}x{int(nh)}+{int(nx)}+{int(ny)}")

    def _end_resize(self, event=None):
        self._resize_state = None

    def _install_resize_edges(self):
        # Thin invisible hit areas preserve resizing after removing the
        # native Windows frame.  Bottom corners are intentionally a little
        # wider so they are easy to grab.
        specs = [
            ("w",  {"x": 0, "y": 36, "width": 5, "relheight": 1, "height": -41}, "size_we"),
            ("e",  {"relx": 1, "x": -5, "y": 36, "width": 5, "relheight": 1, "height": -41}, "size_we"),
            ("s",  {"x": 8, "rely": 1, "y": -5, "relwidth": 1, "width": -16, "height": 5}, "size_ns"),
            ("sw", {"x": 0, "rely": 1, "y": -9, "width": 9, "height": 9}, "size_ne_sw"),
            ("se", {"relx": 1, "x": -9, "rely": 1, "y": -9, "width": 9, "height": 9}, "size_nw_se"),
        ]
        self._resize_handles = []
        for edge, place_args, cursor in specs:
            if os.name != "nt":
                cursor = "arrow"
            handle = tk.Frame(self.root, bg=UI_BG, cursor=cursor, bd=0, highlightthickness=0)
            handle.place(**place_args)
            handle.bind("<ButtonPress-1>", lambda e, ed=edge: self._begin_resize(e, ed))
            handle.bind("<B1-Motion>", self._resize_drag)
            handle.bind("<ButtonRelease-1>", self._end_resize)
            self._resize_handles.append(handle)

    def _make_card(self, parent, *, padx=16, pady=14):
        card = tk.Frame(
            parent,
            bg=UI_CARD,
            highlightbackground=UI_BORDER,
            highlightcolor=UI_BORDER,
            highlightthickness=1,
            bd=0,
        )
        body = tk.Frame(card, bg=UI_CARD)
        body.pack(fill="both", expand=True, padx=padx, pady=pady)
        return card, body

    def _label(self, parent, text=None, *, textvariable=None, fg=UI_TEXT,
               bg=None, size=10, weight="normal", anchor="w", **kwargs):
        return tk.Label(
            parent,
            text=text,
            textvariable=textvariable,
            bg=bg or parent.cget("bg"),
            fg=fg,
            font=("Segoe UI", size, weight),
            anchor=anchor,
            bd=0,
            **kwargs,
        )

    def _pill(self, parent, text, *, fg=UI_GREEN, bg=UI_GREEN_DARK):
        return tk.Label(
            parent,
            text=text,
            bg=bg,
            fg=fg,
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=3,
            bd=0,
        )

    def _action_button(self, parent, text, command, *, accent=False, danger=False,
                       width=None):
        if accent:
            bg, hover, fg = UI_ACCENT, "#E53F5E", "white"
        elif danger:
            bg, hover, fg = "#2A1B23", "#3A202B", UI_RED
        else:
            bg, hover, fg = UI_TILE, "#202C3C", UI_TEXT
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=hover,
            activeforeground=fg,
            relief="flat",
            bd=0,
            highlightthickness=0,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            padx=16,
            pady=9,
            width=width,
        )
        return btn

    def _metric_tile(self, parent, title, key, *, value_fg=UI_TEXT):
        tile = tk.Frame(parent, bg=UI_TILE, bd=0)
        self._label(tile, title, fg=UI_MUTED, bg=UI_TILE, size=8).pack(
            anchor="w", padx=10, pady=(8, 1)
        )
        self._label(
            tile,
            textvariable=self.vars[key],
            fg=value_fg,
            bg=UI_TILE,
            size=10,
            weight="bold"
        ).pack(anchor="w", padx=10, pady=(0, 8))
        return tile

    def _nav_button(self, parent, text, icon, command, *, active=False):
        bg = UI_ACCENT_DARK if active else UI_SIDEBAR
        fg = UI_TEXT if active else UI_MUTED
        btn = tk.Button(
            parent,
            text=f"{icon}   {text}",
            command=command,
            bg=bg,
            fg=fg,
            activebackground=UI_ACCENT_DARK if active else UI_TILE,
            activeforeground=UI_TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            cursor="hand2",
            anchor="w",
            font=("Segoe UI", 10, "bold" if active else "normal"),
            padx=14,
            pady=11,
        )
        return btn

    def _set_active_nav(self, active_name):
        for name, btn in getattr(self, "nav_buttons", {}).items():
            active = name == active_name
            btn.config(
                bg=UI_ACCENT_DARK if active else UI_SIDEBAR,
                fg=UI_TEXT if active else UI_MUTED,
                font=("Segoe UI", 10, "bold" if active else "normal"),
            )

    def show_dashboard(self):
        for page_name in ("history_page", "intelligence_page", "strategy_page", "diagnostics_page", "daily_page", "vision_page"):
            page = getattr(self, page_name, None)
            if page is not None:
                try:
                    page.grid_remove()
                except Exception:
                    pass
        if hasattr(self, "dashboard_main"):
            self.dashboard_main.grid()
        self._set_active_nav("dashboard")

    def _build_ui(self):
        self.root.configure(bg=UI_BG)

        # ttk is kept for the progress bar and existing dialogs.  Clam lets
        # us color it consistently on Windows without another dependency.
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "Arena.Horizontal.TProgressbar",
            troughcolor="#222D3C",
            background=UI_ACCENT,
            darkcolor=UI_ACCENT,
            lightcolor=UI_ACCENT,
            bordercolor="#222D3C",
            thickness=8,
        )
        style.configure("TFrame", background=UI_BG)
        style.configure("TLabel", background=UI_BG, foreground=UI_TEXT)
        style.configure("TButton", padding=7)
        style.configure(
            "Arena.Treeview",
            background=UI_CARD,
            fieldbackground=UI_CARD,
            foreground=UI_MUTED,
            rowheight=26,
            borderwidth=0,
            relief="flat",
            font=("Segoe UI", 8),
        )
        style.configure(
            "Arena.Treeview.Heading",
            background=UI_TILE,
            foreground=UI_TEXT,
            borderwidth=0,
            relief="flat",
            font=("Segoe UI", 8, "bold"),
        )
        style.map(
            "Arena.Treeview",
            background=[("selected", "#213149")],
            foreground=[("selected", UI_TEXT)],
        )
        style.map(
            "Arena.Treeview.Heading",
            background=[("active", "#202C3C")],
        )

        # Every live variable used by refresh() exists whether it is visible
        # on the main dashboard or in a secondary view.
        for key in (
            "status", "auto", "next", "arena_time", "rank", "points",
            "matches", "wins", "losses", "wr", "streak", "bestw", "net",
            "mph", "pph", "avg", "master_left", "master_est", "projected",
            "elapsed", "vision_mode", "vision_fps", "frame_age",
            "recognition_ms", "reaction_ms", "tap_mode", "dodges",
            "played_losses", "dodge_losses", "owl_score", "owl_sample",
            "time_saved"
        ):
            if key not in self.vars:
                self._var(key)

        self.ocr_live_var = tk.StringVar(value="")
        self.ocr_var = tk.StringVar(value="")
        self.device_var = tk.StringVar(value="ADB NOT STARTED")
        self.device_detail_var = tk.StringVar(value="Wireless ADB")
        self.version_var = tk.StringVar(value=f"v{APP_VERSION}")
        self.update_status_var = tk.StringVar(value="Up to date")
        self.master_progress_text = tk.StringVar(value="Waiting for score…")
        self.intel_hint_var = tk.StringVar(value="Opponent model learning…")
        self.last10_var = tk.StringVar(value="No history yet")
        self.opponent_identity_var = tk.StringVar(value="ORG detector not calibrated")
        self.history_page = None
        self.history_vars = {}
        self.intelligence_page = None
        self.intelligence_vars = {}
        self.strategy_page = None
        self.strategy_vars = {}
        self.diagnostics_page = None
        self.health_vars = {}
        self.daily_page = None
        self.daily_module_vars = {}
        self.daily_runner_thread = None
        self.daily_stop_event = threading.Event()
        self.daily_active_module = None
        self.daily_dry_run = False
        self.daily_deadline = 0.0
        self.daily_debug_var = tk.StringVar(value="Debug idle")
        # Normal Daily runs no longer write before/after PNGs for every tap.
        # That field-debug behavior was useful in 7.0.7 but adds avoidable I/O
        # latency. DRY RUN still captures evidence automatically.
        self.daily_debug_capture = False
        self.daily_summary_var = tk.StringVar(value="No Daily run yet")
        self.daily_last_results = {}
        self.daily_run_all_active = False
        # V7.1.1: Daily Assistant owns a low-latency screen stream + persistent
        # tap shell while Arena grinding is stopped. This avoids multi-second
        # adb screencap/process startup on every Daily action.
        self.daily_vision = None
        self.daily_tap_shell = None
        self.daily_transport_device = None
        # V7.2 Vision Inspector / shared visual understanding state.
        self.vision_page = None
        self.vision_vars = {}
        self.vision_live = False
        self.vision_live_job = None
        self.vision_scan_thread = None
        self.vision_preview_photo = None
        self.vision_preview_label = None
        self.vision_actions_text = None
        self.vision_last_result = None
        self.vision_analysis_cache = None
        self.health_overall_var = tk.StringVar(value="SYSTEM IDLE")
        self.health_detail_var = tk.StringVar(value="Self-healing ready")
        self.battle_hud_var = tk.StringVar(value="Waiting for opponent…")
        self.goal_var = tk.StringVar(value=goal_status().get("text", "No active goal"))
        self._toast_marks = set()
        self._last_health_toast_at = 0.0
        self._last_arena_notice_key = None
        self._last_intel_refresh = 0.0
        self._last_history_refresh = 0.0

        cfg = get_dodge_settings()
        self.dodge_enabled_var = tk.BooleanVar(value=bool(cfg.get("enabled", False)))
        self.dodge_owl_var = tk.BooleanVar(value=bool(cfg.get("dodge_owl", True)))
        self.dodge_master_var = tk.BooleanVar(value=bool(cfg.get("disable_at_master_plus", True)))
        self.dodge_threshold_var = tk.StringVar(value=f"{float(cfg.get('owl_threshold', 0.74)):.2f}")
        self.dodge_calibration_var = tk.StringVar(value="")
        self.dodge_short_var = tk.StringVar(value="OWL 0/3  •  QUIT —  •  CONFIRM —")
        self.dodge_state_var = tk.StringVar(value="ACTIVE" if self.dodge_enabled_var.get() else "OFF")

        # ==========================================================
        # CUSTOM TITLE BAR (replaces native white Windows caption)
        # ==========================================================
        chrome = tk.Frame(
            self.root,
            bg=UI_BG,
            height=36,
            highlightbackground=UI_BORDER,
            highlightthickness=0,
            bd=0,
        )
        chrome.pack(side="top", fill="x")
        chrome.pack_propagate(False)

        chrome_left = tk.Frame(chrome, bg=UI_BG)
        chrome_left.pack(side="left", fill="y", padx=(14, 0))
        chrome_mark = tk.Label(
            chrome_left, text="◇", bg=UI_BG, fg=UI_ACCENT,
            font=("Segoe UI Symbol", 10, "bold"), bd=0
        )
        chrome_mark.pack(side="left", pady=7)
        chrome_title = tk.Label(
            chrome_left, text="TG:BTC Game Assistant", bg=UI_BG, fg=UI_MUTED,
            font=("Segoe UI", 9, "normal"), bd=0
        )
        chrome_title.pack(side="left", padx=(7, 0), pady=7)
        chrome_version = tk.Label(
            chrome_left, text=f"v{APP_VERSION}", bg=UI_BG, fg=UI_MUTED_2,
            font=("Segoe UI", 8, "normal"), bd=0
        )
        chrome_version.pack(side="left", padx=(8, 0), pady=7)

        chrome_right = tk.Frame(chrome, bg=UI_BG)
        chrome_right.pack(side="right", fill="y")
        self.chrome_min_btn = self._chrome_button(chrome_right, "—", self._minimize_window)
        self.chrome_min_btn.pack(side="left", fill="y", ipadx=11)
        self.chrome_max_btn = self._chrome_button(chrome_right, "□", self._toggle_maximize)
        self.chrome_max_btn.pack(side="left", fill="y", ipadx=11)
        self.chrome_close_btn = self._chrome_button(chrome_right, "✕", self.close_window, close=True)
        self.chrome_close_btn.pack(side="left", fill="y", ipadx=11)

        # Drag from all non-button title-bar surfaces; double-click toggles
        # maximize just like a normal Windows caption.
        for drag_widget in (chrome, chrome_left, chrome_mark, chrome_title, chrome_version):
            drag_widget.bind("<ButtonPress-1>", self._title_press)
            drag_widget.bind("<B1-Motion>", self._title_drag)
            drag_widget.bind("<Double-Button-1>", self._toggle_maximize)

        divider = tk.Frame(self.root, bg=UI_BORDER, height=1)
        divider.pack(side="top", fill="x")

        shell = tk.Frame(self.root, bg=UI_BG)
        shell.pack(fill="both", expand=True)
        shell.grid_rowconfigure(0, weight=1)
        shell.grid_columnconfigure(1, weight=1)
        self.shell = shell

        # ==========================================================
        # SIDEBAR
        # ==========================================================
        sidebar = tk.Frame(shell, bg=UI_SIDEBAR, width=214)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(2, weight=1)

        brand = tk.Frame(sidebar, bg=UI_SIDEBAR)
        brand.grid(row=0, column=0, sticky="ew", padx=18, pady=(22, 22))
        self._label(brand, "TG:BTC", fg=UI_TEXT, bg=UI_SIDEBAR, size=16, weight="bold").pack(anchor="w")
        self._label(brand, "GAME ASSISTANT", fg=UI_ACCENT, bg=UI_SIDEBAR, size=8, weight="bold").pack(anchor="w", pady=(1, 0))

        nav = tk.Frame(sidebar, bg=UI_SIDEBAR)
        nav.grid(row=1, column=0, sticky="new", padx=18)
        self.nav_buttons = {}
        self.nav_buttons["dashboard"] = self._nav_button(nav, "Dashboard", "◇", self.show_dashboard, active=True)
        self.nav_buttons["dashboard"].pack(fill="x", pady=(0, 8))
        self.nav_buttons["daily"] = self._nav_button(nav, "Daily Assistant", "✓", self.open_daily_assistant)
        self.nav_buttons["daily"].pack(fill="x", pady=(0, 8))
        self.nav_buttons["vision"] = self._nav_button(nav, "Vision", "◉", self.open_vision_inspector)
        self.nav_buttons["vision"].pack(fill="x", pady=(0, 8))
        self.nav_buttons["intelligence"] = self._nav_button(nav, "Intelligence", "◎", self.open_intelligence)
        self.nav_buttons["intelligence"].pack(fill="x", pady=2)
        self.nav_buttons["history"] = self._nav_button(nav, "History", "▤", self.open_history)
        self.nav_buttons["history"].pack(fill="x", pady=2)
        self.nav_buttons["dodge"] = self._nav_button(nav, "Smart Dodge", "◇", self.open_dodge_calibration)
        self.nav_buttons["dodge"].pack(fill="x", pady=2)
        self.nav_buttons["strategy"] = self._nav_button(nav, "Strategy", "⚔", self.open_strategy)
        self.nav_buttons["strategy"].pack(fill="x", pady=2)
        self.nav_buttons["diagnostics"] = self._nav_button(nav, "Diagnostics", "⌁", self.toggle_diagnostics)
        self.nav_buttons["diagnostics"].pack(fill="x", pady=2)
        self.nav_buttons["settings"] = self._nav_button(nav, "Settings", "⚙", self.open_settings)
        self.nav_buttons["settings"].pack(fill="x", pady=2)

        adb_card = tk.Frame(sidebar, bg=UI_TILE, bd=0)
        adb_card.grid(row=3, column=0, sticky="sew", padx=18, pady=20)
        adb_top = tk.Frame(adb_card, bg=UI_TILE)
        adb_top.pack(fill="x", padx=12, pady=(11, 2))
        self.adb_health_dot = tk.Label(adb_top, text="●", bg=UI_TILE, fg=UI_MUTED, font=("Segoe UI", 10, "bold"))
        self.adb_health_dot.pack(side="left")
        self._label(adb_top, textvariable=self.device_var, fg=UI_GREEN, bg=UI_TILE, size=8, weight="bold").pack(side="left", padx=(5, 0))
        self._label(adb_card, textvariable=self.device_detail_var, fg=UI_MUTED, bg=UI_TILE, size=8).pack(anchor="w", padx=12, pady=(0, 11))

        # ==========================================================
        # MAIN DASHBOARD
        # ==========================================================
        main = tk.Frame(shell, bg=UI_BG)
        main.grid(row=0, column=1, sticky="nsew", padx=(26, 26), pady=(18, 18))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(4, weight=1)
        self.dashboard_main = main

        # Header
        header = tk.Frame(main, bg=UI_BG)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        header.grid_columnconfigure(0, weight=1)

        hleft = tk.Frame(header, bg=UI_BG)
        hleft.grid(row=0, column=0, sticky="w")
        self._label(hleft, "Arena Dashboard", fg=UI_TEXT, bg=UI_BG, size=18, weight="bold").pack(anchor="w")
        self._label(
            hleft,
            "Opponent scanner  •  decision engine  •  strategy  •  self-healing",
            fg=UI_MUTED,
            bg=UI_BG,
            size=9,
        ).pack(anchor="w", pady=(2, 0))

        hright = tk.Frame(header, bg=UI_BG)
        hright.grid(row=0, column=1, sticky="e")
        self.health_button = tk.Button(
            hright,
            textvariable=self.health_overall_var,
            command=self.toggle_diagnostics,
            bg=UI_GREEN_DARK,
            fg=UI_GREEN,
            activebackground="#174A3D",
            activeforeground=UI_GREEN,
            relief="flat",
            bd=0,
            highlightthickness=0,
            cursor="hand2",
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=5,
        )
        self.health_button.pack(side="left", padx=(0, 8))
        self.goal_button = tk.Button(
            hright, textvariable=self.goal_var, command=self.open_strategy,
            bg=UI_TILE, fg=UI_GOLD, activebackground="#243044", activeforeground=UI_GOLD,
            relief="flat", bd=0, highlightthickness=0, cursor="hand2",
            font=("Segoe UI", 8, "bold"), padx=9, pady=5,
        )
        self.goal_button.pack(side="left", padx=(0, 10))
        self._pill(hright, f"v{APP_VERSION}", fg=UI_MUTED, bg=UI_TILE).pack(side="left", padx=(0, 10))

        self.update_wrap = tk.Frame(hright, bg=UI_BG, width=42, height=36)
        self.update_wrap.pack(side="left")
        self.update_wrap.pack_propagate(False)
        self.update_btn = tk.Button(
            self.update_wrap,
            text="↓",
            command=self.on_update_icon,
            bg=UI_BLUE_DARK,
            fg=UI_BLUE,
            activebackground="#1B3560",
            activeforeground="#BBD3FF",
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground="#31517D",
            cursor="hand2",
            font=("Segoe UI Symbol", 12, "bold"),
        )
        self.update_btn.place(x=0, y=0, width=38, height=34)
        self.update_badge = tk.Label(
            self.update_wrap,
            text="1",
            bg=UI_ACCENT,
            fg="white",
            font=("Segoe UI", 7, "bold"),
            padx=4,
            pady=1,
            bd=0,
        )
        self.update_badge.place(relx=1.0, x=0, y=-2, anchor="ne")
        self.update_badge.place_forget()

        # ----------------------------------------------------------
        # TOP CARDS: Live / Rank / Session
        # ----------------------------------------------------------
        top_cards = tk.Frame(main, bg=UI_BG)
        top_cards.grid(row=1, column=0, sticky="ew")
        for c in range(3):
            top_cards.grid_columnconfigure(c, weight=1, uniform="topcards")

        live_card, live = self._make_card(top_cards)
        live_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._label(live, "LIVE STATUS", fg=UI_MUTED, size=8).pack(anchor="w")
        self._label(live, textvariable=self.vars["status"], size=18, weight="bold").pack(anchor="w", pady=(7, 7))
        chips = tk.Frame(live, bg=UI_CARD)
        chips.pack(fill="x")
        tk.Label(chips, text="●", bg=UI_CARD, fg=UI_GREEN, font=("Segoe UI", 9, "bold")).pack(side="left")
        self._label(chips, textvariable=self.vars["auto"], fg=UI_GREEN, size=8, weight="bold").pack(side="left", padx=(3, 12))
        self._label(chips, "Next:", fg=UI_MUTED_2, size=8).pack(side="left")
        self._label(chips, textvariable=self.vars["next"], fg=UI_MUTED, size=8).pack(side="left", padx=(4, 0))
        self._label(live, textvariable=self.vars["arena_time"], fg=UI_GOLD, size=8).pack(anchor="w", pady=(8, 0))
        self._label(live, textvariable=self.intel_hint_var, fg=UI_BLUE, size=7).pack(anchor="w", pady=(4, 0))
        hud = tk.Frame(live, bg=UI_TILE)
        hud.pack(fill="x", pady=(7, 0))
        self._label(hud, "BATTLE INTEL", bg=UI_TILE, fg=UI_MUTED, size=7, weight="bold").pack(side="left", padx=(8, 6), pady=5)
        self._label(hud, textvariable=self.battle_hud_var, bg=UI_TILE, fg=UI_TEXT, size=7, weight="bold").pack(side="left", pady=5)

        rank_card, rank = self._make_card(top_cards)
        rank_card.grid(row=0, column=1, sticky="nsew", padx=6)
        rank_head = tk.Frame(rank, bg=UI_CARD)
        rank_head.pack(fill="x")
        left_rank = tk.Frame(rank_head, bg=UI_CARD)
        left_rank.pack(side="left")
        self._label(left_rank, "RANK", fg=UI_MUTED, size=8).pack(anchor="w")
        self._label(left_rank, textvariable=self.vars["rank"], fg=UI_GOLD, size=16, weight="bold").pack(anchor="w", pady=(4, 0))
        points_box = tk.Frame(rank_head, bg=UI_CARD)
        points_box.pack(side="right")
        self._label(points_box, textvariable=self.vars["points"], size=10, weight="bold", anchor="e").pack(side="left")
        self._label(points_box, " pts", fg=UI_MUTED, size=9, anchor="e").pack(side="left")
        self.master_progress_bar = ttk.Progressbar(
            rank,
            orient="horizontal",
            mode="determinate",
            maximum=MASTER_V_POINTS,
            style="Arena.Horizontal.TProgressbar",
        )
        self.master_progress_bar.pack(fill="x", pady=(10, 8))
        self._label(rank, textvariable=self.master_progress_text, fg=UI_MUTED, size=8).pack(anchor="w")

        session_card, ses = self._make_card(top_cards)
        session_card.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        self._label(ses, "SESSION", fg=UI_MUTED, size=8).pack(anchor="w")
        ses_main = tk.Frame(ses, bg=UI_CARD)
        ses_main.pack(fill="x", pady=(7, 6))
        self._label(ses_main, textvariable=self.vars["matches"], size=13, weight="bold").pack(side="left")
        self._label(ses_main, " matches", size=11, weight="bold").pack(side="left")
        self._label(ses_main, textvariable=self.vars["wins"], fg=UI_GREEN, size=10, weight="bold").pack(side="left", padx=(20, 2))
        self._label(ses_main, "W", fg=UI_GREEN, size=9, weight="bold").pack(side="left")
        self._label(ses_main, textvariable=self.vars["losses"], fg=UI_RED, size=10, weight="bold").pack(side="left", padx=(10, 2))
        self._label(ses_main, "L", fg=UI_RED, size=9, weight="bold").pack(side="left")
        ses_sub = tk.Frame(ses, bg=UI_CARD)
        ses_sub.pack(fill="x")
        self._label(ses_sub, textvariable=self.vars["wr"], fg=UI_MUTED, size=8).pack(side="left")
        self._label(ses_sub, " win rate", fg=UI_MUTED, size=8).pack(side="left")
        self._label(ses_sub, textvariable=self.vars["streak"], fg=UI_MUTED, size=8).pack(side="left", padx=(18, 0))
        ses_bottom = tk.Frame(ses, bg=UI_CARD)
        ses_bottom.pack(fill="x", pady=(8, 0))
        self._label(ses_bottom, textvariable=self.vars["net"], fg=UI_BLUE, size=8, weight="bold").pack(side="left")
        self._label(ses_bottom, " net  •  ", fg=UI_MUTED, size=8).pack(side="left")
        self._label(ses_bottom, textvariable=self.vars["pph"], fg=UI_BLUE, size=8, weight="bold").pack(side="left")
        self._label(ses_bottom, " pts/hr", fg=UI_MUTED, size=8).pack(side="left")
        self._label(ses, textvariable=self.last10_var, fg=UI_MUTED_2, size=7).pack(anchor="w", pady=(5, 0))

        # ----------------------------------------------------------
        # SMART DODGE + PERFORMANCE
        # ----------------------------------------------------------
        middle = tk.Frame(main, bg=UI_BG)
        middle.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        middle.grid_columnconfigure(0, weight=4)
        middle.grid_columnconfigure(1, weight=6)

        dodge_card, dodge = self._make_card(middle)
        dodge_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        dodge_title = tk.Frame(dodge, bg=UI_CARD)
        dodge_title.pack(fill="x")
        left = tk.Frame(dodge_title, bg=UI_CARD)
        left.pack(side="left")
        self._label(left, "Smart Dodge", size=11, weight="bold").pack(anchor="w")
        self._label(left, "Opponent-aware early surrender", fg=UI_MUTED, size=8).pack(anchor="w", pady=(2, 0))
        dodge_right = tk.Frame(dodge_title, bg=UI_CARD)
        dodge_right.pack(side="right", anchor="n")
        self.dodge_active_badge = self._pill(
            dodge_right,
            self.dodge_state_var.get(),
            fg=UI_GREEN if self.dodge_enabled_var.get() else UI_MUTED,
            bg=UI_GREEN_DARK if self.dodge_enabled_var.get() else UI_TILE,
        )
        self.dodge_active_badge.pack(side="left", padx=(0, 8))
        self.dodge_master_switch = ToggleSwitch(
            dodge_right,
            self.dodge_enabled_var,
            self.save_dodge_ui,
            bg=UI_CARD,
            on_color=UI_GREEN,
        )
        self.dodge_master_switch.pack(side="left")

        row1 = tk.Frame(dodge, bg=UI_CARD)
        row1.pack(fill="x", pady=(12, 5))
        text1 = tk.Frame(row1, bg=UI_CARD)
        text1.pack(side="left", fill="x", expand=True)
        self._label(text1, "Dodge Owl of Readiness", size=9, weight="bold").pack(anchor="w")
        self._label(text1, text=f"2-frame confirmation  •  threshold {self.dodge_threshold_var.get()}", fg=UI_MUTED, size=8).pack(anchor="w", pady=(1, 0))
        ToggleSwitch(row1, self.dodge_owl_var, self.save_dodge_ui, bg=UI_CARD).pack(side="right")

        row2 = tk.Frame(dodge, bg=UI_CARD)
        row2.pack(fill="x", pady=5)
        text2 = tk.Frame(row2, bg=UI_CARD)
        text2.pack(side="left", fill="x", expand=True)
        self._label(text2, "Disable at Master+", size=9, weight="bold").pack(anchor="w")
        self._label(text2, "Preserve real-weak-bot opportunities", fg=UI_MUTED, size=8).pack(anchor="w", pady=(1, 0))
        ToggleSwitch(row2, self.dodge_master_var, self.save_dodge_ui, bg=UI_CARD).pack(side="right")

        dodge_bottom = tk.Frame(dodge, bg=UI_CARD)
        dodge_bottom.pack(fill="x", pady=(9, 0))
        self._pill(dodge_bottom, "OWL", fg=UI_MUTED, bg=UI_TILE).pack(side="left")
        self._pill(dodge_bottom, "QUIT ✓", fg=UI_GREEN, bg=UI_GREEN_DARK).pack(side="left", padx=(6, 0))
        self._pill(dodge_bottom, "CONFIRM ✓", fg=UI_GREEN, bg=UI_GREEN_DARK).pack(side="left", padx=(6, 0))
        self._action_button(dodge_bottom, "CALIBRATE", self.open_dodge_calibration).pack(side="right")

        perf_card, perf = self._make_card(middle)
        perf_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        perf_head = tk.Frame(perf, bg=UI_CARD)
        perf_head.pack(fill="x", pady=(0, 10))
        self._label(perf_head, "Performance", size=11, weight="bold").pack(side="left")
        self._pill(perf_head, "LIVE", fg=UI_BLUE, bg=UI_BLUE_DARK).pack(side="left", padx=(8, 0))

        metrics = tk.Frame(perf, bg=UI_CARD)
        metrics.pack(fill="both", expand=True)
        for c in range(4):
            metrics.grid_columnconfigure(c, weight=1, uniform="metric")
        specs = [
            ("Matches / hr", "mph", UI_TEXT),
            ("Points / hr", "pph", UI_GREEN),
            ("Vision FPS", "vision_fps", UI_BLUE),
            ("Frame age", "frame_age", UI_TEXT),
            ("Dodges", "dodges", UI_TEXT),
            ("Time saved", "time_saved", UI_GOLD),
            ("Owl score", "owl_score", UI_RED),
            ("Reaction", "reaction_ms", UI_TEXT),
        ]
        for i, (title, key, color) in enumerate(specs):
            tile = self._metric_tile(metrics, title, key, value_fg=color)
            tile.grid(row=i // 4, column=i % 4, sticky="nsew", padx=4, pady=4)

        # ----------------------------------------------------------
        # ACTIVITY
        # ----------------------------------------------------------
        activity_card, activity = self._make_card(main, padx=14, pady=12)
        activity_card.grid(row=3, column=0, sticky="nsew", pady=(16, 0))
        act_head = tk.Frame(activity, bg=UI_CARD)
        act_head.pack(fill="x", pady=(0, 7))
        self._label(act_head, "Activity", size=10, weight="bold").pack(side="left")
        self._pill(act_head, "STREAM HEALTHY", fg=UI_GREEN, bg=UI_GREEN_DARK).pack(side="left", padx=(8, 0))

        self.log = tk.Text(
            activity,
            height=7,
            wrap="word",
            state="disabled",
            bg=UI_CARD,
            fg=UI_MUTED,
            insertbackground=UI_TEXT,
            selectbackground="#274369",
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Consolas", 8),
            padx=0,
            pady=0,
        )
        self.log.pack(fill="both", expand=True)
        self.log.tag_configure("time", foreground=UI_MUTED_2)
        self.log.tag_configure("auto", foreground=UI_BLUE)
        self.log.tag_configure("rank", foreground=UI_GREEN)
        self.log.tag_configure("action", foreground=UI_GOLD)
        self.log.tag_configure("error", foreground=UI_RED)

        # Spacer row keeps control bar at the visual bottom when window grows.
        tk.Frame(main, bg=UI_BG, height=1).grid(row=4, column=0, sticky="nsew")

        controls = tk.Frame(main, bg=UI_BG)
        controls.grid(row=5, column=0, sticky="ew", pady=(16, 0))
        self.start_btn = self._action_button(controls, "START GRIND", self.start, accent=True)
        self.start_btn.pack(side="left")
        self.stop_btn = self._action_button(controls, "STOP", self.stop)
        self.stop_btn.pack(side="left", padx=(8, 0))
        self.stop_btn.config(state="disabled", disabledforeground="#657084")
        self._action_button(controls, "RESET SESSION", self.reset_session).pack(side="left", padx=(8, 0))

        self.tools_button = self._action_button(controls, "TOOLS  ⋯", self.show_tools_menu)
        self.tools_button.pack(side="right")
        self._label(controls, "Persistent shell", fg=UI_MUTED, size=8).pack(side="right", padx=(0, 10))
        self._pill(controls, "VISION STREAM", fg=UI_BLUE, bg=UI_BLUE_DARK).pack(side="right", padx=(0, 8))

        # Legacy compatibility fields used by older methods.
        self.diag_visible = False
        self.diag_window = None
        self.refresh_dodge_calibration_status()
        self.update_ocr_status()

        # Window chrome finishing touches happen after the dashboard exists.
        self.root.bind("<Map>", self._on_window_map, add="+")
        self.root.bind("<Alt-F4>", lambda e: self.close_window(), add="+")
        self.root.after(50, self._install_resize_edges)
        self.root.after(90, self._ensure_taskbar_presence)

    def show_tools_menu(self):
        menu = tk.Menu(
            self.root,
            tearoff=0,
            bg=UI_TILE,
            fg=UI_TEXT,
            activebackground=UI_ACCENT_DARK,
            activeforeground=UI_TEXT,
            bd=0,
            relief="flat",
            font=("Segoe UI", 9),
        )
        menu.add_command(label="Opponent Intelligence", command=self.open_intelligence)
        menu.add_command(label="Battle Strategy", command=self.open_strategy)
        menu.add_command(label="Smart Dodge Calibration", command=self.open_dodge_calibration)
        menu.add_command(label="Diagnostics", command=self.toggle_diagnostics)
        menu.add_command(label="History", command=self.open_history)
        menu.add_separator()
        menu.add_command(label="Set Rank / Points", command=self.set_rank_points_manual)
        menu.add_command(label="Test OCR", command=self.test_ocr)
        menu.add_command(label="Install OCR", command=self.install_ocr)
        menu.add_command(label="Install Fast Vision", command=self.install_fast_vision)
        menu.add_separator()
        menu.add_command(label="Check for Updates", command=self.check_updates_manual)
        menu.add_command(label="Open Profile Folder", command=self.open_profile)
        menu.add_command(label="Settings", command=self.open_settings)
        try:
            x = self.tools_button.winfo_rootx()
            y = self.tools_button.winfo_rooty() + self.tools_button.winfo_height()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def set_update_indicator(self, state="idle", latest=None):
        """Compact top-right update state from the V5.5 Figma concept."""
        if not hasattr(self, "update_btn"):
            return

        if state == "available":
            self.update_btn.config(
                text="↓",
                bg="#173B71",
                fg="#C7DAFF",
                activebackground="#214A84",
                activeforeground="white",
                highlightbackground="#426DA6",
            )
            self.update_badge.place(relx=1.0, x=0, y=-2, anchor="ne")
            self.update_status_var.set(
                f"Update v{latest} available" if latest else "Update available"
            )
        elif state == "checking":
            self.update_btn.config(
                text="↻",
                bg=UI_BLUE_DARK,
                fg=UI_BLUE,
                activebackground="#1B3560",
                activeforeground="#C7DAFF",
                highlightbackground="#31517D",
            )
            self.update_badge.place_forget()
            self.update_status_var.set("Checking for updates…")
        elif state == "error":
            self.update_btn.config(
                text="!",
                bg="#341A22",
                fg=UI_RED,
                activebackground="#44212C",
                activeforeground=UI_RED,
                highlightbackground="#68313E",
            )
            self.update_badge.place_forget()
            self.update_status_var.set("Update check failed")
        else:
            self.update_btn.config(
                text="↓",
                bg=UI_BLUE_DARK,
                fg=UI_BLUE,
                activebackground="#1B3560",
                activeforeground="#C7DAFF",
                highlightbackground="#31517D",
            )
            self.update_badge.place_forget()
            self.update_status_var.set("Up to date")

    def on_update_icon(self):
        release = getattr(self, "latest_release", None)
        if release and version_tuple(release.get("version")) > version_tuple(APP_VERSION):
            self.show_update_dialog(release)
        else:
            self._check_updates(manual=True)

    def show_update_dialog(self, release):
        latest = release["version"]
        notes = (release.get("notes") or "").strip()
        if len(notes) > 1800:
            notes = notes[:1800] + "\n…"

        message = (
            f"TG:BTC Game Assistant v{latest} is ready.\n\n"
            f"Installed: v{APP_VERSION}\n"
            f"Source: {release.get('name') or ('v' + latest)}\n\n"
        )
        if notes:
            message += f"What's new:\n{notes}\n\n"
        message += "Install this update now?"

        if messagebox.askyesno("Update Available", message):
            self._download_and_install_update(release)

    def _health_var(self, component, field="status", default="-"):
        key = f"{component}:{field}"
        var = self.health_vars.get(key)
        if var is None:
            var = tk.StringVar(value=default)
            self.health_vars[key] = var
        return var

    def _health_status_color(self, status):
        status = str(status or "").upper()
        if status in ("HEALTHY", "READY", "PAUSED"):
            return UI_GREEN
        if status in ("RECOVERING", "DEGRADED", "STALE", "CHECK", "NOT READY", "MISSING"):
            return UI_GOLD
        if status in ("ERROR", "FAILED"):
            return UI_RED
        return UI_MUTED

    def toggle_diagnostics(self):
        # V5.8: Diagnostics is now a first-class dark in-app page.
        if hasattr(self, "dashboard_main"):
            self.dashboard_main.grid_remove()
        if getattr(self, "history_page", None) is not None:
            try:
                self.history_page.grid_remove()
            except Exception:
                pass
        for other_name in ("intelligence_page", "strategy_page", "daily_page", "vision_page"):
            other = getattr(self, other_name, None)
            if other is not None:
                try: other.grid_remove()
                except Exception: pass

        if getattr(self, "diagnostics_page", None) is not None:
            try:
                self.diagnostics_page.destroy()
            except Exception:
                pass

        page = tk.Frame(self.shell, bg=UI_BG)
        page.grid(row=0, column=1, sticky="nsew", padx=(26, 26), pady=(18, 18))
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(3, weight=1)
        self.diagnostics_page = page
        self._set_active_nav("diagnostics")

        header = tk.Frame(page, bg=UI_BG)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.grid_columnconfigure(0, weight=1)
        left = tk.Frame(header, bg=UI_BG)
        left.grid(row=0, column=0, sticky="w")
        self._label(left, "System Diagnostics", bg=UI_BG, size=18, weight="bold").pack(anchor="w")
        self._label(
            left,
            "Live health  •  automatic recovery  •  no blind recovery taps",
            bg=UI_BG, fg=UI_MUTED, size=9,
        ).pack(anchor="w", pady=(2, 0))
        actions = tk.Frame(header, bg=UI_BG)
        actions.grid(row=0, column=1, sticky="e")
        self._action_button(actions, "RUN HEALTH CHECK", self.run_health_check).pack(side="left", padx=(0, 7))
        self._action_button(actions, "DASHBOARD", self.show_dashboard).pack(side="left")

        overall_card, overall = self._make_card(page, padx=16, pady=12)
        overall_card.grid(row=1, column=0, sticky="ew")
        top = tk.Frame(overall, bg=UI_CARD)
        top.pack(fill="x")
        self._label(top, "SELF-HEALING STATUS", fg=UI_MUTED, size=8).pack(side="left")
        self._pill(top, "AUTO-RECOVERY ON", fg=UI_GREEN, bg=UI_GREEN_DARK).pack(side="right")
        summary = tk.Frame(overall, bg=UI_CARD)
        summary.pack(fill="x", pady=(8, 0))
        self._label(summary, textvariable=self.health_overall_var, size=15, weight="bold").pack(side="left")
        self._label(summary, textvariable=self.health_detail_var, fg=UI_MUTED, size=8).pack(side="left", padx=(14, 0))

        components = tk.Frame(page, bg=UI_BG)
        components.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        for c in range(4):
            components.grid_columnconfigure(c, weight=1, uniform="health")
        specs = [
            ("ADB", "adb"),
            ("FAST VISION", "vision"),
            ("TAP SHELL", "tap"),
            ("OCR", "ocr"),
            ("TEMPLATES", "templates"),
            ("SMART DODGE", "dodge"),
            ("OPPONENT INTEL", "intel"),
            ("STRATEGY", "strategy"),
            ("ENGINE", "engine"),
        ]
        self.health_component_widgets = {}
        for i, (title, key) in enumerate(specs):
            outer, body = self._make_card(components, padx=12, pady=10)
            outer.grid(row=i // 4, column=i % 4, sticky="nsew", padx=(0 if i % 4 == 0 else 5, 0 if i % 4 == 3 else 5), pady=(0 if i < 4 else 10, 0))
            self._label(body, title, fg=UI_MUTED, size=7).pack(anchor="w")
            status_label = self._label(body, textvariable=self._health_var(key, "status"), size=10, weight="bold")
            status_label.pack(anchor="w", pady=(5, 0))
            self._label(body, textvariable=self._health_var(key, "detail"), fg=UI_MUTED, size=7, wraplength=220, justify="left").pack(anchor="w", pady=(3, 0))
            self.health_component_widgets[key] = status_label

        bottom = tk.Frame(page, bg=UI_BG)
        bottom.grid(row=3, column=0, sticky="nsew", pady=(14, 0))
        bottom.grid_columnconfigure(0, weight=6)
        bottom.grid_columnconfigure(1, weight=4)
        bottom.grid_rowconfigure(0, weight=1)

        events_card, events = self._make_card(bottom, padx=12, pady=10)
        events_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._label(events, "Recovery Activity", size=10, weight="bold").pack(anchor="w")
        self.health_event_text = tk.Text(
            events, height=10, bg=UI_CARD, fg=UI_MUTED, insertbackground=UI_TEXT,
            relief="flat", bd=0, highlightthickness=0, font=("Consolas", 8), wrap="word",
        )
        self.health_event_text.pack(fill="both", expand=True, pady=(7, 0))
        self.health_event_text.config(state="disabled")

        recovery_card, recovery = self._make_card(bottom, padx=14, pady=10)
        recovery_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self._label(recovery, "Manual Recovery", size=10, weight="bold").pack(anchor="w")
        self._label(recovery, "The watchdog already does these automatically. These controls are safe manual retries.", fg=UI_MUTED, size=7, wraplength=310, justify="left").pack(anchor="w", pady=(4, 9))
        self._action_button(recovery, "RECONNECT ADB", self.recover_adb).pack(fill="x", pady=3)
        self._action_button(recovery, "RESTART VISION", self.recover_vision).pack(fill="x", pady=3)
        self._action_button(recovery, "RESTART TAP SHELL", self.recover_tap_shell).pack(fill="x", pady=3)
        self._label(recovery, textvariable=self._health_var("recovery", "last"), fg=UI_GOLD, size=7, wraplength=310, justify="left").pack(anchor="w", pady=(10, 0))

        self.refresh_diagnostics_page()

    def run_health_check(self):
        if not self.engine.running:
            messagebox.showinfo("Health Check", "Start the grinder first so ADB, Vision and Tap Shell can be checked live.")
            return
        self.engine.request_health_check()
        self.add_log("Manual health check requested")
        self.root.after(1200, self.refresh_diagnostics_page)

    def recover_adb(self):
        if not self.engine.running:
            messagebox.showinfo("ADB Recovery", "Start the grinder first.")
            return
        self.engine.recover_adb_manual()

    def recover_vision(self):
        if not self.engine.running:
            messagebox.showinfo("Vision Recovery", "Start the grinder first.")
            return
        self.engine.recover_vision_manual()

    def recover_tap_shell(self):
        if not self.engine.running:
            messagebox.showinfo("Tap Shell Recovery", "Start the grinder first.")
            return
        self.engine.recover_tap_manual()

    def refresh_diagnostics_page(self):
        snap = self.engine.health_snapshot()
        comps = snap.get("components", {})
        for key, data in comps.items():
            self._health_var(key, "status").set(str(data.get("status") or "?"))
            detail = str(data.get("detail") or "")
            latency = data.get("latency_ms")
            if latency is not None and key == "adb" and "ms" not in detail:
                detail = f"{detail} • {latency} ms"
            self._health_var(key, "detail").set(detail or "-")
            widget = getattr(self, "health_component_widgets", {}).get(key)
            if widget is not None:
                widget.config(fg=self._health_status_color(data.get("status")))

        self._health_var("recovery", "last").set(
            f"Recoveries: {snap.get('recovery_count', 0)}\nLast: {snap.get('last_recovery') or 'None yet'}"
        )

        text = getattr(self, "health_event_text", None)
        if text is not None:
            events = load_recent_health_events(60)
            lines = []
            for row in reversed(events[-30:]):
                stamp = str(row.get("timestamp") or "")[-8:]
                component = str(row.get("component") or "?")
                status = str(row.get("status") or "?")
                detail = str(row.get("detail") or "")
                lines.append(f"{stamp}  {component:<12} {status:<10} {detail}")
            text.config(state="normal")
            text.delete("1.0", "end")
            text.insert("1.0", "\n".join(lines) if lines else "No recovery events yet. The watchdog is standing by.")
            text.config(state="disabled")

    def _history_var(self, name, default="-"):
        var = self.history_vars.get(name)
        if var is None:
            var = tk.StringVar(value=default)
            self.history_vars[name] = var
        return var

    def _refresh_intel_dashboard(self):
        try:
            records = load_intel_history()
            self.intel_hint_var.set(opponent_intel_text(records))
            self.opponent_identity_var.set(opponent_identity_summary(records))
            self.last10_var.set(last_ten_summary(records))
        except Exception:
            self.intel_hint_var.set("Opponent model learning…")

    def open_history(self):
        # V5.7 History is a real in-app page, not another bright native popup.
        if hasattr(self, "dashboard_main"):
            self.dashboard_main.grid_remove()
        if getattr(self, "diagnostics_page", None) is not None:
            try:
                self.diagnostics_page.grid_remove()
            except Exception:
                pass
        for other_name in ("intelligence_page", "strategy_page", "daily_page", "vision_page"):
            other = getattr(self, other_name, None)
            if other is not None:
                try: other.grid_remove()
                except Exception: pass

        if getattr(self, "history_page", None) is not None:
            try:
                self.history_page.destroy()
            except Exception:
                pass

        page = tk.Frame(self.shell, bg=UI_BG)
        page.grid(row=0, column=1, sticky="nsew", padx=(26, 26), pady=(18, 18))
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(4, weight=1)
        self.history_page = page
        self._set_active_nav("history")
        self.history_vars = {}

        # ------------------------------------------------------
        # Header
        # ------------------------------------------------------
        header = tk.Frame(page, bg=UI_BG)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.grid_columnconfigure(0, weight=1)
        left = tk.Frame(header, bg=UI_BG)
        left.grid(row=0, column=0, sticky="w")
        self._label(left, "Arena History", bg=UI_BG, size=18, weight="bold").pack(anchor="w")
        self._label(
            left,
            "Persistent match history  •  opponent intelligence  •  rank journey",
            bg=UI_BG,
            fg=UI_MUTED,
            size=9,
        ).pack(anchor="w", pady=(2, 0))
        header_actions = tk.Frame(header, bg=UI_BG)
        header_actions.grid(row=0, column=1, sticky="e")
        self._action_button(header_actions, "CALIBRATE USER", self.capture_opponent_username_roi).pack(side="left", padx=(0, 7))
        self._action_button(header_actions, "CALIBRATE ORG", self.capture_opponent_org_roi).pack(side="left", padx=(0, 7))
        self._action_button(header_actions, "INTEL", self.open_intelligence).pack(side="left", padx=(0, 7))
        self._action_button(header_actions, "DASHBOARD", self.show_dashboard).pack(side="left")

        # ------------------------------------------------------
        # Persistent summary cards
        # ------------------------------------------------------
        summaries = tk.Frame(page, bg=UI_BG)
        summaries.grid(row=1, column=0, sticky="ew")
        for c in range(4):
            summaries.grid_columnconfigure(c, weight=1, uniform="historySummary")

        cards = [
            ("PERSISTENT MATCHES", "persistent_matches", UI_TEXT),
            ("RECENT FORM", "recent_form", UI_GREEN),
            ("TRACKED NET", "persistent_net", UI_BLUE),
            ("CURRENT RANK", "history_rank", UI_GOLD),
        ]
        for i, (title, key, color) in enumerate(cards):
            outer, body = self._make_card(summaries, padx=12, pady=10)
            outer.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 5, 0 if i == 3 else 5))
            self._label(body, title, fg=UI_MUTED, size=7).pack(anchor="w")
            self._label(body, textvariable=self._history_var(key), fg=color, size=12, weight="bold").pack(anchor="w", pady=(5, 0))

        # ------------------------------------------------------
        # Opponent intelligence
        # ------------------------------------------------------
        intel_card, intel = self._make_card(page, padx=14, pady=12)
        intel_card.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        intel_head = tk.Frame(intel, bg=UI_CARD)
        intel_head.pack(fill="x", pady=(0, 9))
        self._label(intel_head, "Opponent Intelligence", size=11, weight="bold").pack(side="left")
        self._pill(intel_head, "LEARNING", fg=UI_BLUE, bg=UI_BLUE_DARK).pack(side="left", padx=(8, 0))
        self._label(
            intel_head,
            textvariable=self._history_var("prediction"),
            fg=UI_BLUE,
            size=8,
            weight="bold",
        ).pack(side="right")
        self._label(
            intel,
            textvariable=self._history_var("identity_status"),
            fg=UI_GREEN,
            size=8,
            weight="bold",
        ).pack(anchor="w", pady=(0, 9))

        buckets = tk.Frame(intel, bg=UI_CARD)
        buckets.pack(fill="x")
        for c in range(3):
            buckets.grid_columnconfigure(c, weight=1, uniform="intelBuckets")
        for i, (name, key) in enumerate((
            ("REAL OPPONENT", "real_stats"),
            ("STRONG BOT", "strong_stats"),
            ("WEAK BOT", "weak_stats"),
        )):
            tile = tk.Frame(buckets, bg=UI_TILE, padx=12, pady=9)
            tile.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 5, 0 if i == 2 else 5))
            self._label(tile, name, bg=UI_TILE, fg=UI_MUTED, size=7).pack(anchor="w")
            self._label(tile, textvariable=self._history_var(key), bg=UI_TILE, size=9, weight="bold").pack(anchor="w", pady=(4, 0))

        # ------------------------------------------------------
        # Rank journey + Smart Dodge intelligence
        # ------------------------------------------------------
        insight_row = tk.Frame(page, bg=UI_BG)
        insight_row.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        insight_row.grid_columnconfigure(0, weight=6)
        insight_row.grid_columnconfigure(1, weight=4)

        chart_card, chart_body = self._make_card(insight_row, padx=14, pady=10)
        chart_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ch = tk.Frame(chart_body, bg=UI_CARD)
        ch.pack(fill="x", pady=(0, 5))
        self._label(ch, "Rank & Points Journey", size=10, weight="bold").pack(side="left")
        self._label(ch, textvariable=self._history_var("journey"), fg=UI_MUTED, size=7).pack(side="right")
        self.history_chart = tk.Canvas(
            chart_body,
            height=86,
            bg=UI_CARD,
            highlightthickness=0,
            bd=0,
        )
        self.history_chart.pack(fill="x", expand=True)

        dodge_card, dodge_body = self._make_card(insight_row, padx=14, pady=10)
        dodge_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self._label(dodge_body, "Smart Dodge Intel", size=10, weight="bold").pack(anchor="w")
        self._label(dodge_body, textvariable=self._history_var("dodge_summary"), fg=UI_GREEN, size=8).pack(anchor="w", pady=(7, 0))
        self._label(dodge_body, textvariable=self._history_var("owl_summary"), fg=UI_RED, size=8).pack(anchor="w", pady=(4, 0))
        self._label(dodge_body, textvariable=self._history_var("time_summary"), fg=UI_GOLD, size=8).pack(anchor="w", pady=(4, 0))

        # ------------------------------------------------------
        # Match table
        # ------------------------------------------------------
        table_card, table_body = self._make_card(page, padx=10, pady=9)
        table_card.grid(row=4, column=0, sticky="nsew", pady=(14, 0))
        table_body.grid_rowconfigure(1, weight=1)
        table_body.grid_columnconfigure(0, weight=1)
        table_head = tk.Frame(table_body, bg=UI_CARD)
        table_head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 7))
        self._label(table_head, "Matches", size=10, weight="bold").pack(side="left")
        self._label(table_head, "Newest first  •  OCR-enriched after each result", fg=UI_MUTED, size=7).pack(side="left", padx=(10, 0))
        self._action_button(table_head, "REFRESH", self.refresh_history_page).pack(side="right")

        columns = ("time", "match", "result", "opponent", "type", "queue", "heroes", "threat", "decision", "rank", "points", "delta", "mode", "duration")
        tree = ttk.Treeview(
            table_body,
            columns=columns,
            show="headings",
            style="Arena.Treeview",
            height=8,
        )
        self.history_tree = tree
        headings = {
            "time": "TIME", "match": "#", "result": "RESULT", "opponent": "OPPONENT", "type": "TYPE", "queue": "QUEUE",
            "heroes": "HEROES", "threat": "THREAT", "decision": "DECISION", "rank": "RANK", "points": "PTS", "delta": "Δ", "mode": "MODE", "duration": "TIME",
        }
        widths = {
            "time": 112, "match": 42, "result": 64, "opponent": 110, "type": 62, "queue": 102,
            "heroes": 160, "threat": 80, "decision": 80, "rank": 94, "points": 60, "delta": 52, "mode": 70, "duration": 66,
        }
        for col in columns:
            tree.heading(col, text=headings[col])
            tree.column(col, width=widths[col], minwidth=35, anchor="w", stretch=(col in ("opponent", "heroes", "queue", "rank")))
        tree.tag_configure("win", foreground=UI_GREEN)
        tree.tag_configure("loss", foreground=UI_RED)
        tree.tag_configure("dodge", foreground=UI_GOLD)
        scroll = ttk.Scrollbar(table_body, orient="vertical", command=tree.yview)
        hscroll = ttk.Scrollbar(table_body, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=scroll.set, xscrollcommand=hscroll.set)
        tree.grid(row=1, column=0, sticky="nsew")
        scroll.grid(row=1, column=1, sticky="ns")
        hscroll.grid(row=2, column=0, sticky="ew")
        tree.bind("<Double-1>", lambda e: self.open_selected_snapshot())

        self.refresh_history_page()

    def _draw_history_chart(self, records):
        canvas = getattr(self, "history_chart", None)
        if canvas is None:
            return
        canvas.delete("all")
        series = history_point_series(records)
        w = max(20, canvas.winfo_width())
        h = max(50, int(canvas.cget("height")))
        pad_x, pad_y = 10, 10

        if not series:
            canvas.create_text(
                10, h // 2,
                anchor="w",
                text="Points will appear here as OCR records results.",
                fill=UI_MUTED_2,
                font=("Segoe UI", 8),
            )
            return

        points = [p for _, p in series[-60:]]
        lo, hi = min(points), max(points)
        if hi == lo:
            hi = lo + 1

        # Subtle guide lines.
        for frac in (0.25, 0.5, 0.75):
            y = pad_y + (h - 2 * pad_y) * frac
            canvas.create_line(pad_x, y, w - pad_x, y, fill=UI_BORDER, width=1)

        coords = []
        count = len(points)
        for i, value in enumerate(points):
            x = pad_x if count == 1 else pad_x + (w - 2 * pad_x) * i / (count - 1)
            y = pad_y + (h - 2 * pad_y) * (1.0 - (value - lo) / (hi - lo))
            coords.extend((x, y))
        if len(coords) >= 4:
            canvas.create_line(*coords, fill=UI_ACCENT, width=2, smooth=True)
        x, y = coords[-2], coords[-1]
        canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=UI_ACCENT, outline=UI_ACCENT)
        canvas.create_text(pad_x, 2, anchor="nw", text=str(hi), fill=UI_MUTED_2, font=("Segoe UI", 7))
        canvas.create_text(pad_x, h - 2, anchor="sw", text=str(lo), fill=UI_MUTED_2, font=("Segoe UI", 7))

    def refresh_history_page(self):
        page = getattr(self, "history_page", None)
        tree = getattr(self, "history_tree", None)
        if page is None or tree is None:
            return
        try:
            if not page.winfo_exists():
                return
        except Exception:
            return

        records = load_intel_history()
        summary = persistent_history_summary(records)
        stats = opponent_bucket_stats(records)
        journey = rank_journey(records)

        self._history_var("persistent_matches").set(str(summary["matches"]))
        self._history_var("recent_form").set(last_ten_summary(records).replace("Last 10: ", ""))
        self._history_var("persistent_net").set(f"{summary['net']:+d} pts")
        current_rank = session.get("rank") or (journey[-1] if journey else "?")
        self._history_var("history_rank").set(current_rank)
        self._history_var("prediction").set("NEXT  •  " + opponent_intel_text(records))
        self._history_var("identity_status").set(opponent_identity_summary(records))

        def bucket_text(name):
            b = stats.get(name, {})
            played = int(b.get("played") or 0)
            dodges = int(b.get("dodges") or 0)
            wr = b.get("win_rate")
            wr_text = "learning" if wr is None else f"{wr:.0f}% WR"
            return f"{wr_text}  •  {played} played  •  {dodges} dodged"

        self._history_var("real_stats").set(bucket_text("Real Opponent"))
        self._history_var("strong_stats").set(bucket_text("Strong Bot"))
        self._history_var("weak_stats").set(bucket_text("Weak Bot"))

        if journey:
            shown = journey[-6:]
            prefix = "… → " if len(journey) > len(shown) else ""
            self._history_var("journey").set(prefix + " → ".join(shown))
        else:
            self._history_var("journey").set("Waiting for rank OCR")

        dodges = int(summary.get("dodges") or 0)
        owl_avg = summary.get("owl_avg")
        dodge_avg = summary.get("dodge_avg")
        self._history_var("dodge_summary").set(f"{dodges} Owl dodge" + ("s" if dodges != 1 else "") + " recorded")
        self._history_var("owl_summary").set(
            "Avg Owl confidence: ?" if owl_avg is None else f"Avg Owl confidence: {owl_avg:.3f}"
        )

        played_loss_durations = [
            _safe_float(r.get("duration_s")) for r in records
            if str(r.get("result") or "").upper() == "LOSS" and not bool(r.get("was_dodge"))
        ]
        played_loss_durations = [x for x in played_loss_durations if x is not None]
        dodge_durations = [
            _safe_float(r.get("duration_s")) for r in records if bool(r.get("was_dodge"))
        ]
        dodge_durations = [x for x in dodge_durations if x is not None]
        saved = None
        if played_loss_durations and dodge_durations:
            normal_avg = sum(played_loss_durations) / len(played_loss_durations)
            saved = max(0.0, sum(max(0.0, normal_avg - x) for x in dodge_durations))
        if saved is not None:
            time_text = f"Estimated time saved: {format_duration(saved)}"
        elif dodge_avg is not None:
            time_text = f"Avg dodge duration: {dodge_avg:.1f}s"
        else:
            time_text = "Time saved: learning"
        self._history_var("time_summary").set(time_text)

        # Rebuild the visible table.  Only the latest 160 rows are rendered,
        # while the JSON history can keep thousands of matches.
        for item in tree.get_children():
            tree.delete(item)
        self.history_snapshot_by_item = {}
        for row in reversed(records[-160:]):
            stamp = str(row.get("timestamp") or "")
            display_time = stamp.replace("T", " ")[-19:] if stamp else "?"
            result = str(row.get("result") or "?").upper()
            mode = "DODGE" if bool(row.get("was_dodge")) else "PLAYED"
            delta = _safe_int(row.get("delta"))
            duration = _safe_float(row.get("duration_s"))
            values = (
                display_time,
                row.get("match") or "?",
                result,
                row.get("opponent_username") or "?",
                str(row.get("opponent_type") or "MODEL").upper(),
                row.get("predicted_opponent") or "?",
                ", ".join(row.get("detected_heroes") or []) or "—",
                f"{row.get('threat_label') or '?'} {row.get('threat_score') if row.get('threat_score') is not None else ''}".strip(),
                row.get("decision") or "?",
                row.get("rank_after") or row.get("rank_before") or "?",
                row.get("points_after") if row.get("points_after") is not None else "?",
                "?" if delta is None else f"{delta:+d}",
                mode,
                "?" if duration is None else f"{duration:.1f}s",
            )
            tag = "dodge" if mode == "DODGE" else ("win" if result == "WIN" else "loss")
            item_id = tree.insert("", "end", values=values, tags=(tag,))
            self.history_snapshot_by_item[item_id] = row.get("opening_snapshot")

        self._draw_history_chart(records)


    # ==========================================================
    # V6.0 OPPONENT INTELLIGENCE + STRATEGY UI
    # ==========================================================
    def _intel_var(self, name, default="-"):
        var = self.intelligence_vars.get(name)
        if var is None:
            var = tk.StringVar(value=default)
            self.intelligence_vars[name] = var
        return var

    def _strategy_var(self, name, default="-"):
        var = self.strategy_vars.get(name)
        if var is None:
            var = tk.StringVar(value=default)
            self.strategy_vars[name] = var
        return var

    def open_intelligence(self):
        if hasattr(self, "dashboard_main"):
            self.dashboard_main.grid_remove()
        for name in ("history_page", "diagnostics_page", "strategy_page", "daily_page", "vision_page"):
            page = getattr(self, name, None)
            if page is not None:
                try: page.grid_remove()
                except Exception: pass
        if self.intelligence_page is not None:
            try: self.intelligence_page.destroy()
            except Exception: pass
        page = tk.Frame(self.shell, bg=UI_BG)
        page.grid(row=0, column=1, sticky="nsew", padx=(26, 26), pady=(18, 18))
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(3, weight=1)
        self.intelligence_page = page
        self.intelligence_vars = {}
        self._set_active_nav("intelligence")

        header = tk.Frame(page, bg=UI_BG)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.grid_columnconfigure(0, weight=1)
        left = tk.Frame(header, bg=UI_BG); left.grid(row=0, column=0, sticky="w")
        self._label(left, "Opponent Intelligence", bg=UI_BG, size=18, weight="bold").pack(anchor="w")
        self._label(left, "Hero scanner  •  identity confidence  •  threat score  •  opponent memory", bg=UI_BG, fg=UI_MUTED, size=9).pack(anchor="w", pady=(2, 0))
        actions = tk.Frame(header, bg=UI_BG); actions.grid(row=0, column=1, sticky="e")
        self._action_button(actions, "ADD HERO SAMPLE", self.capture_hero_sample, accent=True).pack(side="left", padx=(0, 7))
        self._action_button(actions, "TEST SCANNER", self.test_opponent_scanner).pack(side="left", padx=(0, 7))
        self._action_button(actions, "DASHBOARD", self.show_dashboard).pack(side="left")

        live_card, live = self._make_card(page, padx=14, pady=12)
        live_card.grid(row=1, column=0, sticky="ew")
        top = tk.Frame(live, bg=UI_CARD); top.pack(fill="x")
        self._label(top, "LIVE OPPONENT", size=11, weight="bold").pack(side="left")
        self._pill(top, "REAL-TIME", fg=UI_BLUE, bg=UI_BLUE_DARK).pack(side="left", padx=(8, 0))
        grid = tk.Frame(live, bg=UI_CARD); grid.pack(fill="x", pady=(10, 0))
        for c in range(5): grid.grid_columnconfigure(c, weight=1, uniform="liveintel")
        for i, (title, key, color) in enumerate((
            ("IDENTITY", "identity", UI_GREEN), ("OPPONENT", "username", UI_TEXT),
            ("HEROES", "heroes", UI_BLUE), ("THREAT", "threat", UI_RED), ("DECISION", "decision", UI_GOLD),
        )):
            tile = tk.Frame(grid, bg=UI_TILE, padx=10, pady=9); tile.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 4, 0 if i == 4 else 4))
            self._label(tile, title, bg=UI_TILE, fg=UI_MUTED, size=7).pack(anchor="w")
            self._label(tile, textvariable=self._intel_var(key), bg=UI_TILE, fg=color, size=9, weight="bold", wraplength=180, justify="left").pack(anchor="w", pady=(4, 0))
        self._label(live, textvariable=self._intel_var("reason"), fg=UI_MUTED, size=8).pack(anchor="w", pady=(9, 0))
        self._label(live, textvariable=self._intel_var("memory"), fg=UI_GOLD, size=8).pack(anchor="w", pady=(3, 0))

        mid = tk.Frame(page, bg=UI_BG); mid.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        mid.grid_columnconfigure(0, weight=1); mid.grid_columnconfigure(1, weight=1)
        scanner_card, scanner = self._make_card(mid, padx=14, pady=11); scanner_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        head = tk.Frame(scanner, bg=UI_CARD); head.pack(fill="x")
        self._label(head, "Hero Template Library", size=10, weight="bold").pack(side="left")
        self._action_button(head, "CALIBRATE USER", self.capture_opponent_username_roi).pack(side="right", padx=(5, 0))
        self._action_button(head, "CALIBRATE ORG", self.capture_opponent_org_roi).pack(side="right")
        self.hero_library_text = tk.Text(scanner, height=7, bg=UI_CARD, fg=UI_MUTED, relief="flat", bd=0, highlightthickness=0, font=("Consolas", 8), wrap="word")
        self.hero_library_text.pack(fill="both", expand=True, pady=(8, 0)); self.hero_library_text.config(state="disabled")

        analysis_card, analysis = self._make_card(mid, padx=14, pady=11); analysis_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self._label(analysis, "Replay / Result Analysis", size=10, weight="bold").pack(anchor="w")
        self.analysis_text = tk.Text(analysis, height=7, bg=UI_CARD, fg=UI_MUTED, relief="flat", bd=0, highlightthickness=0, font=("Consolas", 8), wrap="word")
        self.analysis_text.pack(fill="both", expand=True, pady=(8, 0)); self.analysis_text.config(state="disabled")

        bottom_card, bottom = self._make_card(page, padx=12, pady=10); bottom_card.grid(row=3, column=0, sticky="nsew", pady=(14, 0))
        bh = tk.Frame(bottom, bg=UI_CARD); bh.pack(fill="x")
        self._label(bh, "Decision Profiles & Rules", size=10, weight="bold").pack(side="left")
        self._action_button(bh, "ADD RULE", self.add_custom_rule).pack(side="right", padx=(5, 0))
        self._action_button(bh, "CLEAR RULES", self.clear_custom_rules).pack(side="right")
        profile_row = tk.Frame(bottom, bg=UI_CARD); profile_row.pack(fill="x", pady=(9, 7))
        for name in INTELLIGENCE_PROFILES:
            self._action_button(profile_row, name.upper(), lambda n=name: self.set_intelligence_profile(n)).pack(side="left", padx=(0, 6))
        self.rules_text = tk.Text(bottom, height=7, bg=UI_TILE, fg=UI_MUTED, relief="flat", bd=0, highlightthickness=0, font=("Consolas", 8), wrap="word")
        self.rules_text.pack(fill="both", expand=True); self.rules_text.config(state="disabled")
        self.refresh_intelligence_page()

    def refresh_intelligence_page(self):
        if self.intelligence_page is None:
            return
        with session_lock:
            identity = session.get("current_opponent_type") or "?"
            conf = session.get("current_identity_confidence")
            user = session.get("current_opponent_username") or "?"
            heroes = list(session.get("current_detected_heroes") or [])
            threat = session.get("current_threat_score")
            label = session.get("current_threat_label") or "?"
            decision = session.get("current_decision") or "WAIT"
            reason = session.get("current_decision_reason") or "Waiting for opening scan"
        self._intel_var("identity").set(f"{identity} {conf if conf is not None else '?'}%")
        self._intel_var("username").set(user)
        self._intel_var("heroes").set(", ".join(heroes) or "None recognized")
        self._intel_var("threat").set(f"{label} {threat if threat is not None else '?'}")
        self._intel_var("decision").set(decision)
        self._intel_var("reason").set(reason)
        mem = opponent_memory_stats(user if user != "?" else None)
        if mem.get("matches"):
            wr = mem.get("win_rate")
            text = f"Opponent memory: seen {mem['matches']}x • {mem['wins']}W {mem['losses']}L {mem['dodges']} dodges" + (f" • {wr:.0f}% WR" if wr is not None else "")
        else:
            text = "Opponent memory: first encounter / username not calibrated"
        self._intel_var("memory").set(text)
        if hasattr(self, "hero_library_text"):
            lines = []
            for item in hero_library_summary():
                lines.append(f"{item['label']:<28} {item['samples']:>2} sample(s)  threat +{item['threat']}")
            if not lines: lines = ["No general hero templates yet. Owl Smart Dodge samples are automatically reused when available."]
            self.hero_library_text.config(state="normal"); self.hero_library_text.delete("1.0", "end"); self.hero_library_text.insert("1.0", "\n".join(lines)); self.hero_library_text.config(state="disabled")
        if hasattr(self, "analysis_text"):
            self.analysis_text.config(state="normal"); self.analysis_text.delete("1.0", "end"); self.analysis_text.insert("1.0", "\n".join(replay_analysis_lines())); self.analysis_text.config(state="disabled")
        if hasattr(self, "rules_text"):
            cfg = get_intelligence_settings(); profile = current_profile_name()
            lines = [f"ACTIVE PROFILE: {profile}", f"Decision Engine: {'ON' if cfg.get('decision_engine_enabled', True) else 'OFF'}"]
            rules = cfg.get("custom_rules") or []
            if rules:
                lines.append("")
                for i, rule in enumerate(rules, 1):
                    lines.append(f"{i}. {rule.get('name','Rule')} -> {rule.get('action','PLAY')} | identity={rule.get('identity','ANY')} | heroes={','.join(rule.get('heroes') or []) or 'ANY'} | threat>={rule.get('min_threat',0)}")
            else:
                lines.append("No custom rules. Active profile rules are in control.")
            self.rules_text.config(state="normal"); self.rules_text.delete("1.0", "end"); self.rules_text.insert("1.0", "\n".join(lines)); self.rules_text.config(state="disabled")

    def set_intelligence_profile(self, name):
        if name not in INTELLIGENCE_PROFILES:
            return
        update_intelligence_setting("active_profile", name)
        self.add_log(f"Decision profile: {name}")
        self.refresh_intelligence_page()
        self.refresh()

    def add_custom_rule(self):
        name = simpledialog.askstring("Decision Rule", "Rule name:", parent=self.root)
        if not name: return
        action = (simpledialog.askstring("Decision Rule", "Action: DODGE or PLAY", initialvalue="DODGE", parent=self.root) or "DODGE").upper()
        if action not in ("DODGE", "PLAY"): action = "DODGE"
        identity = (simpledialog.askstring("Decision Rule", "Identity: REAL, BOT or ANY", initialvalue="ANY", parent=self.root) or "ANY").upper()
        heroes_text = simpledialog.askstring("Decision Rule", "Required hero names, comma separated (blank = any):", parent=self.root) or ""
        heroes = [x.strip() for x in heroes_text.split(",") if x.strip()]
        min_threat = simpledialog.askinteger("Decision Rule", "Minimum threat score (0-100):", initialvalue=0, minvalue=0, maxvalue=100, parent=self.root)
        cfg = get_intelligence_settings(); rules = list(cfg.get("custom_rules") or [])
        rules.append({"name": name, "action": action, "identity": identity, "heroes": heroes, "min_threat": int(min_threat or 0), "enabled": True})
        update_intelligence_setting("custom_rules", rules)
        self.refresh_intelligence_page()

    def clear_custom_rules(self):
        if messagebox.askyesno("Clear Rules", "Delete all custom Decision Engine rules?"):
            update_intelligence_setting("custom_rules", [])
            self.refresh_intelligence_page()

    def capture_hero_sample(self):
        if self.engine.running:
            messagebox.showwarning("Stop grinder first", "Stop the grinder before adding a hero sample.")
            return
        label = simpledialog.askstring("Hero Sample", "Hero name (example: Owl of Readiness):", parent=self.root)
        if not label: return
        threat = simpledialog.askinteger("Hero Threat", "Threat weight for this hero (0-50):", initialvalue=20, minvalue=0, maxvalue=50, parent=self.root)
        try: ref = self._phone_reference_screenshot()
        except Exception as e:
            messagebox.showerror("Hero Sample", str(e)); return
        def save_crop(x1, y1, x2, y2):
            region = ref[y1:y2, x1:x2]
            if region.size == 0: return
            slug = _safe_slug(label)
            folder = HERO_TEMPLATE_DIR / slug; folder.mkdir(parents=True, exist_ok=True)
            idx = len(list(folder.glob("sample_*.png"))) + 1
            path = folder / f"sample_{idx:02d}.png"
            cv2.imwrite(str(path), region)
            meta = load_hero_library_meta(); meta[slug] = {"label": label, "threat": int(threat or 20)}; save_hero_library_meta(meta)
            cfg = get_intelligence_settings(); weights = dict(cfg.get("threat_weights") or {}); weights[label] = int(threat or 20); update_intelligence_setting("threat_weights", weights)
            self.add_log(f"Opponent Scanner: saved {label} sample {path.name}")
            if self.intelligence_page is not None: self.refresh_intelligence_page()
        self._show_roi_picker(ref, "Add Hero Sample", save_crop, instructions="Drag tightly around one enemy hero portrait / distinctive hero art. Use 2-4 poses for best recognition.")

    def test_opponent_scanner(self):
        try: ref = self._phone_reference_screenshot()
        except Exception as e:
            messagebox.showerror("Opponent Scanner", str(e)); return
        intel = collect_opponent_intelligence(ref)
        heroes = ", ".join(intel.get("heroes") or []) or "none"
        msg = f"Identity: {intel['identity']} ({intel['identity_confidence']}%)\nUsername: {intel.get('username') or '?'}\nHeroes: {heroes}\nThreat: {intel['threat_label']} {intel['threat']}\nDecision: {intel['decision']}\nReason: {intel['decision_reason']}"
        messagebox.showinfo("Opponent Scanner", msg)

    def capture_opponent_username_roi(self):
        if self.engine.running:
            messagebox.showwarning("Stop grinder first", "Stop the grinder before opponent username calibration.")
            return
        if not messagebox.askokcancel("Opponent Username Calibration", "Put the PHONE on an Arena battle/opponent screen where the opponent username is visible. Then select ONLY the username text."):
            return
        try: ref = self._phone_reference_screenshot()
        except Exception as e:
            messagebox.showerror("Calibration", str(e)); return
        def save_roi(x1, y1, x2, y2):
            update_opponent_setting("username_roi", [x1, y1, x2, y2])
            self.add_log(f"Opponent username ROI calibrated: {x1},{y1} -> {x2},{y2}")
        self._show_roi_picker(ref, "Opponent Username", save_roi, instructions="Drag around ONLY the opponent username.")

    def open_selected_snapshot(self):
        tree = getattr(self, "history_tree", None)
        if tree is None: return
        selected = tree.selection()
        if not selected: return
        snapshot_name = getattr(self, "history_snapshot_by_item", {}).get(selected[0])
        path = match_snapshot_path(snapshot_name)
        if path:
            try: os.startfile(path)
            except Exception: pass
        else:
            messagebox.showinfo("Match Snapshot", "No opening snapshot was stored for this match.")

    def open_strategy(self):
        if hasattr(self, "dashboard_main"): self.dashboard_main.grid_remove()
        for name in ("history_page", "diagnostics_page", "intelligence_page", "daily_page", "vision_page"):
            page = getattr(self, name, None)
            if page is not None:
                try: page.grid_remove()
                except Exception: pass
        if self.strategy_page is not None:
            try: self.strategy_page.destroy()
            except Exception: pass
        page = tk.Frame(self.shell, bg=UI_BG)
        page.grid(row=0, column=1, sticky="nsew", padx=(26, 26), pady=(18, 18))
        page.grid_columnconfigure(0, weight=1); page.grid_rowconfigure(3, weight=1)
        self.strategy_page = page; self.strategy_vars = {}; self._set_active_nav("strategy")
        header = tk.Frame(page, bg=UI_BG); header.grid(row=0, column=0, sticky="ew", pady=(0, 14)); header.grid_columnconfigure(0, weight=1)
        left = tk.Frame(header, bg=UI_BG); left.grid(row=0, column=0, sticky="w")
        self._label(left, "Battle Strategy Engine", bg=UI_BG, size=18, weight="bold").pack(anchor="w")
        self._label(left, "Profiles  •  conditional action scripts  •  session goals  •  notifications", bg=UI_BG, fg=UI_MUTED, size=9).pack(anchor="w", pady=(2, 0))
        actions = tk.Frame(header, bg=UI_BG); actions.grid(row=0, column=1, sticky="e")
        self._action_button(actions, "DASHBOARD", self.show_dashboard).pack(side="left")

        settings = get_intelligence_settings(); strat = settings.get("strategy_engine") or {}
        self.strategy_enabled_var = tk.BooleanVar(value=bool(strat.get("enabled", False)))
        self.strategy_auto_var = tk.BooleanVar(value=bool(strat.get("allow_auto", True)))

        top = tk.Frame(page, bg=UI_BG); top.grid(row=1, column=0, sticky="ew"); top.grid_columnconfigure(0, weight=1); top.grid_columnconfigure(1, weight=1)
        profile_card, profile = self._make_card(top, padx=14, pady=11); profile_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._label(profile, "Decision Profile", size=10, weight="bold").pack(anchor="w")
        self._label(profile, textvariable=self._strategy_var("profile"), fg=UI_GOLD, size=13, weight="bold").pack(anchor="w", pady=(7, 8))
        row = tk.Frame(profile, bg=UI_CARD); row.pack(fill="x")
        for name in INTELLIGENCE_PROFILES:
            self._action_button(row, name.upper(), lambda n=name: self.set_intelligence_profile(n)).pack(side="left", padx=(0, 5))

        goal_card, goal = self._make_card(top, padx=14, pady=11); goal_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        gh = tk.Frame(goal, bg=UI_CARD); gh.pack(fill="x")
        self._label(gh, "Session Goal", size=10, weight="bold").pack(side="left")
        self._action_button(gh, "SET GOAL", self.set_session_goal).pack(side="right")
        self._label(goal, textvariable=self._strategy_var("goal"), fg=UI_GREEN, size=12, weight="bold").pack(anchor="w", pady=(8, 4))
        self._label(goal, "Windows notifications fire on completion, Master V, Arena close and critical health.", fg=UI_MUTED, size=7, wraplength=430, justify="left").pack(anchor="w")

        engine_card, eng = self._make_card(page, padx=14, pady=11); engine_card.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        eh = tk.Frame(eng, bg=UI_CARD); eh.pack(fill="x")
        self._label(eh, "In-Battle Script Engine", size=10, weight="bold").pack(side="left")
        ToggleSwitch(eh, self.strategy_enabled_var, self.save_strategy_switches, bg=UI_CARD, on_color=UI_GREEN).pack(side="right")
        self._label(eh, "Enabled", fg=UI_MUTED, size=8).pack(side="right", padx=(0, 6))
        row2 = tk.Frame(eng, bg=UI_CARD); row2.pack(fill="x", pady=(9, 0))
        ToggleSwitch(row2, self.strategy_auto_var, self.save_strategy_switches, bg=UI_CARD).pack(side="right")
        self._label(row2, "Keep game AUTO enabled while script taps calibrated actions", fg=UI_MUTED, size=8).pack(side="left")
        buttons = tk.Frame(eng, bg=UI_CARD); buttons.pack(fill="x", pady=(9, 0))
        self._action_button(buttons, "CALIBRATE ACTION", self.calibrate_strategy_action).pack(side="left", padx=(0, 6))
        self._action_button(buttons, "ADD STEP", self.add_strategy_step).pack(side="left", padx=(0, 6))
        self._action_button(buttons, "CLEAR STEPS", self.clear_strategy_steps).pack(side="left")

        bottom = tk.Frame(page, bg=UI_BG); bottom.grid(row=3, column=0, sticky="nsew", pady=(14, 0)); bottom.grid_columnconfigure(0, weight=1); bottom.grid_columnconfigure(1, weight=1); bottom.grid_rowconfigure(0, weight=1)
        actions_card, ab = self._make_card(bottom, padx=14, pady=10); actions_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._label(ab, "Calibrated Actions", size=10, weight="bold").pack(anchor="w")
        self.strategy_actions_text = tk.Text(ab, bg=UI_CARD, fg=UI_MUTED, relief="flat", bd=0, highlightthickness=0, font=("Consolas", 8), wrap="word")
        self.strategy_actions_text.pack(fill="both", expand=True, pady=(7, 0)); self.strategy_actions_text.config(state="disabled")
        steps_card, sb = self._make_card(bottom, padx=14, pady=10); steps_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self._label(sb, "Script Steps", size=10, weight="bold").pack(anchor="w")
        self.strategy_steps_text = tk.Text(sb, bg=UI_CARD, fg=UI_MUTED, relief="flat", bd=0, highlightthickness=0, font=("Consolas", 8), wrap="word")
        self.strategy_steps_text.pack(fill="both", expand=True, pady=(7, 0)); self.strategy_steps_text.config(state="disabled")
        self.refresh_strategy_page()

    def refresh_strategy_page(self):
        if self.strategy_page is None: return
        cfg = get_intelligence_settings(); strat = cfg.get("strategy_engine") or {}
        self._strategy_var("profile").set(current_profile_name())
        self._strategy_var("goal").set(goal_status().get("text", "No active goal"))
        if hasattr(self, "strategy_actions_text"):
            points = strat.get("action_points") or {}
            lines = [f"{name}: ({pt[0]:.0f}, {pt[1]:.0f})" for name, pt in points.items()] or ["No actions calibrated. Safe: script engine cannot tap anything yet."]
            self.strategy_actions_text.config(state="normal"); self.strategy_actions_text.delete("1.0", "end"); self.strategy_actions_text.insert("1.0", "\n".join(lines)); self.strategy_actions_text.config(state="disabled")
        if hasattr(self, "strategy_steps_text"):
            steps = strat.get("steps") or []
            lines = []
            for i, step in enumerate(steps, 1):
                cond = []
                if step.get("identity") not in (None, "", "ANY"): cond.append(str(step.get("identity")))
                if step.get("hero"): cond.append("hero=" + str(step.get("hero")))
                if int(step.get("min_threat") or 0): cond.append("threat≥" + str(step.get("min_threat")))
                lines.append(f"{i}. {int(step.get('at_ms') or 0)}ms -> {step.get('action')}" + (" | " + ", ".join(cond) if cond else ""))
            if not lines: lines = ["No script steps. Add calibrated actions first, then timed/conditional steps."]
            self.strategy_steps_text.config(state="normal"); self.strategy_steps_text.delete("1.0", "end"); self.strategy_steps_text.insert("1.0", "\n".join(lines)); self.strategy_steps_text.config(state="disabled")

    def save_strategy_switches(self):
        cfg = get_intelligence_settings(); strat = dict(cfg.get("strategy_engine") or {})
        strat["enabled"] = bool(self.strategy_enabled_var.get()); strat["allow_auto"] = bool(self.strategy_auto_var.get())
        update_intelligence_setting("strategy_engine", strat)
        self.add_log(f"Battle Strategy: {'ON' if strat['enabled'] else 'OFF'} • AUTO {'ON' if strat['allow_auto'] else 'OFF'}")

    def calibrate_strategy_action(self):
        if self.engine.running:
            messagebox.showwarning("Stop grinder first", "Stop the grinder before calibrating battle action points."); return
        name = simpledialog.askstring("Battle Action", "Action name (example: Skill A / Ultimate / Target 1):", parent=self.root)
        if not name: return
        try: ref = self._phone_reference_screenshot()
        except Exception as e: messagebox.showerror("Battle Action", str(e)); return
        def save_point(x, y):
            cfg = get_intelligence_settings(); strat = dict(cfg.get("strategy_engine") or {}); points = dict(strat.get("action_points") or {}); points[name] = [x, y]; strat["action_points"] = points; update_intelligence_setting("strategy_engine", strat)
            self.add_log(f"Strategy action '{name}' calibrated at ({x:.0f},{y:.0f})"); self.refresh_strategy_page()
        self._show_point_picker(ref, "Calibrate Battle Action", f"Click the CENTER of '{name}' on the phone screenshot.", save_point)

    def add_strategy_step(self):
        cfg = get_intelligence_settings(); strat = dict(cfg.get("strategy_engine") or {}); points = strat.get("action_points") or {}
        if not points:
            messagebox.showinfo("Strategy Step", "Calibrate at least one action first."); return
        action = simpledialog.askstring("Strategy Step", "Action name exactly as calibrated:\n" + ", ".join(points.keys()), parent=self.root)
        if not action or action not in points:
            messagebox.showerror("Strategy Step", "Unknown action name."); return
        at_ms = simpledialog.askinteger("Strategy Step", "Execute how many milliseconds after battle starts?", initialvalue=1000, minvalue=0, maxvalue=120000, parent=self.root)
        identity = (simpledialog.askstring("Strategy Step", "Identity condition: ANY, REAL or BOT", initialvalue="ANY", parent=self.root) or "ANY").upper()
        hero = simpledialog.askstring("Strategy Step", "Required detected hero (blank = any):", parent=self.root) or ""
        min_threat = simpledialog.askinteger("Strategy Step", "Minimum threat (0-100):", initialvalue=0, minvalue=0, maxvalue=100, parent=self.root)
        steps = list(strat.get("steps") or []); steps.append({"action": action, "at_ms": int(at_ms or 0), "identity": identity, "hero": hero.strip(), "min_threat": int(min_threat or 0), "enabled": True}); steps.sort(key=lambda x: int(x.get("at_ms") or 0)); strat["steps"] = steps; update_intelligence_setting("strategy_engine", strat); self.refresh_strategy_page()

    def clear_strategy_steps(self):
        if not messagebox.askyesno("Clear Strategy", "Delete all in-battle script steps? Calibrated action points will remain."): return
        cfg = get_intelligence_settings(); strat = dict(cfg.get("strategy_engine") or {}); strat["steps"] = []; update_intelligence_setting("strategy_engine", strat); self.refresh_strategy_page()

    def set_session_goal(self):
        gtype = (simpledialog.askstring("Session Goal", "Goal type: points, matches, or net", initialvalue="points", parent=self.root) or "points").lower().strip()
        if gtype not in ("points", "matches", "net"): gtype = "points"
        default = MASTER_V_POINTS if gtype == "points" else (50 if gtype == "matches" else 500)
        target = simpledialog.askinteger("Session Goal", f"Target {gtype}:", initialvalue=default, minvalue=1, maxvalue=1000000, parent=self.root)
        if target is None: return
        update_intelligence_setting("goal", {"enabled": True, "type": gtype, "target": int(target)})
        self.goal_var.set(goal_status().get("text", "Goal")); self.refresh_strategy_page(); self.add_log(f"Session goal set: {gtype} {target}")

    def _check_notifications(self):
        cfg = get_intelligence_settings(); notes = cfg.get("notifications") or {}
        now = datetime.now()
        with session_lock:
            pts = session.get("points"); started = session.get("started_at")
        if notes.get("master_reached", True) and pts is not None and int(pts) >= MASTER_V_POINTS:
            key = f"master:{started}"
            if key not in self._toast_marks:
                self._toast_marks.add(key); send_windows_toast("Master V reached", f"Arena score: {int(pts)}. Grinding continues.")
        goal = goal_status()
        if notes.get("goal_complete", True) and goal.get("complete"):
            key = f"goal:{started}:{goal.get('type')}:{goal.get('target')}"
            if key not in self._toast_marks:
                self._toast_marks.add(key); send_windows_toast("Arena goal complete", goal.get("text"))
        if notes.get("arena_close", True):
            close = arena_close_time(now)
            seconds = (close - now).total_seconds()
            if 0 < seconds <= 600 and close.hour in (13, 20):
                key = close.isoformat(timespec="minutes")
                if key != self._last_arena_notice_key:
                    self._last_arena_notice_key = key; send_windows_toast("Arena closes soon", f"About {max(1, int(seconds // 60))} minutes remaining.")
        if notes.get("critical_health", True):
            health = self.engine.health_snapshot()
            if health.get("overall") == "ISSUE" and time.time() - self._last_health_toast_at > 300:
                self._last_health_toast_at = time.time(); send_windows_toast("Arena Companion system issue", health.get("last_error") or health.get("last_recovery") or "Open Diagnostics for details.")



    # ==========================================================
    # V7.0 DAILY ASSISTANT — modular safe collectors
    # ==========================================================
    def _daily_var(self, name, default="READY"):
        var = self.daily_module_vars.get(name)
        if var is None:
            var = tk.StringVar(value=default)
            self.daily_module_vars[name] = var
        return var

    def _daily_set_status(self, module, text):
        # Tk variables must only be touched from Tk's UI thread. Daily workers
        # run in background threads, so marshal status updates through after().
        def apply():
            try:
                self._daily_var(module).set(text)
            except Exception:
                pass
        try:
            self.root.after(0, apply)
        except Exception:
            pass

    def _daily_set_debug(self, text):
        def apply():
            try:
                self.daily_debug_var.set(text)
            except Exception:
                pass
        try:
            self.root.after(0, apply)
        except Exception:
            pass

    def _daily_set_summary(self, text):
        def apply():
            try:
                self.daily_summary_var.set(text)
            except Exception:
                pass
        try:
            self.root.after(0, apply)
        except Exception:
            pass

    def _daily_phone_xy(self, ref_x, ref_y):
        aw = int(getattr(self.engine, "actual_w", REFERENCE_W) or REFERENCE_W)
        ah = int(getattr(self.engine, "actual_h", REFERENCE_H) or REFERENCE_H)
        x = round(float(ref_x) * aw / REFERENCE_W)
        y = round(float(ref_y) * ah / REFERENCE_H)
        return x, y

    def _daily_debug_dir(self):
        root = PROFILE_DIR / "daily_debug"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _daily_save_debug_frame(self, module, stage, ref, point=None, label=None):
        # Keep normal automation hot.  DRY RUN remains a full visual debugger.
        if not getattr(self, "daily_dry_run", False) and not getattr(self, "daily_debug_capture", False):
            return None
        try:
            img = ref.copy()
            if point is not None:
                x, y = int(point[0]), int(point[1])
                cv2.circle(img, (x, y), 18, (0, 0, 255), 3)
                cv2.line(img, (x - 28, y), (x + 28, y), (0, 0, 255), 2)
                cv2.line(img, (x, y - 28), (x, y + 28), (0, 0, 255), 2)
                if label:
                    cv2.putText(
                        img, str(label), (max(5, x - 140), max(28, y - 34)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255), 2, cv2.LINE_AA
                    )
            stamp = time.strftime("%Y%m%d_%H%M%S")
            safe_module = re.sub(r"[^A-Za-z0-9_-]+", "_", str(module)).strip("_") or "daily"
            safe_stage = re.sub(r"[^A-Za-z0-9_-]+", "_", str(stage)).strip("_") or "frame"
            path = self._daily_debug_dir() / f"{stamp}_{safe_module}_{safe_stage}_{int(time.time()*1000)%100000}.png"
            cv2.imwrite(str(path), img)
            return path
        except Exception:
            return None

    def _daily_check_deadline(self):
        if self.daily_deadline and time.monotonic() > self.daily_deadline:
            self.daily_stop_event.set()
            raise TimeoutError("Daily module watchdog timeout (120s).")

    def _daily_phash(self, ref, roi):
        try:
            x1, y1, x2, y2 = [int(v) for v in roi]
            crop = ref[y1:y2, x1:x2]
            if crop is None or crop.size == 0:
                return None
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA)
            dct = cv2.dct(np.float32(gray))
            low = dct[:8, :8]
            med = float(np.median(low.flatten()[1:]))
            value = 0
            for bit in (low > med).flatten():
                value = (value << 1) | int(bool(bit))
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _daily_hamming(a, b):
        try:
            return int(int(a ^ b).bit_count())
        except Exception:
            return 64

    def _daily_ocr_region(self, ref, roi, psm=11):
        if not HAS_TESSERACT:
            return ""
        try:
            x1, y1, x2, y2 = [int(v) for v in roi]
            crop = ref[y1:y2, x1:x2]
            text = pytesseract.image_to_string(crop, config=f"--psm {int(psm)}")
            return normalize_daily_word(text)
        except Exception:
            return ""

    def _daily_anchor_check(self, anchor, ref):
        """Vision-first route verification with no OCR in the hot path."""
        name = str(anchor or "").upper()
        screen, conf, detail = self._vision_identify_screen(ref)
        accepted = {
            "HOME": {"HOME"},
            "MAIL": {"MAIL"},
            "SHOP": {"SHOP", "QUEST"},
            "QUEST": {"QUEST"},
            "EVENT": {"EVENT"},
            "RECRUIT": {"RECRUIT"},
            "REGULAR_RECRUIT": {"RECRUIT"},
            "CHAIN": {"CHAIN"},
            "IDLE_POPUP": {"IDLE_POPUP"},
        }
        if name in accepted:
            ok = screen in accepted[name]
            return ok, f"vision={screen} {conf:.0f}% • {detail}"
        return True, "no anchor configured"

    def _daily_frame_hash(self, ref):
        # Cheap whole-screen transition fingerprint. It is intentionally coarse
        # and used only to know when a tap has produced a new frame.
        return self._daily_phash(ref, (0, 0, REFERENCE_W, REFERENCE_H))

    def _daily_wait_frame_change(self, before, timeout=DAILY_ROUTE_CHANGE_TIMEOUT, min_bits=5):
        base = self._daily_frame_hash(before) if before is not None else None
        deadline = time.monotonic() + max(0.12, float(timeout))
        last = before
        while time.monotonic() < deadline and not self.daily_stop_event.is_set():
            self._daily_check_deadline()
            try:
                cur = self._phone_reference_screenshot()
                last = cur
                if base is None:
                    return True, cur
                got = self._daily_frame_hash(cur)
                if got is not None and self._daily_hamming(base, got) >= int(min_bits):
                    return True, cur
            except Exception:
                pass
            time.sleep(0.025)
        return False, last

    def _daily_wait_anchor(self, anchor, timeout=1.4, initial_ref=None):
        deadline = time.monotonic() + max(0.35, float(timeout))
        last_ref = initial_ref
        last_detail = "not checked"
        # OCR anchors are intentionally checked at a modest cadence. HOME and
        # IDLE are image-only and therefore essentially instant.
        while time.monotonic() < deadline and not self.daily_stop_event.is_set():
            self._daily_check_deadline()
            if last_ref is None:
                last_ref = self._phone_reference_screenshot()
            ok, last_detail = self._daily_anchor_check(anchor, last_ref)
            if ok:
                return True, last_detail, last_ref
            time.sleep(0.055)
            last_ref = self._phone_reference_screenshot()
        return False, last_detail, last_ref

    def _daily_return_home(self, module, max_attempts=4):
        """Return via the visible Home control and verify HOME; retry if needed."""
        if self.daily_stop_event.is_set():
            return False
        last_detail = "not checked"
        try:
            for attempt in range(1, max(1, int(max_attempts)) + 1):
                if self.daily_stop_event.is_set():
                    return False
                before = self._phone_reference_screenshot()
                already_home, detail = self._daily_anchor_check("HOME", before)
                if already_home:
                    self.add_log(f"Daily {module}: Home already visible • {detail}")
                    self._daily_set_debug(f"{module}: HOME visible")
                    return True

                px, py = self._daily_phone_xy(*DAILY_HOME_REF)
                self._daily_set_debug(
                    f"{module}: HOME attempt {attempt}/{max_attempts} • "
                    f"ref {DAILY_HOME_REF[0]},{DAILY_HOME_REF[1]} -> phone {px},{py}"
                )
                self._daily_save_debug_frame(
                    module, f"return_home_{attempt:02d}_before", before, DAILY_HOME_REF, "HOME"
                )
                self._daily_tap_reference(float(DAILY_HOME_REF[0]), float(DAILY_HOME_REF[1]))
                self.add_log(
                    f"Daily {module}: Home tap attempt {attempt}/{max_attempts} "
                    f"ref {DAILY_HOME_REF[0]},{DAILY_HOME_REF[1]} -> phone {px},{py}"
                )

                ok, last_detail, ref = self._daily_wait_anchor("HOME", timeout=DAILY_HOME_VERIFY_TIMEOUT)
                if ref is not None:
                    self._daily_save_debug_frame(
                        module,
                        f"return_home_{attempt:02d}_{'verified' if ok else 'retry'}",
                        ref,
                    )
                if ok:
                    self.add_log(f"Daily {module}: Home visible after attempt {attempt} • {last_detail}")
                    self._daily_set_debug(f"{module}: HOME verified on attempt {attempt}")
                    return True

                self.add_log(
                    f"Daily {module}: Home not visible after attempt {attempt}; repeating Home action • {last_detail}"
                )
                time.sleep(0.04)

            self.add_log(f"Daily {module}: Home verification FAILED after {max_attempts} attempts • {last_detail}")
            return False
        except Exception as e:
            self.add_log(f"Daily {module}: Home return error: {e}")
            return False

    def _daily_write_run_log(self, payload):
        try:
            with open(DAILY_RUN_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass

    @staticmethod
    def _daily_merge_stats(target, extra):
        for key in ("actions", "claims", "free", "overlays", "detected"):
            target[key] = int(target.get(key, 0) or 0) + int((extra or {}).get(key, 0) or 0)
        return target

    def _daily_summary_text(self, results, elapsed=None):
        rows = list(results or [])
        done = sum(1 for r in rows if r.get("status") == "DONE")
        skipped = sum(1 for r in rows if r.get("status") == "SKIPPED")
        claims = sum(int(r.get("claims", 0) or 0) for r in rows)
        free = sum(int(r.get("free", 0) or 0) for r in rows)
        failures = sum(1 for r in rows if r.get("status") not in ("DONE", "SKIPPED"))
        bits = [f"{done} done", f"{claims} claim action{'s' if claims != 1 else ''}", f"{free} free action{'s' if free != 1 else ''}"]
        if skipped:
            bits.append(f"{skipped} skipped")
        if failures:
            bits.append(f"{failures} issue{'s' if failures != 1 else ''}")
        if elapsed is not None:
            bits.append(f"{float(elapsed):.0f}s")
        bits.append("spend actions blocked")
        return " • ".join(bits)

    def _daily_preview_route(self, module, route, ref):
        img = ref.copy()
        rows = []
        for i, pair in enumerate(route, 1):
            x, y = float(pair[0]), float(pair[1])
            px, py = self._daily_phone_xy(x, y)
            rows.append(f"{i}: ref {int(x)},{int(y)} -> phone {px},{py}")
            try:
                cv2.circle(img, (int(x), int(y)), 16, (0, 0, 255), 3)
                cv2.putText(img, str(i), (int(x)+18, int(y)-12),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA)
            except Exception:
                pass
        path = self._daily_save_debug_frame(module, "dry_route", img)
        self.add_log(f"Daily {module} DRY RUN route: " + (" | ".join(rows) if rows else "no route"))
        if path:
            self.add_log(f"Daily {module} DRY RUN screenshot: {path}")
        return rows

    # ==========================================================
    # V7.2 VISION-FIRST SCREEN UNDERSTANDING
    # ==========================================================
    def _vision_var(self, name, default="-"):
        var = self.vision_vars.get(name)
        if var is None:
            var = tk.StringVar(value=default)
            self.vision_vars[name] = var
        return var

    def _vision_frame_signature(self, ref):
        try:
            gray=cv2.cvtColor(ref,cv2.COLOR_BGR2GRAY)
            tiny=cv2.resize(gray,(64,30),interpolation=cv2.INTER_AREA)
            return hashlib.blake2s(tiny.tobytes(),digest_size=8).hexdigest()
        except Exception:
            return None

    def _vision_identify_screen(self, ref):
        best_name = "UNKNOWN"
        best_avg = 999.0
        best_dists = []
        for name, cfg in VISION_SCREEN_SIGNATURES.items():
            dists = []
            for roi, expected in zip(cfg.get("rois", []), cfg.get("hashes", [])):
                got = self._daily_phash(ref, roi)
                dists.append(self._daily_hamming(got, expected) if got is not None else 64)
            if not dists:
                continue
            avg = float(sum(dists)) / len(dists)
            if avg < best_avg:
                best_name, best_avg, best_dists = name, avg, dists
        cfg = VISION_SCREEN_SIGNATURES.get(best_name, {})
        limit = float(cfg.get("max_avg", 12.0))
        if best_avg > limit:
            conf = max(0.0, 100.0 - best_avg * 3.0)
            return "UNKNOWN", conf, f"nearest {best_name} d={best_avg:.1f}"
        conf = max(0.0, min(100.0, 100.0 - (best_avg / max(1.0, limit)) * 28.0))
        return best_name, conf, f"d={best_avg:.1f} {best_dists}"

    @staticmethod
    def _vision_nms(actions, radius_x=48, radius_y=28):
        out = []
        for a in sorted(actions, key=lambda x: (-float(x.get("conf",0)), x.get("y",0), x.get("x",0))):
            if any(abs(int(a["x"])-int(b["x"])) < radius_x and abs(int(a["y"])-int(b["y"])) < radius_y and a.get("label") == b.get("label") for b in out):
                continue
            out.append(a)
        priority = {"CLAIM ALL":0, "CLAIM":1, "FREE":2}
        out.sort(key=lambda a:(priority.get(a.get("label"),9), -float(a.get("conf",0)), a.get("y",0), a.get("x",0)))
        return out

    def _vision_candidate_boxes(self, ref, screen="UNKNOWN"):
        """Find likely clickable colored button rectangles using OpenCV only."""
        roi = VISION_ACTION_ROIS.get(screen, VISION_ACTION_ROIS["UNKNOWN"])
        x0,y0,x1,y1 = [int(v) for v in roi]
        crop = ref[y0:y1, x0:x1]
        if crop is None or crop.size == 0:
            return []
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        # TG:BTC action buttons are predominantly saturated red/pink/orange.
        red1 = cv2.inRange(hsv, np.array((0,70,65),np.uint8), np.array((24,255,255),np.uint8))
        red2 = cv2.inRange(hsv, np.array((154,65,65),np.uint8), np.array((179,255,255),np.uint8))
        gold = cv2.inRange(hsv, np.array((18,80,80),np.uint8), np.array((42,255,255),np.uint8))
        mask = cv2.bitwise_or(cv2.bitwise_or(red1, red2), gold)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (11,5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for c in contours:
            x,y,w,h = cv2.boundingRect(c)
            area = w*h
            if not (58 <= w <= 460 and 18 <= h <= 125 and area >= 1500):
                continue
            # Avoid tiny icon-only saturated blocks and long decorative bars.
            fill = float(cv2.contourArea(c)) / max(1.0, float(area))
            if fill < 0.14:
                continue
            gx1=max(0,x0+x-12); gy1=max(55,y0+y-10)
            gx2=min(REFERENCE_W,x0+x+w+12); gy2=min(REFERENCE_H,y0+y+h+10)
            boxes.append((gx1,gy1,gx2,gy2))
        boxes.sort(key=lambda b: ((b[2]-b[0])*(b[3]-b[1])), reverse=True)
        # De-duplicate heavily-overlapping regions.
        out=[]
        for b in boxes:
            bx1,by1,bx2,by2=b
            keep=True
            for q in out:
                qx1,qy1,qx2,qy2=q
                ix=max(0,min(bx2,qx2)-max(bx1,qx1)); iy=max(0,min(by2,qy2)-max(by1,qy1))
                inter=ix*iy
                amin=min((bx2-bx1)*(by2-by1),(qx2-qx1)*(qy2-qy1))
                if amin and inter/amin > 0.72:
                    keep=False; break
            if keep:
                out.append(b)
            if len(out) >= VISION_CANDIDATE_LIMIT:
                break
        return out

    @staticmethod
    def _vision_label_from_text(text, allowed):
        norm = normalize_daily_word(text)
        allowed = set(normalize_daily_word(x) for x in allowed)
        words = [x for x in norm.split() if x]
        joined = " ".join(words)
        if "CLAIM ALL" in allowed and joined == "CLAIM ALL":
            return "CLAIM ALL"
        if "CLAIM" in allowed and joined == "CLAIM":
            return "CLAIM"
        if "FREE" in allowed and joined == "FREE":
            return "FREE"
        return None

    def _vision_ocr_candidate_batch(self, ref, boxes, allowed):
        """OCR all OpenCV button candidates in one Tesseract process."""
        if not HAS_TESSERACT or not boxes:
            return []
        prepared=[]
        max_w=1
        for box in boxes:
            x1,y1,x2,y2=[int(v) for v in box]
            crop=ref[y1:y2,x1:x2]
            if crop is None or crop.size == 0:
                continue
            scale=1.25
            small=cv2.resize(crop,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
            prepared.append((box,small))
            max_w=max(max_w,small.shape[1])
        if not prepared:
            return []
        gap=14
        total_h=sum(img.shape[0]+gap for _,img in prepared)+gap
        canvas=np.full((total_h,max_w+24,3),245,dtype=np.uint8)
        rows=[]; cy=gap
        for box,img in prepared:
            h,w=img.shape[:2]
            canvas[cy:cy+h,12:12+w]=img
            rows.append((cy,cy+h,box))
            cy+=h+gap
        try:
            data=pytesseract.image_to_data(canvas,config="--psm 11",output_type=pytesseract.Output.DICT)
        except Exception:
            return []
        grouped={i:[] for i in range(len(rows))}
        n=len(data.get("text",[]))
        for i in range(n):
            raw=str(data.get("text",[""])[i] or "").strip()
            if not raw:
                continue
            try: conf=float(data.get("conf",[-1])[i])
            except Exception: conf=-1.0
            if conf < 45:
                continue
            y=int(data.get("top",[0])[i]); h=int(data.get("height",[0])[i]); mid=y+h/2
            for idx,(ry1,ry2,_) in enumerate(rows):
                if ry1 <= mid <= ry2:
                    grouped[idx].append((int(data.get("left",[0])[i]),raw,conf)); break
        actions=[]
        for idx,items in grouped.items():
            if not items:
                continue
            items.sort(key=lambda z:z[0])
            text=" ".join(x[1] for x in items)
            label=self._vision_label_from_text(text,allowed)
            if not label:
                continue
            conf=min(x[2] for x in items)
            x1,y1,x2,y2=rows[idx][2]
            actions.append({"label":label,"x":(x1+x2)//2,"y":(y1+y2)//2,"conf":conf,"source":"CV+OCR","box":(x1,y1,x2,y2)})
        return self._vision_nms(actions)

    def _vision_ocr_region(self, ref, roi, allowed):
        """Small ROI OCR fallback; maps detections back to reference coords."""
        if not HAS_TESSERACT:
            return [], ""
        x0,y0,x1,y1=[int(v) for v in roi]
        crop=ref[y0:y1,x0:x1]
        if crop is None or crop.size == 0:
            return [], ""
        scale=float(VISION_OCR_SCALE)
        img=cv2.resize(crop,(max(240,int(crop.shape[1]*scale)),max(120,int(crop.shape[0]*scale))),interpolation=cv2.INTER_AREA)
        sy=float(crop.shape[0])/max(1,img.shape[0]); sx=float(crop.shape[1])/max(1,img.shape[1])
        try:
            data=pytesseract.image_to_data(img,config="--psm 11",output_type=pytesseract.Output.DICT)
        except Exception:
            return [], ""
        words=[]; full=[]
        for i,raw0 in enumerate(data.get("text",[])):
            raw=str(raw0 or "").strip()
            if not raw: continue
            try: conf=float(data.get("conf",[-1])[i])
            except Exception: conf=-1.0
            norm=normalize_daily_word(raw)
            if norm: full.append(norm)
            words.append({
                "raw":raw,"norm":norm,"conf":conf,
                "x":x0+int(round(int(data.get("left",[0])[i])*sx)),
                "y":y0+int(round(int(data.get("top",[0])[i])*sy)),
                "w":int(round(int(data.get("width",[0])[i])*sx)),
                "h":int(round(int(data.get("height",[0])[i])*sy)),
                "block":int(data.get("block_num",[0])[i]),"par":int(data.get("par_num",[0])[i]),"line":int(data.get("line_num",[0])[i]),
            })
        allowed=[normalize_daily_word(x) for x in allowed]
        actions=[]; lines={}
        for w in words:
            lines.setdefault((w["block"],w["par"],w["line"]),[]).append(w)
        for line_words in lines.values():
            line_words.sort(key=lambda z:z["x"])
            norms=[x["norm"] for x in line_words if x["norm"]]
            line_text=" ".join(norms)
            if "CLAIM ALL" in allowed:
                for i,w in enumerate(line_words[:-1]):
                    n=line_words[i+1]
                    if w["norm"]=="CLAIM" and n["norm"]=="ALL" and _daily_button_candidate(w) and _daily_button_candidate(n):
                        if abs((w["y"]+w["h"]/2)-(n["y"]+n["h"]/2))<18 and n["x"]-(w["x"]+w["w"])<45:
                            x1=min(w["x"],n["x"]); y1=min(w["y"],n["y"]); x2=max(w["x"]+w["w"],n["x"]+n["w"]); y2=max(w["y"]+w["h"],n["y"]+n["h"])
                            actions.append({"label":"CLAIM ALL","x":(x1+x2)//2,"y":(y1+y2)//2,"conf":min(w["conf"],n["conf"]),"source":"ROI OCR"})
            for w in line_words:
                if not _daily_button_candidate(w): continue
                if w["norm"]=="CLAIM" and "CLAIM" in allowed and "CLAIM ALL" not in line_text:
                    actions.append({"label":"CLAIM","x":w["x"]+w["w"]//2,"y":w["y"]+w["h"]//2,"conf":w["conf"],"source":"ROI OCR"})
                elif w["norm"]=="FREE" and "FREE" in allowed:
                    if len([z for z in norms if z]) <= 2:
                        actions.append({"label":"FREE","x":w["x"]+w["w"]//2,"y":w["y"]+w["h"]//2,"conf":w["conf"],"source":"ROI OCR"})
        return self._vision_nms(actions), " ".join(full)

    def _vision_match_actions(self, ref, allowed, screen="UNKNOWN", allow_roi_fallback=True):
        # Fast path: OpenCV finds candidate buttons in a few ms; one compact
        # Tesseract batch only confirms exact safe words.
        boxes=self._vision_candidate_boxes(ref,screen)
        actions=self._vision_ocr_candidate_batch(ref,boxes,allowed)
        full_text=""
        if not actions and allow_roi_fallback and HAS_TESSERACT and screen not in ("HOME","CHAIN","IDLE_POPUP","REWARD_OVERLAY"):
            roi=VISION_ACTION_ROIS.get(screen,VISION_ACTION_ROIS["UNKNOWN"])
            actions,full_text=self._vision_ocr_region(ref,roi,allowed)
        return actions,full_text,len(boxes)

    def _vision_analyze_frame(self, ref, allowed=None, allow_ocr_fallback=False):
        started=time.perf_counter()
        allowed=list(allowed or ["CLAIM ALL","CLAIM","FREE"])
        screen,screen_conf,detail=self._vision_identify_screen(ref)
        sig=self._vision_frame_signature(ref)
        cache_key=(screen,sig,tuple(sorted(normalize_daily_word(x) for x in allowed)),bool(allow_ocr_fallback))
        cached=getattr(self,"vision_analysis_cache",None)
        if cached and cached.get("key")==cache_key and time.monotonic()-float(cached.get("at",0))<0.75:
            result=dict(cached.get("result") or {})
            result["actions"]=[dict(x) for x in result.get("actions",[])]
            result["scan_ms"]=(time.perf_counter()-started)*1000.0
            result["cached"]=True
            return result
        overlay=screen=="REWARD_OVERLAY"
        actions=[]; full_text=""; candidate_count=0
        if not overlay:
            actions,full_text,candidate_count=self._vision_match_actions(ref,allowed,screen,allow_roi_fallback=bool(allow_ocr_fallback))
        elapsed=(time.perf_counter()-started)*1000.0
        result={
            "screen":screen,"screen_conf":screen_conf,"screen_detail":detail,
            "actions":actions,"overlay":overlay,"scan_ms":elapsed,
            "used_ocr":bool(actions or full_text),"full_text":full_text,
            "candidate_count":candidate_count,"cached":False,
        }
        self.vision_analysis_cache={"key":cache_key,"at":time.monotonic(),"result":dict(result)}
        return result

    def _vision_annotate(self, ref, result):
        img=ref.copy()
        for a in result.get("actions",[]):
            box=a.get("box")
            if box:
                x1,y1,x2,y2=[int(v) for v in box]
            else:
                x,y=int(a.get("x",0)),int(a.get("y",0)); x1,y1,x2,y2=x-55,y-24,x+55,y+24
            cv2.rectangle(img,(x1,y1),(x2,y2),(0,255,0),2)
            cv2.putText(img,f"{a.get('label')} {a.get('conf',0):.0f}%",(max(2,x1),max(18,y1-6)),cv2.FONT_HERSHEY_SIMPLEX,0.55,(0,255,0),2,cv2.LINE_AA)
        cv2.putText(img,f"SCREEN: {result.get('screen')} {result.get('screen_conf',0):.0f}%",(18,30),cv2.FONT_HERSHEY_SIMPLEX,0.72,(255,220,90),2,cv2.LINE_AA)
        return img

    def open_vision_inspector(self):
        if hasattr(self,"dashboard_main"):
            self.dashboard_main.grid_remove()
        for name in ("history_page","diagnostics_page","intelligence_page","strategy_page","daily_page"):
            p=getattr(self,name,None)
            if p is not None:
                try:p.grid_remove()
                except Exception:pass
        if self.vision_page is not None:
            try:self.vision_page.destroy()
            except Exception:pass
        page=tk.Frame(self.shell,bg=UI_BG)
        page.grid(row=0,column=1,sticky="nsew")
        page.grid_columnconfigure(0,weight=1); page.grid_rowconfigure(2,weight=1)
        self.vision_page=page; self.vision_vars={}
        self._set_active_nav("vision")
        header=tk.Frame(page,bg=UI_BG); header.grid(row=0,column=0,sticky="ew",padx=26,pady=(24,14)); header.grid_columnconfigure(0,weight=1)
        left=tk.Frame(header,bg=UI_BG); left.grid(row=0,column=0,sticky="w")
        self._label(left,"Vision Inspector",bg=UI_BG,size=18,weight="bold").pack(anchor="w")
        self._label(left,"Live screen identity + safe buttons • OpenCV candidate isolation • compact OCR confirmation",bg=UI_BG,fg=UI_MUTED,size=9).pack(anchor="w",pady=(3,0))
        buttons=tk.Frame(header,bg=UI_BG); buttons.grid(row=0,column=1,sticky="e")
        self._action_button(buttons,"SCAN NOW",self.vision_scan_now,accent=True).pack(side="left",padx=(0,7))
        self._action_button(buttons,"LIVE ON/OFF",self.toggle_vision_live).pack(side="left")

        stat_card,stat=self._make_card(page,padx=14,pady=11); stat_card.grid(row=1,column=0,sticky="ew",padx=26,pady=(0,12))
        row=tk.Frame(stat,bg=UI_CARD); row.pack(fill="x")
        for title,key,color in (("SCREEN","screen",UI_GREEN),("CONFIDENCE","confidence",UI_BLUE),("SCAN","scan",UI_GOLD),("MODE","mode",UI_ACCENT)):
            tile=tk.Frame(row,bg=UI_TILE,padx=10,pady=9); tile.pack(side="left",fill="x",expand=True,padx=(0,6))
            self._label(tile,title,bg=UI_TILE,fg=UI_MUTED,size=7).pack(anchor="w")
            self._label(tile,textvariable=self._vision_var(key),bg=UI_TILE,fg=color,size=10,weight="bold").pack(anchor="w",pady=(3,0))
        self._label(stat,textvariable=self._vision_var("screen_detail"),bg=UI_CARD,fg=UI_MUTED,size=8).pack(anchor="w",pady=(8,0))

        body=tk.Frame(page,bg=UI_BG); body.grid(row=2,column=0,sticky="nsew",padx=26,pady=(0,20)); body.grid_columnconfigure(0,weight=3); body.grid_columnconfigure(1,weight=2); body.grid_rowconfigure(0,weight=1)
        preview_card,preview=self._make_card(body,padx=10,pady=10); preview_card.grid(row=0,column=0,sticky="nsew",padx=(0,7))
        self._label(preview,"LIVE PHONE VIEW",bg=UI_CARD,fg=UI_MUTED,size=8,weight="bold").pack(anchor="w",pady=(0,8))
        self.vision_preview_label=tk.Label(preview,bg=UI_TILE,bd=0); self.vision_preview_label.pack(fill="both",expand=True)
        action_card,action=self._make_card(body,padx=12,pady=10); action_card.grid(row=0,column=1,sticky="nsew",padx=(7,0))
        self._label(action,"SAFE ACTIONS",bg=UI_CARD,size=10,weight="bold").pack(anchor="w")
        self._label(action,"Only exact CLAIM / CLAIM ALL / FREE labels can become tap targets.",bg=UI_CARD,fg=UI_MUTED,size=8,wraplength=340,justify="left").pack(anchor="w",pady=(3,8))
        self.vision_actions_text=tk.Text(action,bg=UI_TILE,fg=UI_MUTED,relief="flat",bd=0,highlightthickness=0,font=("Consolas",8),wrap="word")
        self.vision_actions_text.pack(fill="both",expand=True); self.vision_actions_text.config(state="disabled")
        self._vision_var("mode").set("IDLE")

    def _vision_apply_result(self, ref, result, age_ms=None):
        self.vision_last_result=result
        self._vision_var("screen").set(str(result.get("screen") or "UNKNOWN"))
        self._vision_var("confidence").set(f"{float(result.get('screen_conf',0)):.0f}%")
        self._vision_var("scan").set(f"{float(result.get('scan_ms',0)):.0f} ms")
        self._vision_var("screen_detail").set(f"{result.get('screen_detail','')} • candidates {result.get('candidate_count',0)}" + (f" • frame {float(age_ms):.0f}ms" if age_ms is not None else ""))
        if self.vision_actions_text is not None:
            lines=[]
            for a in result.get("actions",[]):
                lines.append(f"{a.get('label')}  {float(a.get('conf',0)):.0f}%  @ {int(a.get('x',0))},{int(a.get('y',0))}  [{a.get('source','?')}]")
            if result.get("overlay"): lines.append("REWARD OVERLAY • safe neutral dismiss")
            if not lines: lines=["No safe action detected."]
            self.vision_actions_text.config(state="normal"); self.vision_actions_text.delete("1.0","end"); self.vision_actions_text.insert("1.0","\n".join(lines)); self.vision_actions_text.config(state="disabled")
        try:
            annotated=self._vision_annotate(ref,result)
            h,w=annotated.shape[:2]; target_w=700; target_h=max(1,int(h*target_w/w))
            preview=cv2.resize(annotated,(target_w,target_h),interpolation=cv2.INTER_AREA)
            ok,buf=cv2.imencode(".png",preview)
            if ok and self.vision_preview_label is not None:
                data=base64.b64encode(buf.tobytes()).decode("ascii")
                photo=tk.PhotoImage(data=data); self.vision_preview_photo=photo; self.vision_preview_label.config(image=photo)
        except Exception:
            pass

    def vision_scan_now(self, live=False):
        if self.vision_scan_thread is not None and self.vision_scan_thread.is_alive():
            return
        self._vision_var("mode").set("LIVE" if self.vision_live else "SCANNING")
        def worker():
            try:
                dev=get_device()
                if dev is None: raise RuntimeError("No ADB device connected")
                self.engine.device=dev; self._daily_prepare_transport(dev)
                age=None; vision=getattr(self,"daily_vision",None)
                if vision is not None and getattr(vision,"running",False):
                    ref,age,_=vision.get_latest()
                    if ref is None: ref=self._phone_reference_screenshot()
                    else: ref=ref.copy()
                else:
                    ref=self._phone_reference_screenshot()
                result=self._vision_analyze_frame(ref,allow_ocr_fallback=not live)
                self.root.after(0,lambda r=ref,res=result,a=age:self._vision_apply_result(r,res,a))
            except Exception as e:
                self.root.after(0,lambda msg=str(e):self._vision_var("screen_detail").set(msg))
            finally:
                if self.vision_live:
                    self.root.after(VISION_LIVE_INTERVAL_MS,self.vision_scan_now,True)
                else:
                    self.root.after(0,lambda:self._vision_var("mode").set("IDLE"))
        self.vision_scan_thread=threading.Thread(target=worker,daemon=True); self.vision_scan_thread.start()

    def toggle_vision_live(self):
        self.vision_live=not bool(self.vision_live)
        self._vision_var("mode").set("LIVE" if self.vision_live else "IDLE")
        if self.vision_live:
            self.vision_scan_now(True)

    def open_daily_assistant(self):
        for name in ("history_page", "diagnostics_page", "intelligence_page", "strategy_page", "vision_page"):
            page = getattr(self, name, None)
            if page is not None:
                try: page.grid_remove()
                except Exception: pass
        if hasattr(self, "dashboard_main"):
            self.dashboard_main.grid_remove()
        if self.daily_page is not None:
            try: self.daily_page.destroy()
            except Exception: pass

        page = tk.Frame(self.shell, bg=UI_BG)
        page.grid(row=0, column=1, sticky="nsew")
        page.grid_columnconfigure(0, weight=1)
        self.daily_page = page
        # Preserve module StringVars when reopening the page so a running
        # worker never loses the variables its cards are bound to.
        if not hasattr(self, "daily_module_vars") or self.daily_module_vars is None:
            self.daily_module_vars = {}
        self._set_active_nav("daily")

        header = tk.Frame(page, bg=UI_BG)
        header.pack(fill="x", padx=26, pady=(24, 14))
        self._label(header, "Daily Assistant", bg=UI_BG, size=18, weight="bold").pack(anchor="w")
        self._label(header, "Modular collectors • only explicit CLAIM / CLAIM ALL / FREE actions", bg=UI_BG, fg=UI_MUTED, size=9).pack(anchor="w", pady=(3,0))

        safe, safe_inner = self._make_card(page, padx=16, pady=14)
        safe.pack(fill="x", padx=26, pady=(0, 12))
        safe_top = tk.Frame(safe_inner, bg=UI_CARD)
        safe_top.pack(fill="x")
        self._label(safe_top, "SAFE MODE", bg=UI_CARD, fg=UI_GREEN, size=9, weight="bold").pack(side="left")
        self._action_button(safe_top, "RUN ALL SAFE", self.run_all_safe).pack(side="right")
        self._action_button(safe_top, "STOP ALL", lambda:self.stop_daily_module(None)).pack(side="right", padx=(0,6))
        self._label(safe_inner, "Only explicit CLAIM / CLAIM ALL / FREE actions. BUY, EXCHANGE, USE, SWEEP, START, GO NOW and spend buttons are never action targets.", bg=UI_CARD, fg=UI_MUTED, size=8).pack(anchor="w", pady=(4,0))
        self._label(safe_inner, "V7.2 Vision-First: screen fingerprints + OpenCV button isolation + compact OCR confirmation. Home return stays verified/retried.", bg=UI_CARD, fg=UI_MUTED_2, size=8).pack(anchor="w", pady=(2,0))
        self._label(safe_inner, textvariable=self.daily_summary_var, bg=UI_CARD, fg=UI_GREEN, size=8, weight="bold").pack(anchor="w", pady=(5,0))
        self._label(safe_inner, textvariable=self.daily_debug_var, bg=UI_CARD, fg=UI_BLUE, size=8).pack(anchor="w", pady=(2,0))

        body = tk.Frame(page, bg=UI_BG)
        body.pack(fill="both", expand=True, padx=26, pady=(0, 20))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        modules = [
            ("Mail", "Mail", "Claim all inbox rewards", "CLAIM only"),
            ("Events", "Events", "Collect visible event rewards", "CLAIM / FREE"),
            ("Shop", "Shop", "Daily Deal + literal FREE offers", "No currency spending"),
            ("Recruit", "Recruit", "Regular Recruit free pull only", "Never tickets / gems"),
            ("Quest Pass", "Quest Pass", "Daily / weekly pass reward claims", "CLAIM only"),
            ("Idle Rewards", "Idle Rewards", "Chain Campaign idle farming claim", "CLAIM only"),
            ("Login", "Login / Sign-in", "Rotating login/sign-in reward page", "Teach current event route"),
            ("Current Screen", "Current Screen", "Safe-scan whatever screen is open", "No navigation"),
        ]
        cfg_routes = (get_daily_settings().get("routes") or {})
        for i,(name,title,desc,rule) in enumerate(modules):
            route_ready = name == "Current Screen" or bool(cfg_routes.get(name))
            default_state = "READY" if route_ready else "NEEDS ROUTE"
            card, card_body = self._make_card(body, padx=14, pady=12)
            card.grid(row=i//2, column=i%2, sticky="nsew", padx=(0,7) if i%2==0 else (7,0), pady=7)
            top=tk.Frame(card_body,bg=UI_CARD); top.pack(fill="x", pady=(0,5))
            self._label(top,title,bg=UI_CARD,size=11,weight="bold").pack(side="left")
            self._label(top,textvariable=self._daily_var(name,default_state),bg=UI_CARD,fg=UI_GREEN if route_ready else UI_AMBER,size=8,weight="bold").pack(side="right")
            self._label(card_body,desc,bg=UI_CARD,fg=UI_MUTED,size=8).pack(anchor="w")
            self._label(card_body,rule,bg=UI_CARD,fg=UI_MUTED_2,size=8).pack(anchor="w",pady=(2,8))
            actions=tk.Frame(card_body,bg=UI_CARD); actions.pack(fill="x")
            self._action_button(actions,"START",lambda n=name:self.start_daily_module(n,False)).pack(side="left")
            self._action_button(actions,"DRY RUN",lambda n=name:self.start_daily_module(n,True)).pack(side="left",padx=(6,0))
            if name != "Current Screen":
                self._action_button(actions,"TEACH",lambda n=name:self.teach_daily_route(n)).pack(side="left",padx=(6,0))
            self._action_button(actions,"STOP",lambda n=name:self.stop_daily_module(n)).pack(side="right")

        footer=tk.Frame(page,bg=UI_BG); footer.pack(fill="x",padx=26,pady=(0,20))
        self._action_button(footer,"OPEN DEBUG FOLDER",self.open_daily_debug_folder).pack(side="left")
        self._label(footer,"7.2: vision-first routing + compact safe-action OCR + live Vision Inspector.",bg=UI_BG,fg=UI_MUTED_2,size=8).pack(side="left",padx=12)

    def teach_daily_route(self, module):
        if self.engine.running:
            messagebox.showwarning("Stop grinder first", "Stop Arena grinding before teaching Daily routes.")
            return
        cfg=get_daily_settings(); old=list((cfg.get("routes") or {}).get(module) or [])
        count=simpledialog.askinteger("Teach Daily Route", f"How many taps are needed from HOME to open {module}?", initialvalue=max(1,len(old)), minvalue=1, maxvalue=5, parent=self.root)
        if not count: return
        points=[]
        def pick_next():
            if len(points)>=count:
                with daily_settings_lock:
                    daily_settings.setdefault("routes",{})[module]=points
                save_daily_settings()
                self._daily_var(module).set("READY")
                self.add_log(f"Daily route taught: {module} • {len(points)} tap(s)")
                return
            try: ref=self._phone_reference_screenshot()
            except Exception as e:
                messagebox.showerror("Daily Route", str(e)); return
            idx=len(points)+1
            def save_point(x,y):
                points.append([int(x),int(y)])
                # If the route needs multiple screens, perform the tap now so
                # the next picker sees the next screen exactly as the user would.
                try:
                    self.engine._tap_reference(x,y)
                except Exception:
                    pass
                # Do not block Tk's UI thread while waiting for the next screen.
                self.root.after(260, pick_next)
            self._show_point_picker(ref,"Teach Daily Route",f"Step {idx}/{count}: click the button that advances from HOME toward {module}.",save_point)
        pick_next()

    def open_daily_debug_folder(self):
        try:
            path = self._daily_debug_dir()
            if os.name == "nt":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:
            messagebox.showerror("Daily Debug", str(e))

    def stop_daily_module(self, module=None):
        active = self.daily_active_module
        if module is not None and active not in (None, module):
            self._daily_set_status(module, "IDLE")
            return
        self.daily_stop_event.set()
        if active:
            self._daily_set_status(active, "STOPPING")
            self._daily_set_debug(f"{active}: stop requested")

    def _daily_home_signature(self, ref):
        if not HAS_TESSERACT: return False
        try:
            text=normalize_daily_word(pytesseract.image_to_string(ref,config="--psm 11"))
        except Exception:
            return False
        hits=sum(1 for token in ("COMBAT","PVP","RECRUIT","CAMPAIGN") if token in text)
        return hits>=2

    def _daily_ensure_home(self):
        # V7.0.2 safety rule: Daily modules NEVER send Android Back to find Home.
        # In TG:BTC, Back from Home opens/exits the game, so navigation-to-Home
        # must be user-controlled. We only verify the current screen here.
        if self.daily_stop_event.is_set():
            return False
        try:
            ref = self._phone_reference_screenshot()
            return self._daily_home_signature(ref)
        except Exception:
            return False

    def _daily_dismiss_reward_overlay(self):
        try:
            ref=self._phone_reference_screenshot()
            screen,_,_=self._vision_identify_screen(ref)
            if screen == "REWARD_OVERLAY":
                self._daily_tap_reference(768,620)
                self.add_log("Daily: dismissed Rewards Obtained overlay (vision verified)")
                self._daily_wait_frame_change(ref,timeout=0.60,min_bits=4)
                return True
        except Exception:
            pass
        return False

    def _daily_safe_scan(self, module, max_taps=16, dry_run=False):
        allowed=(get_daily_settings().get("module_words") or {}).get(module,["CLAIM ALL","CLAIM","FREE"])
        interactions=0; empty=0; last=[]
        stats={"actions":0,"claims":0,"free":0,"overlays":0,"detected":0}
        while interactions<max_taps and empty<2 and not self.daily_stop_event.is_set():
            self._daily_check_deadline()
            ref=self._phone_reference_screenshot()
            vision_result=self._vision_analyze_frame(ref,allowed,allow_ocr_fallback=True)
            actions=list(vision_result.get("actions") or [])
            overlay=bool(vision_result.get("overlay"))
            full_text=str(vision_result.get("full_text") or "")
            self._daily_set_debug(f"{module}: {vision_result.get('screen','UNKNOWN')} • {vision_result.get('scan_ms',0):.0f}ms • {len(actions)} safe")

            if dry_run:
                # Pure inspector: never touch the phone.
                found=[]
                if overlay:
                    found.append("reward overlay")
                    self._daily_save_debug_frame(module,"dry_overlay",ref,(768,620),"DISMISS")
                    stats["overlays"] += 1
                for idx,a in enumerate(actions[:8],1):
                    px,py=self._daily_phone_xy(a["x"],a["y"])
                    found.append(f"{a['label']} ref {a['x']},{a['y']} -> phone {px},{py}")
                    self._daily_save_debug_frame(module,f"dry_action_{idx}",ref,(a["x"],a["y"]),a["label"])
                    stats["detected"] += 1
                    if a["label"] in ("CLAIM","CLAIM ALL"):
                        stats["claims"] += 1
                    elif a["label"] == "FREE":
                        stats["free"] += 1
                stats["actions"] = stats["claims"] + stats["free"]
                self.add_log(f"Daily {module} DRY RUN: " + (" | ".join(found) if found else "no safe action detected"))
                self._daily_set_debug(f"{module} DRY RUN • {stats['actions']} safe action(s)" + (" • overlay" if overlay else ""))
                return stats

            if overlay:
                px,py=self._daily_phone_xy(768,620)
                self._daily_set_debug(f"{module}: overlay ref 768,620 -> phone {px},{py}")
                self._daily_save_debug_frame(module,f"before_{interactions+1:02d}_overlay",ref,(768,620),"DISMISS")
                self._daily_tap_reference(768,620); interactions+=1; stats["overlays"]+=1
                self.add_log(f"Daily {module}: dismissed non-spend reward/continue overlay ref 768,620 -> phone {px},{py}")
                self._daily_wait_frame_change(ref, timeout=0.65, min_bits=4)
                empty=0
                continue

            # Avoid hammering an OCR ghost at the same location repeatedly.
            actions=[a for a in actions if not any(abs(a['x']-x)<25 and abs(a['y']-y)<18 for x,y in last[-3:])]
            if not actions:
                # TG:BTC's gold-on-red Idle Farming "Claim" label is unusually
                # poor OCR. Use a fixed tap only after the exact Idle Farming
                # popup itself has been visually verified by pHash.
                if module == "Idle Rewards" and stats.get("claims",0) == 0:
                    idle_ok,idle_detail=self._daily_anchor_check("IDLE_POPUP",ref)
                    if idle_ok:
                        fx,fy=931,598
                        px,py=self._daily_phone_xy(fx,fy)
                        self._daily_set_debug(f"Idle Rewards: verified popup fallback CLAIM ref {fx},{fy} -> phone {px},{py}")
                        self._daily_save_debug_frame(module,f"before_{interactions+1:02d}_CLAIM_FALLBACK",ref,(fx,fy),"CLAIM")
                        self._daily_tap_reference(fx,fy)
                        interactions+=1; stats["actions"]+=1; stats["claims"]+=1; empty=0
                        self.add_log(f"Daily Idle Rewards: verified-popup CLAIM fallback ref {fx},{fy} -> phone {px},{py} • {idle_detail}")
                        self._daily_wait_frame_change(ref, timeout=0.70, min_bits=4)
                        continue
                empty+=1
                self._daily_set_debug(f"{module}: no safe action {empty}/2")
                time.sleep(0.04)
                continue

            a=actions[0]
            px,py=self._daily_phone_xy(a["x"],a["y"])
            self._daily_set_debug(f"{module}: {a['label']} ref {a['x']},{a['y']} -> phone {px},{py}")
            self._daily_save_debug_frame(module,f"before_{interactions+1:02d}_{a['label']}",ref,(a["x"],a["y"]),a["label"])
            self._daily_tap_reference(a["x"],a["y"])
            last.append((a["x"],a["y"])); interactions+=1; empty=0
            stats["actions"] += 1
            if a["label"] in ("CLAIM","CLAIM ALL"):
                stats["claims"] += 1
            elif a["label"] == "FREE":
                stats["free"] += 1
            self.add_log(f"Daily {module}: {a['label']} ref {a['x']},{a['y']} -> phone {px},{py} (OCR {a.get('conf',0):.0f})")
            # React to the first changed Fast-Vision frame instead of sleeping a
            # fixed amount after every action. This is the main V7.1.2 latency
            # win on Wireless ADB.
            self._daily_wait_frame_change(
                ref,
                timeout=0.95 if module == "Recruit" and a["label"] == "FREE" else 0.70,
                min_bits=4,
            )

        return stats

    def _daily_execute_module(self, module, dry_run=False, return_home=True):
        self.daily_active_module=module
        self.daily_dry_run=bool(dry_run)
        self.daily_deadline=time.monotonic()+120.0
        result={"module":module,"status":"ERROR","claims":0,"free":0,"overlays":0,"actions":0,"home_returned":None}
        self._daily_set_status(module,"DRY RUN" if dry_run else "RUNNING")
        try:
            if not HAS_TESSERACT:
                self._daily_set_status(module,"OCR MISSING")
                raise RuntimeError("OCR is required for safe Daily collection. Install OCR from Settings.")
            dev=get_device()
            if dev is None:
                self._daily_set_status(module,"NO ADB")
                raise RuntimeError("No ADB device connected.")

            self.engine.device=dev
            self._daily_set_status(module,"SYNCING")
            self._daily_prepare_transport(dev)
            start_ref=self._phone_reference_screenshot()
            aw=int(getattr(self.engine,"actual_w",REFERENCE_W) or REFERENCE_W)
            ah=int(getattr(self.engine,"actual_h",REFERENCE_H) or REFERENCE_H)
            self._daily_set_debug(f"Phone {aw}x{ah} • reference {REFERENCE_W}x{REFERENCE_H}")
            self.add_log(f"Daily {module}: device geometry {aw}x{ah}")
            self._daily_save_debug_frame(module,"00_start",start_ref)

            if module != "Current Screen":
                route=(get_daily_settings().get("routes") or {}).get(module) or []
                if not route:
                    self._daily_set_status(module,"NEEDS ROUTE")
                    raise RuntimeError(f"{module} has no route yet. Click TEACH once.")

                home_ok,home_detail=self._daily_anchor_check("HOME",start_ref)
                self.add_log(f"Daily {module}: HOME verification {'OK' if home_ok else 'FAILED'} • {home_detail}")
                if not home_ok:
                    self._daily_save_debug_frame(module,"00_not_home",start_ref)
                    self._daily_set_status(module,"OPEN HOME")
                    raise RuntimeError(f"Home screen could not be visually verified ({home_detail}). Open Home and retry.")

                if dry_run:
                    self._daily_preview_route(module,route,start_ref)
                    self._daily_set_status(module,f"DRY • {len(route)} ROUTE TAP" + ("S" if len(route)!=1 else ""))
                    self._daily_set_debug(f"{module}: route preview only • 0 phone taps")
                    result["status"]="DRY"
                    return result

                expectations=list(DAILY_ROUTE_EXPECTATIONS.get(module) or [])
                last_verified_anchor=None
                last_after=start_ref
                for step,(x,y) in enumerate(route,1):
                    self._daily_check_deadline()
                    if self.daily_stop_event.is_set():
                        result["status"]="STOPPED"
                        return result
                    before=self._phone_reference_screenshot()
                    px,py=self._daily_phone_xy(x,y)
                    self._daily_set_debug(f"{module}: route {step}/{len(route)} ref {int(x)},{int(y)} -> phone {px},{py}")
                    self._daily_save_debug_frame(module,f"route_{step:02d}_before",before,(x,y),f"ROUTE {step}")
                    self._daily_tap_reference(float(x),float(y))
                    self.add_log(f"Daily {module}: route {step}/{len(route)} ref {int(x)},{int(y)} -> phone {px},{py}")

                    changed,after=self._daily_wait_frame_change(before,timeout=DAILY_ROUTE_CHANGE_TIMEOUT,min_bits=4)
                    if not changed:
                        # One immediate retry handles a swallowed Wireless ADB tap
                        # without forcing the user to restart the whole module.
                        self.add_log(f"Daily {module}: route {step} had no visual change; retrying tap once")
                        self._daily_tap_reference(float(x),float(y))
                        changed,after=self._daily_wait_frame_change(before,timeout=0.55,min_bits=4)
                    last_after=after if after is not None else before

                    expected=expectations[step-1] if step-1 < len(expectations) else None
                    if expected:
                        ok,detail=self._daily_anchor_check(expected,last_after)
                        if not ok:
                            ok,detail,last_after=self._daily_wait_anchor(expected,timeout=0.85,initial_ref=last_after)
                        self.add_log(f"Daily {module}: route step {step} expected {expected} • {'OK' if ok else 'FAILED'} • {detail}")
                        if not ok:
                            self._daily_save_debug_frame(module,f"route_{step:02d}_failed",last_after)
                            self._daily_set_status(module,f"ROUTE FAIL • {step}")
                            raise RuntimeError(f"Route verification failed at step {step}: expected {expected} ({detail})")
                        last_verified_anchor=expected

                final_anchor=DAILY_FINAL_ANCHOR.get(module)
                if final_anchor:
                    if last_verified_anchor == final_anchor:
                        ok=True; detail="already verified on final route step"; final_ref=last_after
                    else:
                        ok,detail,final_ref=self._daily_wait_anchor(final_anchor,timeout=1.0,initial_ref=last_after)
                    if not ok:
                        if final_ref is not None:
                            self._daily_save_debug_frame(module,"destination_failed",final_ref)
                        self._daily_set_status(module,"DESTINATION FAIL")
                        raise RuntimeError(f"Could not verify {module} destination ({detail})")
                    self._daily_set_debug(f"{module}: destination verified • {final_anchor}")

            self._daily_set_status(module,"DRY RUN" if dry_run else "SCANNING")
            self._daily_check_deadline()
            stats=self._daily_safe_scan(module,dry_run=dry_run)

            # V7.1 module-aware safe traversal. Navigation taps are only made
            # inside a screen whose stable anchor was just verified. Content
            # taps still require literal CLAIM / CLAIM ALL / FREE OCR.
            if not dry_run and module == "Shop" and not self.daily_stop_event.is_set():
                for tab_name,(tx,ty) in DAILY_SHOP_SCAN_TABS[1:]:
                    current=self._phone_reference_screenshot()
                    self._daily_set_debug(f"Shop: inspect {tab_name}")
                    self._daily_tap_reference(float(tx),float(ty))
                    _,changed_ref=self._daily_wait_frame_change(current,timeout=0.60,min_bits=3)
                    check_ref=changed_ref if changed_ref is not None else self._phone_reference_screenshot()
                    ok,detail=self._daily_anchor_check("SHOP",check_ref)
                    if not ok:
                        self.add_log(f"Daily Shop: {tab_name} anchor lost • {detail}")
                        break
                    extra=self._daily_safe_scan(module,dry_run=False)
                    self._daily_merge_stats(stats,extra)
                    if self.daily_stop_event.is_set(): break

            if not dry_run and module == "Quest Pass" and not self.daily_stop_event.is_set():
                # Tab switches stay inside the already-verified Quest Pass page.
                # Wait for the first changed streamed frame instead of repeatedly
                # OCR-verifying the same header.
                for tab_name,(tx,ty) in DAILY_QUEST_SCAN_TABS:
                    current=self._phone_reference_screenshot()
                    self._daily_set_debug(f"Quest Pass: inspect {tab_name}")
                    self._daily_tap_reference(float(tx),float(ty))
                    _,changed_ref=self._daily_wait_frame_change(current,timeout=0.60,min_bits=3)
                    check_ref=changed_ref if changed_ref is not None else self._phone_reference_screenshot()
                    ok,detail=self._daily_anchor_check("QUEST",check_ref)
                    if not ok:
                        self.add_log(f"Daily Quest Pass: {tab_name} anchor lost • {detail}")
                        break
                    extra=self._daily_safe_scan(module,dry_run=False)
                    self._daily_merge_stats(stats,extra)
                    if self.daily_stop_event.is_set(): break

            result.update(stats)
            if self.daily_stop_event.is_set():
                result["status"]="STOPPED"
                self._daily_set_status(module,"STOPPED")
                return result
            if dry_run:
                result["status"]="DRY"
                self._daily_set_status(module,f"DRY • {stats['actions']} FOUND")
                return result

            # Recruit is intentionally last in RUN ALL. If a free pull launches
            # the summon/result flow, do not guess a way out of that screen.
            should_return = bool(return_home and module != "Current Screen")
            if module == "Recruit" and stats.get("free",0) > 0:
                should_return=False
                self.add_log("Daily Recruit: free pull used; leaving recruit/result flow untouched")

            if should_return:
                self._daily_set_status(module,"RETURNING HOME")
                home_ok=self._daily_return_home(module)
                result["home_returned"]=bool(home_ok)
                if not home_ok:
                    result["status"]="HOME_FAIL"
                    self._daily_set_status(module,"DONE • HOME FAIL")
                    self._daily_set_debug(f"{module}: safe actions done, but Home verification failed")
                    return result
            elif module != "Current Screen":
                result["home_returned"]=None

            result["status"]="DONE"
            c=int(stats.get("claims",0)); f=int(stats.get("free",0))
            if c or f:
                parts=[]
                if c: parts.append(f"{c} CLAIM")
                if f: parts.append(f"{f} FREE")
                self._daily_set_status(module,"DONE • " + " / ".join(parts))
            else:
                self._daily_set_status(module,"DONE • 0 SAFE")
            self.add_log(f"Daily {module}: finished • claims={c} free={f} overlays={stats.get('overlays',0)}")
            self._daily_set_debug(f"{module}: DONE • {c} claim / {f} free")
            return result
        finally:
            self.daily_deadline=0.0
            self.daily_dry_run=False

    def _daily_module_worker(self,module,dry_run=False):
        started=time.monotonic()
        try:
            result=self._daily_execute_module(module,bool(dry_run),return_home=not bool(dry_run))
            self.daily_last_results[module]=result
            self._daily_set_summary(self._daily_summary_text([result],time.monotonic()-started))
            self._daily_write_run_log({"time":datetime.now().isoformat(timespec="seconds"),"type":"single","dry_run":bool(dry_run),"results":[result]})
        except TimeoutError as e:
            self._daily_set_status(module,"TIMEOUT")
            self._daily_set_debug(f"{module}: watchdog stopped run after 120s")
            self.add_log(f"Daily {module} watchdog: {e}")
        except Exception as e:
            msg=str(e)
            if "no route" not in msg.lower() and "OCR is required" not in msg and "No ADB" not in msg and "Home screen" not in msg and "Route verification" not in msg:
                short=msg.upper()
                if len(short)>28: short=short[:25]+"..."
                self._daily_set_status(module,short)
            self._daily_set_debug(f"{module}: {msg}")
            self.add_log(f"Daily {module} error: {msg}")
            try:self.root.after(0,lambda m=msg:messagebox.showerror("Daily Assistant",m))
            except Exception:pass
        finally:
            self.daily_active_module=None

    def _daily_run_all_worker(self):
        started=time.monotonic()
        results=[]
        self.daily_run_all_active=True
        self._daily_set_summary("RUN ALL SAFE • starting…")
        try:
            cfg=get_daily_settings(); routes=cfg.get("routes") or {}
            for idx,module in enumerate(DAILY_RUN_ALL_ORDER,1):
                if self.daily_stop_event.is_set():
                    break
                route=routes.get(module) or []
                if not route:
                    skipped={"module":module,"status":"SKIPPED","claims":0,"free":0,"overlays":0,"actions":0,"reason":"no route"}
                    results.append(skipped)
                    self._daily_set_status(module,"SKIPPED • NO ROUTE")
                    continue
                self._daily_set_summary(f"RUN ALL SAFE • {idx}/{len(DAILY_RUN_ALL_ORDER)} • {module}")
                try:
                    # Recruit runs last and may deliberately leave the summon
                    # result flow open after a successful free pull.
                    result=self._daily_execute_module(module,False,return_home=(module != "Recruit"))
                    results.append(result)
                    self.daily_last_results[module]=result
                except TimeoutError as e:
                    result={"module":module,"status":"TIMEOUT","claims":0,"free":0,"overlays":0,"actions":0,"reason":str(e)}
                    results.append(result); self._daily_set_status(module,"TIMEOUT"); break
                except Exception as e:
                    msg=str(e)
                    result={"module":module,"status":"ERROR","claims":0,"free":0,"overlays":0,"actions":0,"reason":msg}
                    results.append(result)
                    self._daily_set_status(module,"ROUTE/SCAN ERROR")
                    self._daily_set_debug(f"RUN ALL stopped at {module}: {msg}")
                    self.add_log(f"Daily RUN ALL stopped at {module}: {msg}")
                    break

                if result.get("status") not in ("DONE",):
                    self._daily_set_debug(f"RUN ALL stopped at {module}: {result.get('status')}")
                    break
                if module != "Recruit" and result.get("home_returned") is False:
                    self._daily_set_debug(f"RUN ALL stopped: {module} could not return Home")
                    break

            elapsed=time.monotonic()-started
            text=self._daily_summary_text(results,elapsed)
            self._daily_set_summary(text)
            self._daily_write_run_log({"time":datetime.now().isoformat(timespec="seconds"),"type":"run_all","elapsed_s":round(elapsed,2),"results":results})
            self.add_log("Daily RUN ALL summary: "+text)
        finally:
            self.daily_run_all_active=False
            self.daily_active_module=None
            self.daily_deadline=0.0

    def run_all_safe(self):
        if self.engine.running:
            messagebox.showwarning("Arena is running","Stop Arena grinding before running Daily Assistant.")
            return
        if self.daily_runner_thread is not None and self.daily_runner_thread.is_alive():
            messagebox.showinfo("Daily Assistant","Another Daily module is already running.")
            return
        self.daily_stop_event.clear()
        self.daily_runner_thread=threading.Thread(target=self._daily_run_all_worker,daemon=True,name="daily-run-all-safe")
        self.daily_runner_thread.start()

    def start_daily_module(self,module,dry_run=False):
        if self.engine.running:
            messagebox.showwarning("Arena is running","Stop Arena grinding before running a Daily module.")
            return
        if self.daily_runner_thread is not None and self.daily_runner_thread.is_alive():
            messagebox.showinfo("Daily Assistant","Another Daily module is already running.")
            return
        self.daily_stop_event.clear()
        self.daily_runner_thread=threading.Thread(
            target=self._daily_module_worker,args=(module,bool(dry_run)),
            daemon=True,name=f"daily-{module}-{'dry' if dry_run else 'run'}"
        )
        self.daily_runner_thread.start()

    def open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("Settings & Tools")
        win.transient(self.root)
        win.resizable(False, False)

        frame = ttk.Frame(win, padding=14)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Tools", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )

        buttons = [
            ("Daily Assistant", self.open_daily_assistant),
            ("Opponent Intelligence", self.open_intelligence),
            ("Battle Strategy", self.open_strategy),
            ("Set Rank / Points", self.set_rank_points_manual),
            ("Test OCR", self.test_ocr),
            ("Install OCR", self.install_ocr),
            ("Install Fast Vision", self.install_fast_vision),
            ("Open Profile Folder", self.open_profile),
            ("Check for Updates", self.check_updates_manual),
            ("Update Source", self.configure_update_source),
        ]

        for i, (label, command) in enumerate(buttons):
            ttk.Button(frame, text=label, command=command, width=24).grid(
                row=1 + i // 2,
                column=i % 2,
                padx=4,
                pady=4,
                sticky="ew"
            )

        ttk.Label(
            frame,
            textvariable=self.ocr_live_var,
            font=("Segoe UI", 8)
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(12, 0))

        ttk.Label(
            frame,
            textvariable=self.update_status_var,
            font=("Segoe UI", 8)
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(4, 0))

    def open_dodge_calibration(self):
        win = tk.Toplevel(self.root)
        win.title("Smart Dodge Calibration")
        win.transient(self.root)
        win.resizable(False, False)

        frame = ttk.Frame(win, padding=14)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="Owl of Readiness",
            font=("Segoe UI", 12, "bold")
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        ttk.Checkbutton(
            frame,
            text="Enable Smart Dodge",
            variable=self.dodge_enabled_var,
            command=self.save_dodge_ui
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))

        actions = [
            ("Add Owl Sample", self.capture_owl_sample),
            ("Test Owl Detection", self.test_owl_detection),
            ("Set Quit Point", lambda: self.capture_dodge_point("quit_ref")),
            ("Set Confirm Point", lambda: self.capture_dodge_point("confirm_ref")),
            ("Clear Owl Samples", self.clear_owl_samples),
        ]

        for i, (label, command) in enumerate(actions):
            ttk.Button(frame, text=label, command=command, width=24).grid(
                row=2 + i // 2,
                column=i % 2,
                padx=4,
                pady=4,
                sticky="ew"
            )

        ttk.Label(
            frame,
            textvariable=self.dodge_calibration_var,
            font=("Segoe UI", 9)
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(12, 0))

    # ==========================================================
    # BUILT-IN UPDATER
    # ==========================================================
    def configure_update_source(self):
        win = tk.Toplevel(self.root)
        win.title("Update Source")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        frame = ttk.Frame(win, padding=14)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="GitHub Releases repository"
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        ttk.Label(
            frame,
            text="Enter owner/repo or a github.com URL."
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 10))

        repo_var = tk.StringVar(value=update_settings.get("github_repo", ""))
        entry = ttk.Entry(frame, textvariable=repo_var, width=48)
        entry.grid(row=2, column=0, columnspan=2, sticky="ew")

        auto_var = tk.BooleanVar(
            value=bool(update_settings.get("auto_check", True))
        )
        ttk.Checkbutton(
            frame,
            text="Check automatically when app starts",
            variable=auto_var
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))

        def save():
            repo = normalize_github_repo(repo_var.get())
            if repo_var.get().strip() and not repo:
                messagebox.showerror(
                    "Invalid Repository",
                    "Use owner/repo or https://github.com/owner/repo"
                )
                return

            with update_settings_lock:
                update_settings["github_repo"] = repo
                update_settings["auto_check"] = bool(auto_var.get())
            save_update_settings()

            self.add_log(
                f"Update source: {repo or 'not configured'}"
            )
            self.update_status_var.set(
                f"v{APP_VERSION} | "
                + (f"Updates: {repo}" if repo else "Updates: not configured")
            )

            win.grab_release()
            win.destroy()

        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="CANCEL", command=win.destroy).pack(side="right")
        ttk.Button(buttons, text="SAVE", command=save).pack(
            side="right", padx=(0, 8)
        )

        entry.focus_set()

    def check_updates_manual(self):
        self._check_updates(manual=True)

    def auto_check_updates(self):
        if update_settings.get("auto_check") and update_settings.get("github_repo"):
            self._check_updates(manual=False)

    def _check_updates(self, manual=False):
        repo = update_settings.get("github_repo", "")

        if not repo:
            self.update_status_var.set(f"v{APP_VERSION} | Updates: not configured")
            if manual:
                if messagebox.askyesno(
                    "Updates Not Configured",
                    "No GitHub update source is configured yet.\n\n"
                    "Configure it now?"
                ):
                    self.configure_update_source()
            return

        self.set_update_indicator("checking")
        if manual:
            self.add_log(f"Checking GitHub Release + main: {repo}")

        def worker():
            try:
                release = check_github_latest(repo)
                self.root.after(
                    0,
                    lambda: self._handle_update_result(release, manual)
                )
            except Exception as e:
                self.root.after(
                    0,
                    lambda err=str(e): self._handle_update_error(err, manual)
                )

        threading.Thread(target=worker, daemon=True).start()

    def _handle_update_error(self, error, manual):
        self.set_update_indicator("error")
        self.add_log(f"Update check failed: {error}")
        if manual:
            messagebox.showerror("Update Check", error)

    def _handle_update_result(self, release, manual):
        latest = release["version"]

        if version_tuple(latest) <= version_tuple(APP_VERSION):
            self.latest_release = None
            self.update_available = False
            self.set_update_indicator("idle")
            if manual:
                messagebox.showinfo(
                    "Updates",
                    f"You are up to date.\n\nInstalled: v{APP_VERSION}\n"
                    f"Latest: v{latest}"
                )
            return

        # Startup checks are intentionally silent.  The header icon turns
        # amber and gains a red notification badge.  The user chooses when
        # to open/install it.
        self.latest_release = release
        self.update_available = True
        self.set_update_indicator("available", latest)
        self.add_log(f"Update available: v{latest}")

        if manual:
            self.show_update_dialog(release)

    def _download_and_install_update(self, release):
        if self.engine.running:
            if not messagebox.askyesno(
                "Stop Grinder",
                "The grinder must stop briefly to install the update.\n\n"
                "Stop and update now?"
            ):
                return
            self.engine.stop()

        self.update_status_var.set(f"Downloading v{release['version']}…")
        self.update_btn.config(text="↓", bg="#0078d4", fg="white")
        self.update_badge.place_forget()
        self.add_log(
            f"Downloading update asset: {release.get('asset_name')}"
        )

        def worker():
            try:
                archive = download_update(
                    release["download_url"],
                    release["version"],
                    release.get("download_kind", "zip"),
                )
                self.root.after(
                    0,
                    lambda: self._launch_updater(archive, release["version"])
                )
            except Exception as e:
                self.root.after(
                    0,
                    lambda err=str(e): self._handle_update_error(err, True)
                )

        threading.Thread(target=worker, daemon=True).start()

    def _launch_updater(self, archive, version):
        try:
            source_updater = ROOT / "updater.py"
            if not source_updater.exists():
                raise RuntimeError("updater.py is missing from the installation.")

            temp_updater = UPDATE_CACHE_DIR / "updater_run.py"
            shutil.copy2(source_updater, temp_updater)

            args = [
                sys.executable,
                str(temp_updater),
                "--zip", str(archive),
                "--install-dir", str(ROOT),
                "--profile-dir", str(PROFILE_DIR),
                "--version", str(version),
                "--pid", str(os.getpid()),
            ]

            kwargs = {}
            if os.name == "nt":
                kwargs["creationflags"] = getattr(
                    subprocess, "CREATE_NO_WINDOW", 0x08000000
                )

            subprocess.Popen(
                args,
                cwd=str(UPDATE_CACHE_DIR),
                close_fds=True,
                **kwargs
            )

            self.add_log(f"Updater launched for v{version}")
            self.update_status_var.set(f"Installing v{version}…")
            self.update_btn.config(text="↻", bg="#0078d4", fg="white")

            # Let updater take over after this process closes.
            self.root.after(400, self.root.destroy)

        except Exception as e:
            messagebox.showerror("Updater", str(e))

    # ==========================================================
    # SMART DODGE GUI / CALIBRATION
    # ==========================================================
    def save_dodge_ui(self):
        try:
            threshold = float(self.dodge_threshold_var.get())
            threshold = max(0.55, min(0.95, threshold))
        except Exception:
            threshold = 0.74
            self.dodge_threshold_var.set("0.74")

        with settings_lock:
            dodge_settings["enabled"] = bool(self.dodge_enabled_var.get())
            dodge_settings["dodge_owl"] = bool(self.dodge_owl_var.get())
            dodge_settings["disable_at_master_plus"] = bool(
                self.dodge_master_var.get()
            )
            dodge_settings["owl_threshold"] = threshold

        save_dodge_settings()
        try:
            self.engine.reload_dodge_samples()
            self.engine._validate_dodge_health()
        except Exception:
            pass
        self.dodge_state_var.set("ACTIVE" if self.dodge_enabled_var.get() else "OFF")
        if hasattr(self, "dodge_active_badge"):
            active = bool(self.dodge_enabled_var.get())
            self.dodge_active_badge.config(
                text=self.dodge_state_var.get(),
                fg=UI_GREEN if active else UI_MUTED,
                bg=UI_GREEN_DARK if active else UI_TILE,
            )
        self.refresh_dodge_calibration_status()

    def refresh_dodge_calibration_status(self):
        samples = load_owl_samples()
        cfg = get_dodge_settings()

        quit_ok = "YES" if cfg.get("quit_ref") else "NO"
        confirm_ok = "YES" if cfg.get("confirm_ref") else "NO"

        self.dodge_calibration_var.set(
            f"Owl samples: {len(samples)}   |   "
            f"Quit calibrated: {quit_ok}   |   "
            f"Confirm calibrated: {confirm_ok}"
        )
        if hasattr(self, "dodge_short_var"):
            self.dodge_short_var.set(
                f"OWL {len(samples)}/3  •  QUIT {'✓' if quit_ok == 'YES' else '—'}  •  "
                f"CONFIRM {'✓' if confirm_ok == 'YES' else '—'}"
            )

    def _daily_shutdown_transport(self):
        """Stop Daily-only Fast Vision / persistent tap transport."""
        vision = getattr(self, "daily_vision", None)
        if vision is not None:
            try:
                vision.stop()
            except Exception:
                pass
        shell = getattr(self, "daily_tap_shell", None)
        if shell is not None:
            try:
                shell.stop()
            except Exception:
                pass
        self.daily_vision = None
        self.daily_tap_shell = None
        self.daily_transport_device = None

    def _daily_prepare_transport(self, dev):
        """Prepare low-latency Daily transport without starting Arena logic."""
        dev = str(dev or "")
        if not dev:
            return False
        if getattr(self, "daily_transport_device", None) != dev:
            self._daily_shutdown_transport()
            self.daily_transport_device = dev

        # Query physical geometry once. Vision frames are already normalized to
        # reference size, but taps still need the real phone dimensions.
        geometry_ok = False
        try:
            size = query_device_size(dev)
            if size:
                w, h = size
                if w < h:
                    w, h = h, w
                self.engine.actual_w, self.engine.actual_h = int(w), int(h)
                geometry_ok = True
        except Exception:
            pass
        if not geometry_ok:
            # Rare fallback: one raw screencap establishes real geometry, then
            # the persistent stream handles subsequent frames at high speed.
            try:
                raw = capture_screen()
                h, w = raw.shape[:2]
                self.engine.actual_w, self.engine.actual_h = int(w), int(h)
            except Exception:
                pass

        if getattr(self, "daily_tap_shell", None) is None:
            try:
                shell = AdbTapShell(dev)
                if shell.start():
                    self.daily_tap_shell = shell
            except Exception:
                self.daily_tap_shell = None

        vision = getattr(self, "daily_vision", None)
        if vision is None or not getattr(vision, "running", False):
            try:
                vision = VisionStream(dev, REFERENCE_W, REFERENCE_H, target_fps=24, on_status=self.add_log)
                ready = vision.start(wait_seconds=1.35)
                # A slow encoder handshake must not permanently force Daily back
                # onto multi-second adb screencap. Keep the stream warming in the
                # background; _phone_reference_screenshot will use it as soon as
                # the first frame arrives.
                if getattr(vision, "running", False):
                    self.daily_vision = vision
                    if ready:
                        self.add_log("Daily Fast Vision ready — low-latency frames active")
                    else:
                        why = getattr(vision, "last_error", None) or "warming up"
                        self.add_log(f"Daily Fast Vision warming ({why}) — will switch automatically")
                else:
                    self.daily_vision = None
                    self.add_log("Daily Fast Vision unavailable — screencap fallback")
            except Exception as e:
                self.daily_vision = None
                self.add_log(f"Daily Fast Vision fallback: {e}")
        return getattr(self, "daily_vision", None) is not None

    def _daily_tap_reference(self, ref_x, ref_y):
        """Fast Daily tap using the persistent shell, with safe process fallback."""
        aw = int(getattr(self.engine, "actual_w", REFERENCE_W) or REFERENCE_W)
        ah = int(getattr(self.engine, "actual_h", REFERENCE_H) or REFERENCE_H)
        x = round(float(ref_x) * aw / REFERENCE_W)
        y = round(float(ref_y) * ah / REFERENCE_H)
        started = time.perf_counter()
        shell = getattr(self, "daily_tap_shell", None)
        if shell is not None:
            try:
                if shell.tap(x, y):
                    return (time.perf_counter() - started) * 1000.0
            except Exception:
                pass
        return self.engine._tap_reference(float(ref_x), float(ref_y), aw, ah)

    def _phone_reference_screenshot(self):
        # Prefer Daily Fast Vision: adb screencap can take several seconds on
        # some Wireless ADB setups, while the continuous stream provides a
        # fresh normalized frame in milliseconds.
        vision = getattr(self, "daily_vision", None)
        if vision is not None and getattr(vision, "running", False):
            try:
                # Most calls return immediately. Only a brand-new stream gets a
                # tiny grace window so we do not unnecessarily fall back to the
                # 4s+ Wireless ADB screencap path during encoder startup.
                deadline = time.monotonic() + (0.45 if getattr(vision, "frame_id", 0) == 0 else 0.0)
                while True:
                    ref, age_ms, _ = vision.get_latest()
                    if ref is not None and (age_ms is None or age_ms < 1200):
                        return ref.copy()
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(0.025)
            except Exception:
                pass

        screen = capture_screen()
        try:
            actual_h, actual_w = screen.shape[:2]
            self.engine.actual_w = int(actual_w)
            self.engine.actual_h = int(actual_h)
        except Exception:
            pass
        return resize_reference(screen)

    def _show_roi_picker(self, ref, title, callback, instructions=None):
        # Use Tk's built-in PNG support; no Pillow dependency.
        ok, encoded = cv2.imencode(".png", ref)
        if not ok:
            messagebox.showerror("Calibration", "Could not encode phone screenshot.")
            return

        data = base64.b64encode(encoded.tobytes()).decode("ascii")

        win = tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        win.grab_set()

        ttk.Label(
            win,
            text=instructions or (
                "Drag a rectangle around ONLY Owl. "
                "Use the enemy character/model area, not the whole screen."
            )
        ).pack(anchor="w", padx=10, pady=(8, 4))

        photo_full = tk.PhotoImage(data=data)
        # Reference is 1536x709 -> preview ~768x355.
        photo = photo_full.subsample(2, 2)

        canvas = tk.Canvas(
            win,
            width=photo.width(),
            height=photo.height(),
            cursor="cross"
        )
        canvas.pack(padx=10, pady=8)
        canvas.create_image(0, 0, anchor="nw", image=photo)
        canvas.image = photo
        canvas.image_full = photo_full

        state = {"sx": None, "sy": None, "rect": None}

        def down(e):
            state["sx"], state["sy"] = e.x, e.y
            if state["rect"] is not None:
                canvas.delete(state["rect"])
            state["rect"] = canvas.create_rectangle(
                e.x, e.y, e.x, e.y,
                outline="red",
                width=2
            )

        def move(e):
            if state["sx"] is None:
                return
            canvas.coords(
                state["rect"],
                state["sx"], state["sy"],
                e.x, e.y
            )

        def up(e):
            if state["sx"] is None:
                return

            x1 = max(0, min(state["sx"], e.x) * 2)
            y1 = max(0, min(state["sy"], e.y) * 2)
            x2 = min(REFERENCE_W, max(state["sx"], e.x) * 2)
            y2 = min(REFERENCE_H, max(state["sy"], e.y) * 2)

            if x2 - x1 < 20 or y2 - y1 < 20:
                messagebox.showwarning(
                    "Calibration",
                    "Selection is too small."
                )
                return

            win.grab_release()
            win.destroy()
            callback(int(x1), int(y1), int(x2), int(y2))

        canvas.bind("<Button-1>", down)
        canvas.bind("<B1-Motion>", move)
        canvas.bind("<ButtonRelease-1>", up)

    def _show_point_picker(self, ref, title, instructions, callback):
        ok, encoded = cv2.imencode(".png", ref)
        if not ok:
            messagebox.showerror("Calibration", "Could not encode phone screenshot.")
            return

        data = base64.b64encode(encoded.tobytes()).decode("ascii")

        win = tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        win.grab_set()

        ttk.Label(
            win,
            text=instructions
        ).pack(anchor="w", padx=10, pady=(8, 4))

        photo_full = tk.PhotoImage(data=data)
        photo = photo_full.subsample(2, 2)

        canvas = tk.Canvas(
            win,
            width=photo.width(),
            height=photo.height(),
            cursor="cross"
        )
        canvas.pack(padx=10, pady=8)
        canvas.create_image(0, 0, anchor="nw", image=photo)
        canvas.image = photo
        canvas.image_full = photo_full

        def pick(e):
            rx = min(REFERENCE_W - 1, max(0, e.x * 2))
            ry = min(REFERENCE_H - 1, max(0, e.y * 2))
            win.grab_release()
            win.destroy()
            callback(float(rx), float(ry))

        canvas.bind("<Button-1>", pick)

    def capture_opponent_org_roi(self):
        if self.engine.running:
            messagebox.showwarning(
                "Stop grinder first",
                "Stop the grinder for a few seconds before opponent detector calibration."
            )
            return

        if not messagebox.askokcancel(
            "Calibrate Opponent Organization",
            "Put the PHONE on a REAL Arena opponent screen where the opponent username "
            "and their Organization are visible.\n\n"
            "Click OK, then drag a rectangle around ONLY the Organization name line "
            "directly under the opponent username.\n\n"
            "Do not include the username itself."
        ):
            return

        try:
            ref = self._phone_reference_screenshot()
        except Exception as e:
            messagebox.showerror("Opponent Calibration", str(e))
            return

        def save_roi(x1, y1, x2, y2):
            update_opponent_setting("org_roi", [x1, y1, x2, y2])
            self.opponent_identity_var.set(
                f"ORG detector calibrated: {x1},{y1} → {x2},{y2}"
            )
            self.add_log(
                f"Opponent ID: Organization ROI calibrated at "
                f"({x1},{y1})-({x2},{y2})"
            )
            messagebox.showinfo(
                "Opponent Detector Ready",
                "Saved.\n\n"
                "Rule now used during every match:\n"
                "Organization present = REAL PERSON\n"
                "Organization blank = BOT"
            )
            if getattr(self, "history_page", None) is not None:
                self.refresh_history_page()

        self._show_roi_picker(
            ref,
            "Opponent Organization Line",
            save_roi,
            instructions=(
                "Drag around ONLY the Organization name under the opponent username. "
                "Organization present = REAL; blank = BOT."
            )
        )

    def test_opponent_identity(self):
        roi = opponent_org_roi()
        if roi is None:
            messagebox.showwarning(
                "Opponent Detector",
                "Organization line is not calibrated yet.\n\n"
                "Open History → CALIBRATE ORG first."
            )
            return

        try:
            ref = self._phone_reference_screenshot()
            kind, org, source, debug = classify_opponent_by_organization(ref)
        except Exception as e:
            messagebox.showerror("Opponent Detector", str(e))
            return

        if kind == "REAL":
            verdict = f"REAL PERSON\nOrganization: {org or '(visible)'}"
        elif kind == "BOT":
            verdict = "BOT\nNo Organization detected under username"
        else:
            verdict = f"UNCERTAIN\n{debug or source}"

        self.add_log(
            f"OPPONENT ID TEST: {kind or 'UNCERTAIN'} source={source} "
            f"org={org or '-'} debug={debug or '-'}"
        )
        messagebox.showinfo(
            "Opponent Identity Test",
            f"{verdict}\n\nSource: {source}"
        )

    def capture_owl_sample(self):
        if self.engine.running:
            messagebox.showwarning(
                "Stop grinder first",
                "Stop the grinder for a few seconds before calibration."
            )
            return

        if not messagebox.askokcancel(
            "Capture Owl",
            "Put the phone in a battle where ENEMY Owl of Readiness is "
            "clearly visible.\n\n"
            "Then click OK and drag a tight rectangle around Owl."
        ):
            return

        try:
            ref = self._phone_reference_screenshot()
        except Exception as e:
            messagebox.showerror("Capture Owl", str(e))
            return

        def save_crop(x1, y1, x2, y2):
            crop_img = ref[y1:y2, x1:x2]
            DODGE_TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

            existing = sorted(DODGE_TEMPLATE_DIR.glob("owl_*.png"))
            idx = len(existing) + 1
            path = DODGE_TEMPLATE_DIR / f"owl_{idx:02d}.png"

            cv2.imwrite(str(path), crop_img)
            self.engine.reload_dodge_samples()
            self.refresh_dodge_calibration_status()
            self.add_log(
                f"Smart Dodge: saved Owl sample {path.name} "
                f"({x2-x1}x{y2-y1})"
            )

        self._show_roi_picker(
            ref,
            "Capture Owl of Readiness",
            save_crop
        )

    def test_owl_detection(self):
        if self.engine.running:
            messagebox.showwarning(
                "Stop grinder first",
                "Stop the grinder before testing Owl calibration."
            )
            return

        samples = load_owl_samples()
        if not samples:
            messagebox.showwarning(
                "Smart Dodge",
                "No Owl samples yet. Use ADD OWL SAMPLE first."
            )
            return

        try:
            ref = self._phone_reference_screenshot()
            score, sample = detect_owl(ref, samples)
        except Exception as e:
            messagebox.showerror("Smart Dodge", str(e))
            return

        threshold = float(get_dodge_settings().get("owl_threshold", 0.74))
        verdict = "OWL DETECTED" if score >= threshold else "NOT DETECTED"

        self.add_log(
            f"OWL TEST: score={score:.3f} threshold={threshold:.3f} "
            f"sample={sample or '?'} -> {verdict}"
        )
        messagebox.showinfo(
            "Owl Detection Test",
            f"{verdict}\n\n"
            f"Score: {score:.3f}\n"
            f"Threshold: {threshold:.3f}\n"
            f"Best sample: {sample or '?'}"
        )

    def capture_dodge_point(self, key):
        if self.engine.running:
            messagebox.showwarning(
                "Stop grinder first",
                "Stop the grinder before calibrating the quit flow."
            )
            return

        if key == "quit_ref":
            message = (
                "On the PHONE, open the battle Pause menu manually.\n\n"
                "When the Quit / Leave / Surrender button is visible, "
                "click OK.\n\n"
                "Then click the CENTER of that button in the screenshot."
            )
            picker_title = "Set Quit / Surrender Point"
            picker_help = "Click the CENTER of the Quit / Leave / Surrender button."
        else:
            message = (
                "On the PHONE, make the quit confirmation dialog visible "
                "manually.\n\n"
                "When its Confirm / Yes button is visible, click OK.\n\n"
                "Then click the CENTER of Confirm / Yes in the screenshot."
            )
            picker_title = "Set Quit Confirmation Point"
            picker_help = "Click the CENTER of Confirm / Yes."

        if not messagebox.askokcancel("Smart Dodge Calibration", message):
            return

        try:
            ref = self._phone_reference_screenshot()
        except Exception as e:
            messagebox.showerror("Calibration", str(e))
            return

        def save_point(x, y):
            update_dodge_setting(key, [x, y])
            self.refresh_dodge_calibration_status()
            self.add_log(
                f"Smart Dodge: {key} calibrated at "
                f"reference ({x:.0f}, {y:.0f})"
            )

        self._show_point_picker(
            ref,
            picker_title,
            picker_help,
            save_point
        )

    def clear_owl_samples(self):
        if self.engine.running:
            messagebox.showwarning(
                "Stop grinder first",
                "Stop the grinder before clearing calibration."
            )
            return

        if not messagebox.askyesno(
            "Clear Owl Samples",
            "Delete every calibrated Owl sample?"
        ):
            return

        for p in DODGE_TEMPLATE_DIR.glob("owl_*.png"):
            try:
                p.unlink()
            except Exception:
                pass

        self.engine.reload_dodge_samples()
        self.refresh_dodge_calibration_status()
        self.add_log("Smart Dodge: Owl samples cleared")

    def install_fast_vision(self):
        if find_ffmpeg():
            messagebox.showinfo(
                "Fast Vision Ready",
                "FFmpeg is already installed. Fast Vision will be used the next time you START GRIND."
            )
            return

        if not messagebox.askyesno(
            "Install Fast Vision",
            "Fast Vision needs FFmpeg to decode the continuous Android screen stream.\n\n"
            "Install FFmpeg now with winget?\n\n"
            "A terminal may appear once for installation."
        ):
            return

        try:
            cmd = (
                'start "Install FFmpeg" cmd /k '
                '"winget install --id Gyan.FFmpeg -e '
                '--accept-package-agreements --accept-source-agreements '
                '&& echo. && echo FFmpeg installation finished. '
                '&& echo Restart TG:BTC Companion if Fast Vision still says unavailable. '
                '&& pause"'
            )
            subprocess.Popen(
                cmd, shell=True, cwd=str(ROOT),
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            )
            self.add_log("Opened FFmpeg installer for Fast Vision")
        except Exception as e:
            messagebox.showerror("Install Fast Vision", str(e))

    def update_ocr_status(self):
        ready = refresh_tesseract()

        if ready:
            msg = "OCR: READY — Rank/Points tracking enabled"
        elif HAS_PYTESSERACT:
            msg = "OCR: MISSING tesseract.exe — click INSTALL OCR"
        else:
            msg = "OCR: MISSING pytesseract + tesseract.exe"

        self.ocr_var.set(msg)
        self.ocr_live_var.set(msg)

    def install_ocr(self):
        """
        Deliberately opens a visible Windows terminal because this is a
        one-time software installation, not a background ADB action.
        """
        if refresh_tesseract():
            messagebox.showinfo(
                "OCR Already Installed",
                f"Tesseract is already available.\n\n{tesseract_path_text()}"
            )
            return

        if messagebox.askyesno(
            "Install Tesseract OCR",
            "Rank/Points need the Tesseract OCR engine.\n\n"
            "Install it now using Windows Package Manager (winget)?\n\n"
            "A terminal/UAC prompt may appear once."
        ):
            try:
                # Current official winget package ID.
                cmd = (
                    'start "Install Tesseract OCR" cmd /k '
                    '"winget install --id tesseract-ocr.tesseract -e '
                    '--accept-package-agreements --accept-source-agreements '
                    '&& echo. && echo Installation finished. '
                    '&& echo Return to TG:BTC Companion and click TEST OCR. '
                    '&& pause"'
                )
                subprocess.Popen(
                    cmd,
                    shell=True,
                    cwd=str(ROOT),
                    creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
                )
                self.add_log("Opened Tesseract OCR installer")
            except Exception as e:
                messagebox.showerror("Install OCR", str(e))

    def set_rank_points_manual(self):
        """
        Manual fallback / seed. Uses a small dialog and known rank list.
        """
        win = tk.Toplevel(self.root)
        win.title("Set Current Rank / Points")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        frame = ttk.Frame(win, padding=14)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="Use this only as fallback if OCR is unavailable."
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Label(frame, text="Rank:").grid(row=1, column=0, sticky="w", pady=4)
        rank_var = tk.StringVar(value=session.get("rank") or "Gold V")
        rank_box = ttk.Combobox(
            frame,
            textvariable=rank_var,
            values=RANK_NAMES,
            state="readonly",
            width=18
        )
        rank_box.grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Points:").grid(row=2, column=0, sticky="w", pady=4)
        points_var = tk.StringVar(
            value=str(session.get("points") if session.get("points") is not None else "")
        )
        points_entry = ttk.Entry(frame, textvariable=points_var, width=20)
        points_entry.grid(row=2, column=1, sticky="ew", pady=4)

        def save():
            try:
                pts = int(points_var.get().strip())
                if pts < 0 or pts > 99999:
                    raise ValueError
            except Exception:
                messagebox.showerror("Invalid points", "Enter a valid numeric point value.")
                return

            rank = rank_var.get().strip()
            set_manual_rank_points(rank, pts)
            self.refresh()
            self.add_log(f"Manual score set: {rank} — {pts} pts")
            win.grab_release()
            win.destroy()

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="CANCEL", command=win.destroy).pack(side="right")
        ttk.Button(buttons, text="SAVE", command=save).pack(side="right", padx=(0, 8))

        points_entry.focus_set()

    def test_ocr(self):
        self.update_ocr_status()

        try:
            result = debug_ocr_current_screen()
        except Exception as e:
            messagebox.showerror("OCR Test", f"OCR test failed:\\n\\n{e}")
            return

        if not result.get("ok"):
            messagebox.showwarning("OCR Not Ready", result["message"])
            self.add_log("OCR TEST: engine missing")
            return

        summary = (
            f"Arena: {result['arena_rank'] or '?'} | "
            f"{result['arena_points'] if result['arena_points'] is not None else '?'} pts\\n"
            f"Result: {result['result_rank'] or '?'} | "
            f"{result['result_points'] if result['result_points'] is not None else '?'} pts | "
            f"delta {result['result_delta'] if result['result_delta'] is not None else '?'}"
        )

        self.add_log(
            f"OCR Arena raw: {result['arena_raw'].strip()!r}"
        )
        self.add_log(
            f"OCR Result rank raw: {result['result_rank_raw'].strip()!r}"
        )
        self.add_log(
            f"OCR Result points raw: {result['result_points_raw'].strip()!r}"
        )

        # If we're currently on the Arena page and OCR found the score,
        # populate the GUI immediately instead of waiting for the next grind.
        parsed_rank = result.get("arena_rank") or result.get("result_rank")
        parsed_points = (
            result.get("arena_points")
            if result.get("arena_points") is not None
            else result.get("result_points")
        )

        if parsed_rank or parsed_points is not None:
            with session_lock:
                update_rank_points(parsed_rank, parsed_points)
            save_session()
            self.refresh()

        messagebox.showinfo("OCR Test", summary)

    def start(self):
        try:
            # Arena owns its own Fast Vision / tap shell. Stop Daily-only
            # transport first so Android screenrecord is never duplicated.
            self._daily_shutdown_transport()
            self.engine.start()
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
        except Exception as e:
            messagebox.showerror("Could not start", str(e))

    def stop(self):
        self.engine.stop()
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    def reset_session(self):
        if self.engine.running:
            messagebox.showwarning("Stop first", "Stop the grinder before resetting the session.")
            return

        if not messagebox.askyesno("Reset session", "Reset all live session counters?"):
            return

        global session
        with session_lock:
            session.clear()
            session.update(new_session())

        save_session()
        self.refresh()
        self.add_log("Session reset")

    def open_profile(self):
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(PROFILE_DIR)

    def open_folder(self):
        # Compatibility alias for older UI references.
        self.open_profile()

    def add_log(self, text):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log.config(state="normal")
        self.log.insert("end", f"{stamp}  ", "time")
        lower = text.lower()
        if "error" in lower or "failed" in lower:
            tag = "error"
        elif "rank" in lower or "ocr" in lower:
            tag = "rank"
        elif "try again" in lower or "dodge" in lower or "quit" in lower:
            tag = "action"
        elif "auto" in lower or "matching" in lower or "vision" in lower:
            tag = "auto"
        else:
            tag = None
        if tag:
            self.log.insert("end", text + "\n", tag)
        else:
            self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def refresh(self):
        with session_lock:
            data = dict(session)

        avg = avg_points_per_match()
        pph = points_per_hour()
        remaining, est = master_progress()
        proj = projected_points_by_close()

        self.vars["status"].set(data["status"])
        self.vars["auto"].set(str(data["auto"]).upper())
        self.vars["next"].set(data["expected_next_opponent"])

        self.vars["rank"].set(data["rank"] or "?")
        self.vars["points"].set("?" if data["points"] is None else str(data["points"]))
        self.vars["matches"].set(str(data["matches"]))
        self.vars["wins"].set(str(data["wins"]))
        self.vars["losses"].set(str(data["losses"]))
        self.vars["wr"].set(f"{win_rate():.1f}%")
        self.vars["streak"].set(current_streak_text())
        self.vars["bestw"].set(f"W{data['best_win_streak']}")
        self.vars["net"].set(f"{data['net_points']:+d}")
        self.vars["mph"].set(f"{matches_per_hour():.1f}")
        self.vars["pph"].set("?" if pph is None else f"{pph:+.1f}")
        self.vars["avg"].set("?" if avg is None else f"{avg:+.2f}")
        self.vars["master_left"].set("?" if remaining is None else str(remaining))
        self.vars["master_est"].set("?" if est is None else str(est))
        self.vars["projected"].set("?" if proj is None else str(proj))
        self.vars["elapsed"].set(format_duration(elapsed_seconds()))
        self.vars["arena_time"].set(arena_countdown_text())

        points_value = data.get("points")
        if points_value is None:
            self.master_progress_bar["value"] = 0
            self.master_progress_text.set("Waiting for score…")
        else:
            shown = max(0, min(MASTER_V_POINTS, int(points_value)))
            self.master_progress_bar["value"] = shown
            if int(points_value) >= MASTER_V_POINTS:
                self.master_progress_text.set("Master V reached — grinding continues")
            else:
                left = MASTER_V_POINTS - int(points_value)
                pct = 100.0 * int(points_value) / MASTER_V_POINTS
                self.master_progress_text.set(f"{left:,} pts to Master V")

        # Never run `adb devices` every GUI refresh — it competes with the
        # screencap/tap loop over Wireless ADB.
        dev = self.engine.device
        if self.engine.running and dev:
            self.device_var.set("ADB CONNECTED")
            self.device_detail_var.set(f"{dev[:12]}  •  Wireless" if dev else "Wireless ADB")
        elif dev:
            self.device_var.set("ADB READY")
            self.device_detail_var.set(f"{dev[:12]}  •  Wireless" if dev else "Wireless ADB")
        else:
            self.device_var.set("ADB NOT STARTED")
            self.device_detail_var.set("Wireless ADB")

        self.vars["vision_mode"].set(self.engine.vision_mode)
        self.vars["vision_fps"].set(f"{self.engine.vision_fps:.1f}" if self.engine.vision_fps else "?")
        self.vars["frame_age"].set(f"{self.engine.frame_age_ms} ms" if self.engine.frame_age_ms else "?")
        self.vars["recognition_ms"].set(f"{self.engine.last_recognition_ms} ms" if self.engine.last_recognition_ms else "?")
        self.vars["reaction_ms"].set(f"{self.engine.last_reaction_ms} ms" if self.engine.last_reaction_ms else "?")
        self.vars["tap_mode"].set(self.engine.tap_mode)

        self.vars["dodges"].set(str(data.get("dodges", 0)))
        self.vars["played_losses"].set(str(data.get("played_losses", 0)))
        self.vars["dodge_losses"].set(str(data.get("dodge_losses", 0)))
        owl_score = data.get("last_owl_score")
        self.vars["owl_score"].set(
            "?" if owl_score is None else f"{float(owl_score):.3f}"
        )
        self.vars["owl_sample"].set(data.get("last_owl_sample") or "?")
        saved = estimated_dodge_time_saved()
        self.vars["time_saved"].set("?" if saved is None else format_duration(saved))

        # V6.0 live battle HUD + goal.
        identity = data.get("current_opponent_type") or "?"
        ident_conf = data.get("current_identity_confidence")
        heroes = list(data.get("current_detected_heroes") or [])
        threat = data.get("current_threat_score")
        tlabel = data.get("current_threat_label") or "?"
        decision = data.get("current_decision") or "WAIT"
        username = data.get("current_opponent_username") or "?"
        hero_short = ",".join(heroes[:2]) + ("+" if len(heroes) > 2 else "") if heroes else "no heroes"
        self.battle_hud_var.set(f"{identity} {ident_conf if ident_conf is not None else '?'}% • {username} • {hero_short} • {tlabel} {threat if threat is not None else '?'} • {decision}")
        self.goal_var.set(goal_status().get("text", "No active goal"))

        # V5.8 overall health indicator.
        health = self.engine.health_snapshot()
        overall = health.get("overall", "IDLE")
        if overall == "HEALTHY":
            label, fg, bg = "● SYSTEM HEALTHY", UI_GREEN, UI_GREEN_DARK
        elif overall == "ATTENTION":
            label, fg, bg = "● NEEDS ATTENTION", UI_GOLD, "#3A3015"
        elif overall == "ISSUE":
            label, fg, bg = "● SYSTEM ISSUE", UI_RED, UI_ACCENT_DARK
        else:
            label, fg, bg = "● SYSTEM IDLE", UI_MUTED, UI_TILE
        self.health_overall_var.set(label)
        recoveries = int(health.get("recovery_count") or 0)
        self.health_detail_var.set(f"{recoveries} automatic recoveries • last: {health.get('last_recovery') or 'none'}")
        if hasattr(self, "health_button"):
            self.health_button.config(fg=fg, bg=bg, activeforeground=fg, activebackground=bg)
        adb_status = str((health.get("components") or {}).get("adb", {}).get("status") or "IDLE").upper()
        if hasattr(self, "adb_health_dot"):
            self.adb_health_dot.config(fg=self._health_status_color(adb_status))

        if hasattr(self, "dodge_active_badge"):
            active = bool(self.dodge_enabled_var.get())
            self.dodge_state_var.set("ACTIVE" if active else "OFF")
            self.dodge_active_badge.config(
                text=self.dodge_state_var.get(),
                fg=UI_GREEN if active else UI_MUTED,
                bg=UI_GREEN_DARK if active else UI_TILE,
            )

    def tick(self):
        self.refresh()

        now = time.time()

        # Opponent intelligence/history is persisted to disk. Refresh it at a
        # human-visible cadence instead of rereading JSON every 500 ms.
        if now - getattr(self, "_last_intel_refresh", 0.0) >= 2.0:
            self._refresh_intel_dashboard()
            self._last_intel_refresh = now

        history_page = getattr(self, "history_page", None)
        if history_page is not None and now - getattr(self, "_last_history_refresh", 0.0) >= 2.0:
            try:
                if history_page.winfo_exists() and history_page.winfo_ismapped():
                    self.refresh_history_page()
            except Exception:
                pass
            self._last_history_refresh = now

        intel_page = getattr(self, "intelligence_page", None)
        if intel_page is not None and now - getattr(self, "_last_intelligence_page_refresh", 0.0) >= 1.5:
            try:
                if intel_page.winfo_exists() and intel_page.winfo_ismapped(): self.refresh_intelligence_page()
            except Exception: pass
            self._last_intelligence_page_refresh = now

        strategy_page = getattr(self, "strategy_page", None)
        if strategy_page is not None and now - getattr(self, "_last_strategy_page_refresh", 0.0) >= 1.5:
            try:
                if strategy_page.winfo_exists() and strategy_page.winfo_ismapped(): self.refresh_strategy_page()
            except Exception: pass
            self._last_strategy_page_refresh = now

        if now - getattr(self, "_last_notification_check", 0.0) >= 5.0:
            try: self._check_notifications()
            except Exception: pass
            self._last_notification_check = now

        diag_page = getattr(self, "diagnostics_page", None)
        if diag_page is not None and now - getattr(self, "_last_diag_refresh", 0.0) >= 1.0:
            try:
                if diag_page.winfo_exists() and diag_page.winfo_ismapped():
                    self.refresh_diagnostics_page()
            except Exception:
                pass
            self._last_diag_refresh = now

        last = getattr(self, "_last_ocr_refresh", 0.0)
        if now - last >= 5.0:
            self.update_ocr_status()
            self._last_ocr_refresh = now

        self.root.after(500, self.tick)

def main():
    root = tk.Tk()
    # Build while hidden so the legacy bright Windows title bar never flashes
    # before V5.6 switches to the custom dark chrome.
    root.withdraw()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.close_window)
    root.update_idletasks()
    root.deiconify()
    root.after(120, app._ensure_taskbar_presence)
    root.mainloop()

if __name__ == "__main__":
    main()

# V6.0 Arena Intelligence Suite build marker

# V7.0 Full Game Assistant / modular Daily Assistant build marker
# V7.0.6 Daily physical-coordinate scaling fix

# V7.1 Daily Assistant V1 build marker

# V7.2 Vision-First Assistant build marker
