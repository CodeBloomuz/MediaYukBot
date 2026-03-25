"""
Shazam orqali musiqa tanish moduli.
ShazamIO kutubxonasi — bepul, API kalit shart emas.

O'rnatish: pip install shazamio
"""

from shazamio import Shazam
from pathlib import Path


async def recognize_song(file_path: str, rapidapi_key: str = "") -> dict | None:
    """
    Audio faylni ShazamIO orqali taniydi.

    Args:
        file_path   : .ogg, .mp3, .wav, .m4a fayl yo'li
        rapidapi_key: Ishlatilmaydi — bot.py bilan moslik uchun saqlab qolindi

    Returns:
        {title, artist, cover, genre, year, label, track_url} yoki None
    """
    p = Path(file_path)
    if not p.exists() or p.stat().st_size == 0:
        return None

    try:
        shazam = Shazam()
        data   = await shazam.recognize(str(p))

        if not data.get("matches"):
            return None

        track = data.get("track", {})
        if not track:
            return None

        title  = track.get("title",    "")
        artist = track.get("subtitle", "")
        if not title and not artist:
            return None

        # Muqova rasmi
        images = track.get("images", {})
        cover  = images.get("coverarthq") or images.get("coverart") or ""

        # Janr
        genre = track.get("genres", {}).get("primary", "")

        # Yil va label (sections ichida)
        year = label = ""
        for section in track.get("sections", []):
            for meta in section.get("metadata", []):
                key = meta.get("title", "").lower()
                val = meta.get("text",  "")
                if "released" in key or "year" in key:
                    year = val
                if "label" in key:
                    label = val

        track_url = track.get("share", {}).get("href", "")

        return {
            "title":     title,
            "artist":    artist,
            "genre":     genre,
            "year":      year,
            "label":     label,
            "cover":     cover,       # bot.py: result.get("cover")
            "track_url": track_url,
        }

    except Exception as e:
        raise RuntimeError(f"ShazamIO xatosi: {e}") from e


def format_result(info: dict) -> str:
    """Natijani Telegram HTML formatida qaytaradi."""
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
