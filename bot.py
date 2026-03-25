import logging
import os
from pathlib import Path

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ChatMember, InputMediaPhoto, InputMediaVideo,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)
from telegram.constants import ChatAction
from telegram.error import BadRequest, TelegramError
import yt_dlp

from config import BOT_TOKEN, CHANNEL_ID, CHANNEL_LINK, CHANNEL_NAME, MAX_SIZE_MB, RAPIDAPI_KEY
from downloader import (
    is_url, extract_url, is_supported, platform_name,
    download_media, cleanup, cleanup_list, duration_str,
)
from shazam import recognize_song, format_result

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

AUDIO_DOWNLOAD_PATH = Path("audio_tmp")
AUDIO_DOWNLOAD_PATH.mkdir(exist_ok=True)


# ══════════════════════════════════════════════
# YORDAMCHI
# ══════════════════════════════════════════════

async def is_subscribed(uid: int, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        m = await ctx.bot.get_chat_member(CHANNEL_ID, uid)
        return m.status in (
            ChatMember.MEMBER,
            ChatMember.ADMINISTRATOR,
            ChatMember.OWNER,
        )
    except Exception as e:
        log.warning(f"Obuna tekshirishda xato: {e}")
        return False

def sub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Kanalga obuna bo'lish", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ Obuna bo'ldim", callback_data="check_sub")],
    ])

async def gate(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    if await is_subscribed(update.effective_user.id, ctx):
        return True
    await update.effective_message.reply_text(
        "⛔ Botdan foydalanish uchun avval kanalimizga obuna bo'ling!",
        reply_markup=sub_keyboard(),
    )
    return False

async def safe_edit(msg, text: str, parse_mode: str = "HTML", **kwargs):
    try:
        await msg.edit_text(text, parse_mode=parse_mode, **kwargs)
    except BadRequest:
        pass
    except Exception as e:
        log.warning(f"safe_edit: {e}")


# ══════════════════════════════════════════════
# /start
# ══════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not await is_subscribed(user.id, ctx):
        await update.message.reply_text(
            f"👋 Salom, <b>{user.first_name}</b>!\n\n"
            f"Botdan foydalanish uchun avval kanalimizga obuna bo'ling 👇",
            parse_mode="HTML",
            reply_markup=sub_keyboard(),
        )
        return

    await update.message.reply_text(
        f"🔥 Assalomu alaykum, <b>{user.first_name}</b>!\n"
        f"<b>{CHANNEL_NAME}</b>ga xush kelibsiz!\n\n"
        f"<b>Nima qila olaman:</b>\n\n"
        f"▶️ <b>YouTube</b> — video (1080p gacha)\n"
        f"📸 <b>Instagram</b> — post, rasm, Reels, Stories\n"
        f"📘 <b>Facebook</b> — video, Reels, Stories\n\n"
        f"🎵 <b>Qo'shiq topish</b> — ovozli xabar yoki audio yuboring\n\n"
        f"🔗 Havola yuboring — bot yuklab beradi!\n"
        f"🎤 Audio yuboring — bot qo'shiq nomini topib beradi!",
        parse_mode="HTML",
    )


# ══════════════════════════════════════════════
# /help
# ══════════════════════════════════════════════

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await gate(update, ctx):
        return
    await update.message.reply_text(
        "📖 <b>Qo'llanma</b>\n\n"
        "▶️ <b>YouTube</b> — video (1080p gacha)\n"
        "📸 <b>Instagram</b> — post, rasm, Reels, Stories\n"
        "📘 <b>Facebook</b> — video, Reels, Stories\n\n"
        "🎵 <b>Qo'shiq topish:</b>\n"
        "  • Ovozli xabar yuboring\n"
        "  • Yoki audio/mp3 fayl yuboring\n"
        "  • Bot qo'shiq nomini topib beradi\n\n"
        "⚠️ <b>Eslatmalar:</b>\n"
        f"  • Xususiy (private) profil yuklanmaydi\n"
        f"  • {MAX_SIZE_MB} MB dan katta fayl yuklanmaydi",
        parse_mode="HTML",
    )


# ══════════════════════════════════════════════
# OBUNA CALLBACK
# ══════════════════════════════════════════════

async def cb_check_sub(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass

    if await is_subscribed(q.from_user.id, ctx):
        await safe_edit(
            q.message,
            "✅ <b>Obuna tasdiqlandi!</b>\n\n"
            "Endi havolani yuboring — bot yuklab beradi! 🚀",
        )
    else:
        await safe_edit(
            q.message,
            "❌ Siz hali kanalga obuna bo'lmagansiz.\n"
            "Obuna bo'lib, qaytadan bosing.",
            reply_markup=sub_keyboard(),
        )


# ══════════════════════════════════════════════
# 🎵 QOʻSHIQ TOPISH — ovozli xabar va audio
# ══════════════════════════════════════════════

async def handle_audio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await gate(update, ctx):
        return

    msg = update.message
    audio_file = None

    # Ovozli xabar (voice) yoki audio/mp3 faylni aniqlash
    if msg.voice:
        audio_file = msg.voice
        file_ext = "ogg"
    elif msg.audio:
        audio_file = msg.audio
        # Fayl nomidan kengaytma olish
        fname = msg.audio.file_name or "audio.mp3"
        file_ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else "mp3"
    elif msg.document:
        doc = msg.document
        mime = doc.mime_type or ""
        fname = doc.file_name or ""
        if not (mime.startswith("audio/") or fname.lower().endswith((".mp3", ".ogg", ".wav", ".flac", ".m4a", ".aac"))):
            return
        audio_file = doc
        file_ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else "mp3"
    else:
        return

    status = await msg.reply_text("🎵 Qo'shiq aniqlanmoqda…")

    # Faylni yuklab olish
    uid = update.effective_user.id
    local_path = AUDIO_DOWNLOAD_PATH / f"{uid}_shazam.{file_ext}"

    try:
        await ctx.bot.send_chat_action(msg.chat_id, ChatAction.TYPING)
        tg_file = await ctx.bot.get_file(audio_file.file_id)
        await tg_file.download_to_drive(str(local_path))

        result = await recognize_song(str(local_path), RAPIDAPI_KEY)

        if result and result.get("title"):
            text = "🎧 <b>Qo'shiq topildi!</b>\n\n" + format_result(result)

            # Cover rasm bor bo'lsa rasm bilan yuborish
            if result.get("cover"):
                try:
                    await status.delete()
                    await msg.reply_photo(
                        photo=result["cover"],
                        caption=text,
                        parse_mode="HTML",
                    )
                except Exception:
                    await safe_edit(status, text)
            else:
                await safe_edit(status, text)
        else:
            await safe_edit(
                status,
                "❌ Qo'shiq aniqlanmadi.\n\n"
                "Ovoz sifatli bo'lishi va kamida 5 soniya bo'lishi kerak."
            )

    except Exception as e:
        log.error(f"Shazam xato: {e}", exc_info=True)
        await safe_edit(status, "❌ Qo'shiq aniqlanmadi. Qaytadan urinib ko'ring.")

    finally:
        try:
            local_path.unlink(missing_ok=True)
        except Exception:
            pass


# ══════════════════════════════════════════════
# URL HANDLER
# ══════════════════════════════════════════════

async def handle_url(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await gate(update, ctx):
        return

    url = extract_url(update.message.text)
    if not url:
        return

    if not is_supported(url):
        await update.message.reply_text(
            "❌ Bu platforma qo'llab-quvvatlanmaydi.\n\n"
            "✅ Ishlaydi:\n"
            "▶️ YouTube\n"
            "📸 Instagram\n"
            "📘 Facebook"
        )
        return

    plat = platform_name(url)
    msg = await update.message.reply_text(
        f"⏳ <b>{plat}</b> dan yuklanmoqda…",
        parse_mode="HTML",
    )

    await _process(msg, ctx, url, uid=update.effective_user.id)


# ══════════════════════════════════════════════
# ASOSIY YUKLAB OLISH VA YUBORISH
# ══════════════════════════════════════════════

async def _process(msg, ctx, url: str, uid: int):
    chat_id = msg.chat_id
    info = None

    try:
        await ctx.bot.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)

        info = await download_media(url, uid)

        plat     = platform_name(url)
        bot_name = (await ctx.bot.get_me()).username

        # ── MEDIA LIST (Stories, Carousel) ────
        if info.get("media_list"):
            items    = info.get("items", [])
            uploader = info.get("uploader", "")

            if not items:
                await safe_edit(msg, "❌ Media topilmadi.")
                return

            await safe_edit(msg, f"📤 {len(items)} ta media yuborilmoqda…")

            media_group = []
            sent_paths  = []

            for i, item in enumerate(items):
                p = Path(item["path"])
                if not p.exists():
                    continue
                size_mb = p.stat().st_size / (1024 * 1024)
                if size_mb > MAX_SIZE_MB:
                    log.warning(f"O'tkazib yuborildi: {size_mb:.1f} MB")
                    continue

                caption = None
                if i == 0:
                    caption = (
                        f"📌 {plat}"
                        + (f" • 👤 {uploader}" if uploader else "")
                        + f"\n🤖 @{bot_name}"
                    )

                with open(p, "rb") as f:
                    data = f.read()

                if item["type"] == "video":
                    media_group.append(InputMediaVideo(data, caption=caption, parse_mode="HTML"))
                else:
                    media_group.append(InputMediaPhoto(data, caption=caption, parse_mode="HTML"))
                sent_paths.append(str(p))

            if not media_group:
                await safe_edit(msg, "❌ Yuborish uchun fayl topilmadi.")
                return

            for i in range(0, len(media_group), 10):
                await ctx.bot.send_media_group(chat_id, media_group[i:i+10])

            try:
                await msg.delete()
            except Exception:
                pass
            cleanup_list(sent_paths)
            return

        # ── BITTA MEDIA ───────────────────────
        mtype = info.get("type", "video")
        path  = Path(info["path"])

        if not path.exists():
            await safe_edit(msg, "❌ Fayl topilmadi. Qaytadan urinib ko'ring.")
            return

        size_mb  = path.stat().st_size / (1024 * 1024)
        title    = info.get("title", "")[:60]
        dur      = duration_str(info.get("duration", 0))
        uploader = info.get("uploader", "")

        if size_mb > MAX_SIZE_MB:
            await safe_edit(
                msg,
                f"⚠️ Fayl hajmi juda katta ({size_mb:.1f} MB).\n"
                f"Telegram {MAX_SIZE_MB} MB dan ortiqni qabul qilmaydi.",
            )
            cleanup(str(path))
            return

        caption = (
            f"{'🎬' if mtype == 'video' else '🖼'} <b>{title}</b>\n"
            f"📌 {plat}"
            + (f" • 👤 {uploader}" if uploader else "")
            + (f" • ⏱ {dur}" if dur else "")
            + f"\n🤖 @{bot_name}"
        )

        await safe_edit(msg, f"📤 Yuborilmoqda… ({size_mb:.1f} MB)")

        with open(path, "rb") as f:
            if mtype == "video":
                await ctx.bot.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO)
                await ctx.bot.send_video(
                    chat_id, f,
                    caption=caption,
                    parse_mode="HTML",
                    supports_streaming=True,
                )
            else:
                await ctx.bot.send_chat_action(chat_id, ChatAction.UPLOAD_PHOTO)
                await ctx.bot.send_photo(
                    chat_id, f,
                    caption=caption,
                    parse_mode="HTML",
                )

        try:
            await msg.delete()
        except Exception:
            pass

    except yt_dlp.utils.DownloadError as e:
        err = str(e).lower()
        if "private" in err or "login" in err or "authentication" in err or "cookies" in err:
            text = "🔒 Bu xususiy (private) kontent yuklab bo'lmadi.\n<i>Faqat ochiq profil va postlar ishlaydi.</i>"
        elif "not available" in err or "unavailable" in err or "removed" in err:
            text = "❌ Kontent mavjud emas yoki o'chirilgan."
        elif "429" in err or "too many" in err:
            text = "⏳ Juda ko'p so'rov. 1-2 daqiqa kutib qaytadan urinib ko'ring."
        elif "unsupported url" in err:
            text = "❌ Bu havola qo'llab-quvvatlanmaydi."
        elif "sign in" in err or "age" in err:
            text = "🔞 Bu kontent faqat tizimga kirganlar uchun."
        elif "copyright" in err or "blocked" in err:
            text = "🚫 Bu video mualliflik huquqi sababli bloklangan."
        else:
            text = f"❌ Yuklab bo'lmadi:\n<code>{str(e)[:250]}</code>"
        await safe_edit(msg, text)

    except FileNotFoundError:
        await safe_edit(msg, "❌ Fayl topilmadi. Qaytadan urinib ko'ring.")

    except TelegramError as e:
        log.error(f"Telegram xato: {e}")
        await safe_edit(msg, f"❌ Yuborishda xato: <code>{str(e)[:150]}</code>")

    except Exception as e:
        log.error(f"_process umumiy xato: {e}", exc_info=True)
        await safe_edit(msg, f"❌ Xato yuz berdi:\n<code>{str(e)[:200]}</code>")

    finally:
        if info:
            if info.get("media_list"):
                cleanup_list([i["path"] for i in info.get("items", [])])
            elif info.get("path"):
                cleanup(info["path"])


# ══════════════════════════════════════════════
# NOTO'G'RI XABAR
# ══════════════════════════════════════════════

async def handle_other(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await gate(update, ctx):
        return
    await update.message.reply_text(
        "🔗 Havola yuboring yoki 🎵 audio yuboring.\n\n"
        "<b>Havola misoli:</b>\n"
        "<code>https://www.instagram.com/p/...</code>\n"
        "<code>https://www.facebook.com/watch/...</code>\n"
        "<code>https://youtu.be/...</code>\n\n"
        "<b>Qo'shiq topish uchun:</b>\n"
        "Ovozli xabar yoki audio fayl yuboring 🎤",
        parse_mode="HTML",
    )


# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(CallbackQueryHandler(cb_check_sub, pattern="^check_sub$"))

    # Ovozli xabar
    app.add_handler(MessageHandler(filters.VOICE, handle_audio))

    # Audio fayl va audio document (mp3 va h.k.)
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    app.add_handler(MessageHandler(
        filters.Document.MimeType("audio/mpeg") |
        filters.Document.MimeType("audio/ogg") |
        filters.Document.MimeType("audio/wav") |
        filters.Document.MimeType("audio/flac") |
        filters.Document.MimeType("audio/mp4") |
        filters.Document.MimeType("audio/aac"),
        handle_audio,
    ))

    # URL
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Regex(r'https?://'),
        handle_url,
    ))

    # Boshqa matn
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_other,
    ))

    log.info("✅ Bot ishga tushdi")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
