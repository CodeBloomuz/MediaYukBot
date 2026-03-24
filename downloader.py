import asyncio
import re
from pathlib import Path
import yt_dlp
from config import DOWNLOAD_DIR, AUDIO_QUALITY

DOWNLOAD_PATH = Path(DOWNLOAD_DIR)
DOWNLOAD_PATH.mkdir(exist_ok=True)

SUPPORTED = [
    "youtube.com", "youtu.be",
    "instagram.com",
    "facebook.com", "fb.com", "fb.watch",
    "tiktok.com",
    "threads.net",
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
    if "youtu" in u:      return "YouTube"
    if "instagram" in u:  return "Instagram"
    if "facebook" in u or "fb." in u: return "Facebook"
    if "tiktok" in u:     return "TikTok"
    if "threads" in u:    return "Threads"
    return "Video"

def _base_opts(uid: int, ext: str) -> dict:
    return {
        "outtmpl": str(DOWNLOAD_PATH / f"{uid}_%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": ext,
        "cookiefile": "cookies.txt",   # ← shu qatorni qo'shing
    }

# ─── VIDEO ────────────────────────────────────
def _download_video_sync(url: str, uid: int) -> dict:
    opts = _base_opts(uid, "mp4")
    opts["format"] = (
        "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]"
        "/best[ext=mp4][height<=720]/best[height<=720]/best"
    )
    # TikTok watermark-free
    if "tiktok" in url.lower():
        opts["extractor_args"] = {"tiktok": {"api_hostname": ["api22-normal-c-useast2a.tiktokv.com"]}}

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        fname = ydl.prepare_filename(info)
        p = Path(fname)
        if not p.exists():
            p = p.with_suffix(".mp4")
        return {"path": str(p), "title": info.get("title","Video"),
                "duration": info.get("duration", 0), "thumb": info.get("thumbnail")}

async def download_video(url: str, uid: int) -> dict:
    return await asyncio.get_event_loop().run_in_executor(
        None, _download_video_sync, url, uid)

# ─── AUDIO ────────────────────────────────────
def _download_audio_sync(url: str, uid: int) -> dict:
    opts = _base_opts(uid, "mp3")
    opts["format"] = "bestaudio/best"
    opts["postprocessors"] = [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": "mp3",
        "preferredquality": AUDIO_QUALITY,
    }]
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        fname = ydl.prepare_filename(info)
        p = Path(fname).with_suffix(".mp3")
        return {"path": str(p), "title": info.get("title","Audio"),
                "duration": info.get("duration", 0), "thumb": info.get("thumbnail"),
                "artist": info.get("artist") or info.get("uploader",""),
                "album": info.get("album","")}

async def download_audio(url: str, uid: int) -> dict:
    return await asyncio.get_event_loop().run_in_executor(
        None, _download_audio_sync, url, uid)

# ─── SONG SEARCH ──────────────────────────────
def _search_song_sync(query: str, uid: int) -> dict:
    opts = _base_opts(uid, "mp3")
    opts["format"] = "bestaudio/best"
    opts["default_search"] = "ytsearch1"
    opts["postprocessors"] = [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": "mp3",
        "preferredquality": AUDIO_QUALITY,
    }]
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(query, download=True)
        if "entries" in info:
            info = info["entries"][0]
        fname = ydl.prepare_filename(info)
        p = Path(fname).with_suffix(".mp3")
        return {"path": str(p), "title": info.get("title","Qo'shiq"),
                "duration": info.get("duration", 0),
                "artist": info.get("artist") or info.get("uploader",""),
                "thumb": info.get("thumbnail")}

async def search_song(query: str, uid: int) -> dict:
    return await asyncio.get_event_loop().run_in_executor(
        None, _search_song_sync, query, uid)

# ─── LYRICS ───────────────────────────────────
async def fetch_lyrics(query: str) -> str | None:
    import aiohttp, urllib.parse
    # lyrics.ovh — bepul, API key shart emas
    parts = query.strip().split(None, 1)
    artist = parts[0] if parts else query
    title  = parts[1] if len(parts) > 1 else parts[0]
    url = f"https://api.lyrics.ovh/v1/{urllib.parse.quote(artist)}/{urllib.parse.quote(title)}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status == 200:
                    data = await r.json()
                    return data.get("lyrics")
    except Exception:
        pass
    return None

def cleanup(path: str):
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass
