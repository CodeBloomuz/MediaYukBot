import asyncio
import re
from pathlib import Path
import yt_dlp
from config import DOWNLOAD_DIR

DOWNLOAD_PATH = Path(DOWNLOAD_DIR)
DOWNLOAD_PATH.mkdir(exist_ok=True)

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
    if "youtu" in u:                       return "YouTube"
    if "instagram.com/stories" in u:       return "Instagram Story"
    if "instagram.com/reels" in u:         return "Instagram Reels"
    if "instagram.com/reel" in u:          return "Instagram Reels"
    if "instagram.com" in u:              return "Instagram"
    if "facebook.com/stories" in u:        return "Facebook Story"
    if "facebook.com" in u or "fb." in u:  return "Facebook"
    if "tiktok.com" in u:                 return "TikTok"
    return "Video"

def is_instagram_photo_post(url: str) -> bool:
    """Instagram /p/ — rasm yoki carousel post bo'lishi mumkin"""
    return bool(re.search(r'instagram\.com/p/', url.lower()))

def _base_opts(uid: int) -> dict:
    return {
        "outtmpl": str(DOWNLOAD_PATH / f"{uid}_%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "socket_timeout": 60,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        },
    }

# ─── INSTAGRAM RASM YUKLAB OLISH ─────────────────────────────────────────────
def _download_instagram_photos_sync(url: str, uid: int) -> dict:
    """
    Instagram post rasmlarini yuklab oladi.
    Natija: {
        "type": "photos",
        "paths": ["1.jpg", "2.jpg", ...],
        "title": "...",
        "uploader": "..."
    }
    """
    opts = {
        **_base_opts(uid),
        "outtmpl": str(DOWNLOAD_PATH / f"{uid}_%(id)s_%(autonumber)s.%(ext)s"),
        "format": "best",
        "writethumbnail": False,
    }
    if Path(INSTAGRAM_COOKIES).exists():
        opts["cookiefile"] = INSTAGRAM_COOKIES

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

        # Carousel (bir nechta rasm/video)
        if info and "entries" in info:
            entries = list(info["entries"])
        else:
            entries = [info] if info else []

        if not entries:
            raise ValueError("Kontent topilmadi")

        paths = []
        media_types = []
        for entry in entries:
            if not entry:
                continue
            fname = ydl.prepare_filename(entry)
            p = Path(fname)

            # Agar fayl topilmasa turli kengaytmalarni sinab ko'rish
            if not p.exists():
                for ext in [".jpg", ".jpeg", ".png", ".webp", ".mp4", ".webm"]:
                    alt = p.with_suffix(ext)
                    if alt.exists():
                        p = alt
                        break

            if p.exists():
                ext = p.suffix.lower()
                if ext in [".mp4", ".webm", ".mkv", ".mov"]:
                    media_types.append("video")
                else:
                    media_types.append("photo")
                paths.append(str(p))

        if not paths:
            raise ValueError("Fayllar topilmadi")

        # Agar hammasi video bo'lsa — oddiy video sifatida qaytarish
        if all(t == "video" for t in media_types) and len(paths) == 1:
            return {
                "type": "video",
                "path": paths[0],
                "title": info.get("title", "Instagram Video"),
                "duration": info.get("duration", 0),
                "thumb": info.get("thumbnail"),
                "uploader": info.get("uploader", ""),
            }

        return {
            "type": "photos",
            "paths": paths,
            "media_types": media_types,
            "title": info.get("title", "Instagram Post"),
            "uploader": entries[0].get("uploader", info.get("uploader", "")),
        }

# ─── VIDEO YUKLAB OLISH ───────────────────────────────────────────────────────
def _download_video_sync(url: str, uid: int) -> dict:
    opts = _base_opts(uid)
    u = url.lower()

    # ── YouTube ───────────────────────────────
    # ── YouTube ───────────────────────────────
if "youtu" in u:
    opts["format"] = "bestvideo+bestaudio/best"

    # YouTube bot-blokidan o'tish
    opts["extractor_args"] = {
        "youtube": {
            "player_client": ["web", "android"],
        }
    }

    # Cookies mavjud bo'lsa ishlatish
    if Path("cookies_yt.txt").exists():
        opts["cookiefile"] = "cookies_yt.txt"

    # ── Instagram ─────────────────────────────
    elif "instagram.com" in u:
    opts["format"] = (
        "bestvideo[ext=mp4]+bestaudio"
        "/best[ext=mp4]"
        "/best"
    )

    opts["extractor_args"] = {
        "instagram": {
            "api_version": "v1",
        }
    }

    opts["merge_output_format"] = "mp4"

    if Path(INSTAGRAM_COOKIES).exists():
        opts["cookiefile"] = INSTAGRAM_COOKIES

    # ── Facebook ──────────────────────────────
    elif "facebook.com" in u or "fb.com" in u or "fb.watch" in u:
        opts["format"] = "best[ext=mp4]/best"
        if Path(FACEBOOK_COOKIES).exists():
            opts["cookiefile"] = FACEBOOK_COOKIES

    # ── TikTok — suv belgisiz ─────────────────
elif "tiktok.com" in u:
    opts["format"] = "bestvideo+bestaudio/best"
    opts["merge_output_format"] = "mp4"

    opts["extractor_args"] = {
        "tiktok": {
            "api_hostname": ["api16-normal-c-useast1a.tiktokv.com"],
            "app_version": ["26.1.3"],
        }
    }

    # ── Boshqa ────────────────────────────────
    else:
        opts["format"] = "best[ext=mp4]/best"

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

        # Stories/playlist — birinchi videoni olish
        if info and "entries" in info:
            entries = list(info["entries"])
            if not entries:
                raise ValueError("Kontent topilmadi")
            info = entries[0]

        if not info:
            raise ValueError("Video ma'lumotlari topilmadi")

        fname = ydl.prepare_filename(info)
        p = Path(fname)

        # Fayl topilmasa kengaytmalarni sinab ko'rish
        if not p.exists():
            for ext in [".mp4", ".webm", ".mkv", ".mov"]:
                alt = p.with_suffix(ext)
                if alt.exists():
                    p = alt
                    break

        if not p.exists():
            # DOWNLOAD_PATH ichida uid bilan boshlangan faylni qidirish
            candidates = list(DOWNLOAD_PATH.glob(f"{uid}_*.mp4"))
            if candidates:
                p = max(candidates, key=lambda f: f.stat().st_mtime)

        return {
            "type": "video",
            "path": str(p),
            "title": info.get("title", "Video"),
            "duration": info.get("duration", 0),
            "thumb": info.get("thumbnail"),
            "uploader": info.get("uploader", ""),
        }

async def download_media(url: str, uid: int) -> dict:
    """
    Asosiy yuklab olish funksiyasi.
    Instagram /p/ postlari uchun rasm/carousel tekshiradi,
    qolganlar uchun video yuklab oladi.
    """
    # Instagram oddiy post (/p/) — avval rasm ekanligini tekshirish
    if is_instagram_photo_post(url):
        return await asyncio.get_event_loop().run_in_executor(
            None, _download_instagram_photos_sync, url, uid
        )

    return await asyncio.get_event_loop().run_in_executor(
        None, _download_video_sync, url, uid
    )

# Orqaga moslik uchun eski nom ham ishlaydi
async def download_video(url: str, uid: int) -> dict:
    return await download_media(url, uid)

# ─── TOZALASH ─────────────────────────────────────────────────────────────────
def cleanup(path: str):
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass

def cleanup_list(paths: list[str]):
    for p in paths:
        cleanup(p)
