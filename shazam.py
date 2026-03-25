"""
Shazam orqali musiqa tanish moduli.
RapidAPI — Shazam Song Downloader API ishlatiladi.

O'rnatish:
    pip install aiohttp aiofiles

RapidAPI obuna:
    https://rapidapi.com/dashydata/api/shazam-song-downloader
    yoki
    https://rapidapi.com/apidojo/api/shazam
"""

import aiohttp
import aiofiles
from pathlib import Path


# ══════════════════════════════════════════════
# ASOSIY FUNKSIYA
# ══════════════════════════════════════════════

async def recognize_song(file_path: str, rapidapi_key: str) -> dict | None:
    """
    Audio faylni RapidAPI Shazam orqali taniydi.

    Args:
        file_path   : .ogg, .mp3, .wav, .m4a, .flac fayl yo'li
        rapidapi_key: config.py dagi RAPIDAPI_KEY

    Returns:
        {title, artist, cover, genre, year, label, track_url}
        yoki None (topilmasa)
    """
    p = Path(file_path)
    if not p.exists() or p.stat().st_size == 0:
        return None

    url = "https://shazam-song-downloader.p.rapidapi.com/search/by-audio/"
    headers = {
        "x-rapidapi-key":  rapidapi_key,
        "x-rapidapi-host": "shazam-song-downloader.p.rapidapi.com",
        "Content-Type":    "application/octet-stream",
    }

    try:
        async with aiofiles.open(str(p), "rb") as f:
            audio_data = await f.read()

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers=headers,
                data=audio_data,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:

                if resp.status == 401:
                    raise RuntimeError("❌ RapidAPI kalit noto'g'ri yoki obuna yo'q.")
                if resp.status == 429:
                    raise RuntimeError("⏳ RapidAPI so'rov limiti tugadi.")
                if resp.status != 200:
                    raise RuntimeError(f"RapidAPI HTTP {resp.status} xatosi.")

                data = await resp.json()

        return _parse(data)

    except aiohttp.ClientError as e:
        raise RuntimeError(f"Tarmoq xatosi: {e}") from e


# ══════════════════════════════════════════════
# JAVOBNI PARSE QILISH
# ══════════════════════════════════════════════

def _parse(data: dict) -> dict | None:
    """RapidAPI turli javob formatlarini yagona dict ga o'tkazadi."""

    if not data:
        return None

    # Track obyektini top (har xil API versiyalarda joyi farq qiladi)
    track = (
        data.get("track")
        or data.get("result")
        or (data if data.get("title") else None)
    )

    if not track:
        # matches orqali
        matches = data.get("matches", [])
        if not matches:
            return None
        track = matches[0]

    title  = track.get("title")  or track.get("name")   or ""
    artist = track.get("subtitle") or track.get("artist") or ""

    if not title and not artist:
        return None

    # Muqova rasmi
    images    = track.get("images", {})
    cover_url = (
        images.get("coverarthq")
        or images.get("coverart")
        or track.get("cover")
        or track.get("artwork")
        or ""
    )

    # Janr
    genres = track.get("genres", {})
    genre  = genres.get("primary") or track.get("genre") or ""

    # Yil va label (sections ichida)
    year = ""
    label = ""
    for section in track.get("sections", []):
        for meta in section.get("metadata", []):
            key = meta.get("title", "").lower()
            val = meta.get("text",  "")
            if "released" in key or "year" in key:
                year = val
            if "label" in key:
                label = val

    # Shazam / Apple Music havolasi
    share     = track.get("share", {})
    track_url = (
        share.get("href")
        or track.get("url")
        or track.get("track_url")
        or ""
    )

    return {
        "title":     title,
        "artist":    artist,
        "genre":     genre,
        "year":      year,
        "label":     label,
        "cover":     cover_url,   # bot.py: result.get("cover")
        "track_url": track_url,
    }


# ══════════════════════════════════════════════
# FORMATLASH
# ══════════════════════════════════════════════

def format_result(info: dict) -> str:
    """
    Natijani Telegram HTML formatida qaytaradi.
    bot.py: '🎧 Qo'shiq topildi!\n\n' + format_result(result)
    """
    if not info:
        return "🎵 Qo'shiq aniqlanmadi."

    lines = [
        f"🎤 <b>Artist:</b> {info.get('artist', '—')}",
        f"🎵 <b>Nomi:</b>   {info.get('title',  '—')}",
    ]

    if info.get("genre"):
        lines.append(f"🎸 <b>Janr:</b>   {info['genre']}")
    if info.get("year"):
        lines.append(f"📅 <b>Yil:</b>    {info['year']}")
    if info.get("label"):
        lines.append(f"🏷 <b>Label:</b>  {info['label']}")
    if info.get("track_url"):
        lines.append(f"\n🔗 <a href='{info['track_url']}'>Shazam'da ochish</a>")

    return "\n".join(lines)


# ══════════════════════════════════════════════
# TEST (terminal orqali)
# ══════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    import asyncio

    if len(sys.argv) < 3:
        print("Ishlatish: python shazam.py <audio_fayl> <RAPIDAPI_KEY>")
        sys.exit(1)

    async def _test():
        result = await recognize_song(sys.argv[1], sys.argv[2])
        if result:
            print(format_result(result))
        else:
            print("Qo'shiq aniqlanmadi.")

    asyncio.run(_test())
