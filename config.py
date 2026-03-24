import os
from dotenv import load_dotenv

# Lokal ishlatganda .env fayldan o'qiydi
# Railway da Variables bo'limidan o'qiydi
load_dotenv()

BOT_TOKEN    = os.environ["BOT_TOKEN"]
CHANNEL_ID   = os.environ["CHANNEL_ID"]
CHANNEL_LINK = os.environ["CHANNEL_LINK"]
CHANNEL_NAME = os.environ.get("CHANNEL_NAME", "Kanal")

DOWNLOAD_DIR  = "downloads"
MAX_SIZE_MB   = 50
AUDIO_QUALITY = "192"
GENIUS_TOKEN  = os.environ.get("GENIUS_TOKEN", "")
