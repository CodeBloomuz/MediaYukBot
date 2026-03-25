import asyncio
import re
import time
from pathlib import Path
import yt_dlp

DOWNLOAD_PATH = Path("downloads")
DOWNLOAD_PATH.mkdir(exist_ok=True)

SUPPORTED = [
    "youtube.com", "youtu.be",
    "instagram.com",
    "facebook.com", "fb.com", "fb.watch",
    "tiktok.com",
    "threads.net", "threads.com",
]

def is_url(text: str) -> bool:
    return bool(re.search(r'https?://\S+', text))

def extract_url(text: str) -> str | None:
    m = re.search(r'https?://\S+', text)
    return m.group(0) if m else None

def is_supported(url: str) -> bool:
    return any(d in url.lower() for d in SUPPORTED)

def platform_name(url: str) -> str:
    u = url.lower()
    if "youtu" in u:                        return "YouTube"
    if "instagram.com/stories" in u:        return "Instagram Story"
    if "instagram.com/reels" in u:          return "Instagram Reels"
    if "instagram.com/reel/" in u:          return "Instagram Reels"
    if "instagram.com/p/" in u:             return "Instagram Post"
    if "instagram.com" in u:                return "Instagram"
    if "facebook.com/stories" in u:         return "Facebook Story"
    if "facebook.com/reel" in u:            return "Facebook Reels"
    if "facebook.com" in u or "fb." in u:  return "Facebook"
    if "tiktok.com" in u:                   return "TikTok"
    if "threads" in u:                      return "Threads"
    return "Video"

def _cookie(filename: str) -> dict:
    p = Path(filename)
    return {"cookiefile": str(p)} if p.exists() else {}

