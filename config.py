import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN    = os.getenv("BOT_TOKEN",    "")
CHANNEL_ID   = os.getenv("CHANNEL_ID",   "")
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "")
CHANNEL_NAME = os.getenv("CHANNEL_NAME", "")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")

MAX_SIZE_MB  = int(os.getenv("MAX_SIZE_MB", "50"))

# Ishga tushganda majburiy o'zgaruvchilarni tekshir
_required = {
    "BOT_TOKEN":    BOT_TOKEN,
    "CHANNEL_ID":   CHANNEL_ID,
    "CHANNEL_LINK": CHANNEL_LINK,
    "RAPIDAPI_KEY": RAPIDAPI_KEY,
}
_missing = [k for k, v in _required.items() if not v]
if _missing:
    raise RuntimeError(f"❌ .env da quyidagilar yo'q: {', '.join(_missing)}")
