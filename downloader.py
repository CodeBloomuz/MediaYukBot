import asyncio
import re
from pathlib import Path
import yt_dlp
from config import DOWNLOAD_DIR

DOWNLOAD_PATH = Path(DOWNLOAD_DIR)
DOWNLOAD_PATH.mkdir(exist_ok=True)

# ─── COOKIES FAYLLARI ─────────────────────────
# Instagram uchun cookies.txt
# Facebook uchun cookies_fb.txt
INSTAGRAM_COOKIES = "cookies.txt"
FACEBOOK_COOKIES  = "cookies_fb.txt"

SUPPORTED = [
    "youtube.com", "youtu.be",
    "instagram.com",
    "facebook.com", "fb.com", "fb.watch",
    "tiktok.com",
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
    if "youtu" in u:                      return "YouTube"
    if "instagram.com/stories" in u:      return "Instagram Story"
    if "instagram.com/reels" in u:        return "Instagram Reels"
    if "instagram.com/reel" in u:         return "Instagram Reels"
    if "instagram.com" in u:             return "Instagram"
    if "facebook.com/stories" in u:       return "Facebook Story"
    if "facebook.com" in u or "fb." in u: return "Facebook"
    if "tiktok.com" in u:                return "TikTok"
    return "Video"

def _base_opts(uid: int) -> dict:
    return {
        "outtmpl": str(DOWNLOAD_PATH / f"{uid}_%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "socket_timeout": 30,
    }

# ─── VIDEO YUKLAB OLISH ───────────────────────
def _download_video_sync(url: str, uid: int) -> dict:
    opts = _base_opts(uid)
    u = url.lower()

    # Faqat video formatlar
    opts["format"] = (
        "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]"
        "/bestvideo[height<=720]+bestaudio"
        "/best[height<=720]"
        "/bestvideo+bestaudio"
        "/best"
    )

    # ── Instagram ──────────────────────────────
    if "instagram.com" in u:
        if Path(INSTAGRAM_COOKIES).exists():
            opts["cookiefile"] = INSTAGRAM_COOKIES
        opts["extractor_args"] = {
            "instagram": {"include_ads": False}
        }

    # ── Facebook ───────────────────────────────
    elif "facebook.com" in u or "fb.com" in u or "fb.watch" in u:
        if Path(FACEBOOK_COOKIES).exists():
            opts["cookiefile"] = FACEBOOK_COOKIES

    # ── TikTok — suv belgisiz ──────────────────
    elif "tiktok.com" in u:
        opts["extractor_args"] = {
            "tiktok": {"api_hostname": ["api22-normal-c-useast2a.tiktokv.com"]}
        }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

        # Stories/playlist bo'lsa birinchi videoni olish
        if info and "entries" in info:
            entries = list(info["entries"])
            if not entries:
                raise ValueError("Kontent topilmadi")
            info = entries[0]

        if not info:
            raise ValueError("Video ma'lumotlari topilmadi")

        fname = ydl.prepare_filename(info)
        p = Path(fname)
        if not p.exists():
            p = p.with_suffix(".mp4")

        return {
            "path": str(p),
            "title": info.get("title", "Video"),
            "duration": info.get("duration", 0),
            "thumb": info.get("thumbnail"),
            "uploader": info.get("uploader", ""),
        }

async def download_video(url: str, uid: int) -> dict:
    return await asyncio.get_event_loop().run_in_executor(
        None, _download_video_sync, url, uid
    )

# ─── TOZALASH ─────────────────────────────────
def cleanup(path: str):
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass
