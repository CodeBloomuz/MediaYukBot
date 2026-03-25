import asyncio
import re
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
    if "youtu" in u:                         return "YouTube"
    if "instagram.com/stories" in u:         return "Instagram Story"
    if "instagram.com/reels" in u:           return "Instagram Reels"
    if "instagram.com/reel/" in u:           return "Instagram Reels"
    if "instagram.com/p/" in u:              return "Instagram Post"
    if "instagram.com" in u:                 return "Instagram"
    if "facebook.com/stories" in u:          return "Facebook Story"
    if "facebook.com/reel" in u:             return "Facebook Reels"
    if "facebook.com" in u or "fb." in u:   return "Facebook"
    if "tiktok.com" in u:                    return "TikTok"
    if "threads" in u:                       return "Threads"
    return "Video"

def _cookie(filename: str) -> dict:
    p = Path(filename)
    return {"cookiefile": str(p)} if p.exists() else {}

def _find_downloaded(outtmpl_base: str, uid: int) -> Path | None:
    """Yuklab olingan faylni topadi."""
    p = Path(outtmpl_base)
    if p.exists():
        return p
    for ext in ["mp4", "mkv", "webm", "mov", "avi",
                "jpg", "jpeg", "png", "webp"]:
        alt = p.with_suffix(f".{ext}")
        if alt.exists():
            return alt
    # Oxirgi yuklangan fayl
    candidates = sorted(
        DOWNLOAD_PATH.glob(f"{uid}_*"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


# ══════════════════════════════════════════════
# ASOSIY YUKLAB OLISH
# ══════════════════════════════════════════════

def _download_sync(url: str, uid: int) -> dict:
    u = url.lower()

    base_opts = {
        "outtmpl": str(DOWNLOAD_PATH / f"{uid}_%(id)s.%(ext)s"),
        "noplaylist": False,        # Stories playlist uchun False
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

    # ── TikTok — suv belgisiz ─────────────────
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
        base_opts["format"] = "best[ext=mp4]/best"
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
        base_opts["format"] = "best[ext=mp4]/best"
        base_opts.update(_cookie("cookies_fb.txt"))
        if not Path("cookies_fb.txt").exists():
            base_opts.update(_cookie("cookies.txt"))

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

    with yt_dlp.YoutubeDL(base_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        if not info:
            raise ValueError("Kontent topilmadi")

        # Playlist / Stories — bir nechta media
        if "entries" in info:
            entries = [e for e in info["entries"] if e]
            if not entries:
                raise ValueError("Kontent topilmadi")

            # Bir nechta media qaytarish
            results = []
            for entry in entries:
                fname = ydl.prepare_filename(entry)
                p = _find_downloaded(fname, uid)
                if p and p.exists():
                    ext = p.suffix.lower()
                    mtype = "video" if ext in [".mp4", ".mkv", ".webm", ".mov"] else "photo"
                    results.append({
                        "path": str(p),
                        "type": mtype,
                        "title": entry.get("title", ""),
                        "duration": entry.get("duration", 0),
                        "uploader": entry.get("uploader", ""),
                    })

            if len(results) == 1:
                # Bitta natija — oddiy media sifatida
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

        # Bitta media
        fname = ydl.prepare_filename(info)
        p = _find_downloaded(fname, uid)

        if not p or not p.exists():
            raise FileNotFoundError("Fayl topilmadi")

        ext = p.suffix.lower()
        mtype = "video" if ext in [".mp4", ".mkv", ".webm", ".mov"] else "photo"

        return {
            "media_list": False,
            "type": mtype,
            "path": str(p),
            "title": info.get("title", ""),
            "duration": info.get("duration", 0),
            "uploader": info.get("uploader", ""),
        }


async def download_media(url: str, uid: int) -> dict:
    return await asyncio.get_event_loop().run_in_executor(
        None, _download_sync, url, uid
    )


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
