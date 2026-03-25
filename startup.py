"""
Railway da cookies fayllarini environment variable dan yaratadi.
bot.py ishga tushishidan OLDIN bu skript ishlashi kerak.

Ishlatish (Dockerfile yoki start komandasi):
    python startup.py && python bot.py

Railway Variables ga qo'shing:
    YT_COOKIES   = cookies_yt.txt ning to'liq matni
    IG_COOKIES   = cookies.txt ning to'liq matni (Instagram)
    FB_COOKIES   = cookies_fb.txt ning to'liq matni (Facebook)
"""

import os
import sys


def write_cookie(env_var: str, filename: str):
    content = os.getenv(env_var, "").strip()
    if content:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ {filename} yaratildi ({len(content)} belgi)")
    else:
        print(f"⚠️  {env_var} topilmadi — {filename} yaratilmadi")


if __name__ == "__main__":
    write_cookie("YT_COOKIES", "cookies_yt.txt")
    write_cookie("IG_COOKIES", "cookies.txt")
    write_cookie("FB_COOKIES", "cookies_fb.txt")
    print("✅ Startup tugadi")