def _find_downloaded(outtmpl_base: str, uid: int) -> Path | None:
    """Yuklab olingan faylni topadi — barcha kengaytmalarni tekshiradi."""
    p = Path(outtmpl_base)
    if p.exists():
        return p
    for ext in ["mp4", "mkv", "webm", "mov", "avi",
                "jpg", "jpeg", "png", "webp"]:
        alt = p.with_suffix(f".{ext}")
        if alt.exists():
            return alt
    # Eng so'nggi yuklangan fayl (zaxira)
    candidates = sorted(
        DOWNLOAD_PATH.glob(f"{uid}_*"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _snapshot_files() -> set:
    """downloads/ papkasidagi barcha fayllarni qaytaradi."""
    return set(DOWNLOAD_PATH.glob("*"))


def _new_files(before: set) -> list:
    """before dan keyin paydo bolgan fayllarni qaytaradi."""
    after = set(DOWNLOAD_PATH.glob("*"))
    return sorted(after - before, key=lambda f: f.stat().st_mtime)


def _media_type(path: Path) -> str:
    return "video" if path.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov", ".avi"} else "photo"


# ══════════════════════════════════════════════
# ASOSIY YUKLAB OLISH
# ══════════════════════════════════════════════

def _download_sync(url: str, uid: int) -> dict:
    u = url.lower()

    # Instagram uchun universal format — rasm VA video
    INSTAGRAM_FORMAT = (
        "best[ext=mp4]/best[ext=jpg]/best[ext=jpeg]"
        "/best[ext=png]/best[ext=webp]/best"
    )

    base_opts = {
        "outtmpl": str(DOWNLOAD_PATH / f"{uid}_%(id)s.%(ext)s"),
        "noplaylist": False,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "socket_timeout": 60,
        "retries": 10,
        "fragment_retries": 10,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        },
    }

    # ── YouTube ───────────────────────────────
    if "youtu" in u:
        base_opts["noplaylist"] = True
        base_opts["format"] = (
            "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]"
            "/bestvideo[ext=mp4]+bestaudio"
            "/best[ext=mp4]/best"
        )
        base_opts["extractor_args"] = {
            "youtube": {"player_client": ["web", "android"]}
        }
        base_opts.update(_cookie("cookies_yt.txt"))

    # ── TikTok ────────────────────────────────
    elif "tiktok.com" in u:
        base_opts["noplaylist"] = True
        base_opts["format"] = "best[ext=mp4]/best"
        base_opts["extractor_args"] = {
            "tiktok": {
                "api_hostname": ["api16-normal-c-useast1a.tiktokv.com"],
                "app_version": ["26.1.3"],
            }
        }
        base_opts["http_headers"] = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
                "Mobile/15E148 Safari/604.1"
            ),
            "Referer": "https://www.tiktok.com/",
        }

    # ── Instagram ─────────────────────────────
    elif "instagram.com" in u:
        # FIX: "No video formats found" xatosini hal qiladi
        # Rasm bo'lsa jpg/png, video bo'lsa mp4 oladi
        base_opts["format"] = INSTAGRAM_FORMAT
        base_opts["http_headers"] = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 15_5 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/19F77 "
                "Instagram 239.2.0.17.109"
            ),
        }
        base_opts.update(_cookie("cookies.txt"))

    # ── Facebook ──────────────────────────────
    elif "facebook.com" in u or "fb." in u:
        # FIX: Stories va share/ havolalari uchun to'liq headers
        base_opts["format"] = "best[ext=mp4]/best"
        base_opts["http_headers"] = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        # Cookies MAJBURIY — Stories va share havolalari ishlamaydi
        base_opts.update(_cookie("cookies_fb.txt"))
        if not Path("cookies_fb.txt").exists():
            base_opts.update(_cookie("cookies.txt"))

        # Stories — playlist sifatida yuklanadi
        if "stories" in u:
            base_opts["noplaylist"] = False
        else:
            base_opts["noplaylist"] = True

    # ── Threads ───────────────────────────────
    elif "threads" in u:
        base_opts["noplaylist"] = True
        base_opts["format"] = "best[ext=mp4]/best"
        base_opts["http_headers"] = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
                "Mobile/15E148 Safari/604.1"
            ),
        }

    else:
        base_opts["noplaylist"] = True
        base_opts["format"] = "best[ext=mp4]/best"

    # Yuklanishdan OLDIN papkadagi fayllarni eslab qolish
    before = _snapshot_files()

    with yt_dlp.YoutubeDL(base_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        if not info:
            raise ValueError("Kontent topilmadi")

        # ── Playlist / Stories / Carousel ─────
        if "entries" in info:
            entries = [e for e in info["entries"] if e]
            if not entries:
                raise ValueError("Kontent topilmadi")

            results = []
            for entry in entries:
                # 1-usul: prepare_filename
                fname = ydl.prepare_filename(entry)
                p = _find_downloaded(fname, uid)

                # 2-usul: yangi fayllar orqali
                if not p or not p.exists():
                    new_files = _new_files(before)
                    idx = len(results)
                    p = new_files[idx] if idx < len(new_files) else None

                if p and p.exists():
                    results.append({
                        "path": str(p),
                        "type": _media_type(p),
                        "title": entry.get("title", ""),
                        "duration": entry.get("duration", 0),
                        "uploader": entry.get("uploader", ""),
                    })

            # 3-usul: hech narsa topilmasa — barcha yangi fayllar
            if not results:
                for p in _new_files(before):
                    results.append({
                        "path": str(p),
                        "type": _media_type(p),
                        "title": info.get("title", ""),
                        "duration": 0,
                        "uploader": info.get("uploader", ""),
                    })

            if not results:
                raise ValueError("Kontent topilmadi")

            if len(results) == 1:
                r = results[0]
                return {
                    "media_list": False,
                    "type": r["type"],
                    "path": r["path"],
                    "title": r["title"],
                    "duration": r["duration"],
                    "uploader": r.get("uploader", ""),
                }

            return {
                "media_list": True,
                "items": results,
                "title": info.get("title", ""),
                "uploader": info.get("uploader", entries[0].get("uploader", "")),
            }

        # ── Bitta media ───────────────────────
        fname = ydl.prepare_filename(info)
        p = _find_downloaded(fname, uid)

        # Zaxira: yuklanishdan keyin paydo bolgan yangi fayl
        if not p or not p.exists():
            new_files = _new_files(before)
            p = new_files[0] if new_files else None

        if not p or not p.exists():
            raise FileNotFoundError("Fayl topilmadi")

        return {
            "media_list": False,
            "type": _media_type(p),
            "path": str(p),
            "title": info.get("title", ""),
            "duration": info.get("duration", 0),
            "uploader": info.get("uploader", ""),
        }


async def download_media(url: str, uid: int) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _download_sync, url, uid)


# ══════════════════════════════════════════════
# TOZALASH
# ══════════════════════════════════════════════

def cleanup(path: str):
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass

def cleanup_list(paths: list):
    for p in paths:
        cleanup(p)

def duration_str(sec) -> str:
    if not sec:
        return ""
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
