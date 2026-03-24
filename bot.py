import logging
from pathlib import Path

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)
from telegram.constants import ChatAction
import yt_dlp

from config import BOT_TOKEN, CHANNEL_ID, CHANNEL_LINK, CHANNEL_NAME, MAX_SIZE_MB
from downloader import (
    is_url, extract_url, is_supported, platform_name,
    download_video, download_audio, search_song, fetch_lyrics, cleanup,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════
#  YORDAMCHI FUNKSIYALAR
# ══════════════════════════════════════════════

async def is_subscribed(uid: int, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        m = await ctx.bot.get_chat_member(CHANNEL_ID, uid)
        return m.status in (ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER)
    except Exception as e:
        log.warning(f"Obuna tekshirishda xato: {e}")
        return False

def sub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Kanalga obuna bo'lish", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ Obuna bo'ldim", callback_data="check_sub")],
    ])

def fmt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🎬 Video",  callback_data="fmt_video"),
        InlineKeyboardButton("🎵 Audio",  callback_data="fmt_audio"),
    ]])

def audio_from_video_keyboard(url: str) -> InlineKeyboardMarkup:
    """Video yuborilgandan keyin audio yuklab olish tugmasi."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🎵 Musiqasini yuklab olish", callback_data=f"dl_audio|{url}"),
    ]])

def duration_str(sec: int) -> str:
    if not sec: return "—"
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

async def gate(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    """True = foydalanuvchi obuna bo'lgan."""
    if await is_subscribed(update.effective_user.id, ctx):
        return True
    await update.effective_message.reply_text(
        "⛔ Botdan foydalanish uchun kanalimizga obuna bo'lishingiz kerak!",
        reply_markup=sub_keyboard(),
    )
    return False

# ══════════════════════════════════════════════
#  /start
# ══════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not await is_subscribed(user.id, ctx):
        await update.message.reply_text(
            f"🔥 Assalomu alaykum, <b>{user.first_name}</b>!\n\n"
            f"👉 Botdan foydalanish uchun avval kanalimizga obuna bo'ling 👇",
            parse_mode="HTML",
            reply_markup=sub_keyboard(),
        )
        return
    await send_welcome(update, user.first_name)

async def send_welcome(update, name: str):
    await update.effective_message.reply_text(
        f"🔥 Assalomu alaykum, <b>{name}</b>!\n"
        f"<b>{CHANNEL_NAME}</b>ga Xush kelibsiz 🎉\n\n"
        f"Bot orqali quyidagilarni yuklab olishingiz mumkin:\n\n"
        f"🎬 <b>Instagram</b> — post, Reels, Stories\n"
        f"🎵 <b>TikTok</b> — suv belgisiz video\n"
        f"▶️ <b>YouTube</b> — video yoki audio\n"
        f"📘 <b>Facebook</b> — video\n"
        f"🧵 <b>Threads</b> — video\n\n"
        f"🎵 <b>Qo'shiq qidirish:</b> nom yoki ijrochi ismini yozing\n"
        f"🎤 <b>Ovozli xabar:</b> qo'shiq nomini aytib yuboring\n"
        f"📝 <b>Qo'shiq matni:</b> /lyrics buyrug'i\n\n"
        f"🚀 Boshlash uchun havola yoki qo'shiq nomini yuboring!",
        parse_mode="HTML",
    )

# ══════════════════════════════════════════════
#  OBUNA CALLBACK
# ══════════════════════════════════════════════

async def cb_check_sub(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if await is_subscribed(q.from_user.id, ctx):
        await q.edit_message_text(
            "✅ <b>Obuna tasdiqlandi!</b>\n\n"
            "Endi havolani yuboring — bot yuklab beradi! 🚀",
            parse_mode="HTML",
        )
    else:
        await q.edit_message_text(
            "❌ Siz hali kanalga obuna bo'lmagansiz.\n"
            "Obuna bo'lib, qaytadan bosing.",
            parse_mode="HTML",
            reply_markup=sub_keyboard(),
        )

# ══════════════════════════════════════════════
#  FORMAT TANLASH CALLBACK (YouTube)
# ══════════════════════════════════════════════

async def cb_format(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass

    if not await is_subscribed(q.from_user.id, ctx):
        await q.edit_message_text("⛔ Obuna kerak!", reply_markup=sub_keyboard())
        return

    fmt = q.data   # "fmt_video" yoki "fmt_audio"
    url = ctx.user_data.get("pending_url")
    if not url:
        await q.edit_message_text("⚠️ Havola topilmadi. Qaytadan yuboring.")
        return

    await q.edit_message_text(
        f"{'🎬 Video' if fmt == 'fmt_video' else '🎵 Audio'} yuklanmoqda…\nBiroz kuting ⏳"
    )
    await _process(q.message, ctx, url, fmt == "fmt_video", q.from_user.id)

# ══════════════════════════════════════════════
#  VIDEO DAN AUDIO YUKLAB OLISH CALLBACK
# ══════════════════════════════════════════════

async def cb_download_audio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Video xabari ostidagi '🎵 Musiqasini yuklab olish' tugmasi."""
    q = update.callback_query
    await q.answer("🎵 Audio yuklanmoqda…")

    if not await is_subscribed(q.from_user.id, ctx):
        await q.message.reply_text("⛔ Obuna kerak!", reply_markup=sub_keyboard())
        return

    # callback_data = "dl_audio|https://..."
    url = q.data.split("|", 1)[1] if "|" in q.data else ""
    if not url:
        await q.message.reply_text("⚠️ URL topilmadi.")
        return

    msg = await q.message.reply_text("🎵 Audio yuklanmoqda… ⏳")
    await ctx.bot.send_chat_action(q.message.chat_id, ChatAction.UPLOAD_DOCUMENT)

    try:
        info = await download_audio(url, q.from_user.id)
        path = Path(info["path"])

        if not path.exists():
            await msg.edit_text("❌ Audio fayl topilmadi.")
            return

        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > MAX_SIZE_MB:
            await msg.edit_text(f"⚠️ Fayl hajmi katta ({size_mb:.1f} MB). Telegram {MAX_SIZE_MB} MB dan ortiqni qabul qilmaydi.")
            cleanup(str(path))
            return

        title  = info.get("title", "")[:60]
        artist = info.get("artist", "")
        dur    = duration_str(info.get("duration", 0))
        bot_name = (await ctx.bot.get_me()).username

        caption = (
            f"🎵 <b>{title}</b>\n"
            f"👤 {artist}  •  ⏱ {dur}\n"
            f"🤖 @{bot_name}"
        )
        await msg.edit_text(f"📤 Yuborilmoqda… ({size_mb:.1f} MB)")
        with open(path, "rb") as f:
            await ctx.bot.send_audio(
                q.message.chat_id, f,
                caption=caption, parse_mode="HTML",
                title=title, performer=artist,
                duration=info.get("duration", 0),
            )
        await msg.delete()

    except Exception as e:
        log.error(f"cb_download_audio xato: {e}", exc_info=True)
        await msg.edit_text(f"❌ Audio yuklab bo'lmadi:\n<code>{str(e)[:150]}</code>", parse_mode="HTML")
    finally:
        if "info" in locals():
            cleanup(info.get("path", ""))

# ══════════════════════════════════════════════
#  URL HANDLER
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
            "✅ Ishlaydi: YouTube • Instagram • TikTok • Facebook • Threads"
        )
        return

    # YouTube uchun format tanlash
    if "youtu" in url.lower():
        ctx.user_data["pending_url"] = url
        await update.message.reply_text(
            f"📌 <b>{platform_name(url)}</b>\n\nQaysi formatda yuklayman?",
            parse_mode="HTML",
            reply_markup=fmt_keyboard(),
        )
    else:
        msg = await update.message.reply_text(
            f"⏳ <b>{platform_name(url)}</b> dan yuklanmoqda…",
            parse_mode="HTML",
        )
        await _process(msg, ctx, url, video=True, uid=update.effective_user.id)

# ══════════════════════════════════════════════
#  UMUMIY YUKLAB OLISH LOGIKASI
# ══════════════════════════════════════════════

async def _process(msg, ctx, url: str, video: bool, uid: int):
    chat_id = msg.chat_id

    try:
        await ctx.bot.send_chat_action(
            chat_id, ChatAction.UPLOAD_VIDEO if video else ChatAction.UPLOAD_DOCUMENT
        )

        if video:
            info = await download_video(url, uid)
        else:
            info = await download_audio(url, uid)

        path = Path(info["path"])
        if not path.exists():
            await msg.edit_text("❌ Fayl topilmadi. Qaytadan urinib ko'ring.")
            return

        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > MAX_SIZE_MB:
            await msg.edit_text(
                f"⚠️ Fayl hajmi juda katta ({size_mb:.1f} MB).\n"
                f"Telegram {MAX_SIZE_MB} MB dan ortiqni qabul qilmaydi.\n"
                f"Qisqaroq video/audio yuboring."
            )
            cleanup(str(path))
            return

        title    = info.get("title", "")[:60]
        dur      = duration_str(info.get("duration", 0))
        platform = platform_name(url)
        bot_name = (await ctx.bot.get_me()).username

        caption = (
            f"{'🎬' if video else '🎵'} <b>{title}</b>\n"
            f"📌 {platform}  •  ⏱ {dur}\n"
            f"🤖 @{bot_name}"
        )

        await msg.edit_text(f"📤 Yuborilmoqda… ({size_mb:.1f} MB)")

        with open(path, "rb") as f:
            if video:
                # Video pastida audio yuklab olish tugmasi
                reply_markup = audio_from_video_keyboard(url)
                await ctx.bot.send_video(
                    chat_id, f,
                    caption=caption, parse_mode="HTML",
                    supports_streaming=True,
                    reply_markup=reply_markup,
                )
            else:
                artist = info.get("artist", "")
                await ctx.bot.send_audio(
                    chat_id, f,
                    caption=caption, parse_mode="HTML",
                    title=title, performer=artist,
                    duration=info.get("duration", 0),
                )

        await msg.delete()

    except yt_dlp.utils.DownloadError as e:
        err = str(e)
        if "private" in err.lower() or "login" in err.lower():
            text = "🔒 Bu xususiy (private) kontent. Yuklab bo'lmaydi."
        elif "not available" in err.lower() or "unavailable" in err.lower():
            text = "❌ Kontent mavjud emas yoki o'chirilgan."
        elif "format" in err.lower():
            text = "❌ Ushbu video formati mavjud emas. Boshqa havola yuboring."
        else:
            text = f"❌ Yuklab bo'lmadi:\n<code>{err[:200]}</code>"
        await msg.edit_text(text, parse_mode="HTML")

    except Exception as e:
        log.error(f"_process xato: {e}", exc_info=True)
        await msg.edit_text(f"❌ Xato: <code>{str(e)[:150]}</code>", parse_mode="HTML")

    finally:
        if "info" in locals():
            cleanup(info.get("path", ""))

# ══════════════════════════════════════════════
#  QO'SHIQ QIDIRISH — matn yuborganda
# ══════════════════════════════════════════════

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if is_url(text):
        return

    if not await gate(update, ctx):
        return

    lower = text.lower()
    if lower.startswith("lyrics:") or lower.startswith("matn:"):
        query = text.split(":", 1)[1].strip()
        await _send_lyrics(update, ctx, query)
        return

    await _search_and_send_song(update, ctx, text)

async def _search_and_send_song(update, ctx, query: str):
    """Qo'shiq qidiradi va yuboradi."""
    msg = await update.effective_message.reply_text(
        f"🔍 <b>{query}</b> qidirilmoqda…", parse_mode="HTML"
    )
    await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_DOCUMENT)

    try:
        info = await search_song(query, update.effective_user.id)
        path = Path(info["path"])

        if not path.exists():
            await msg.edit_text("❌ Qo'shiq topilmadi.")
            return

        size_mb = path.stat().st_size / (1024 * 1024)
        title  = info.get("title", "")[:60]
        artist = info.get("artist", "")
        dur    = duration_str(info.get("duration", 0))
        bot_name = (await ctx.bot.get_me()).username

        caption = (
            f"🎵 <b>{title}</b>\n"
            f"👤 {artist}  •  ⏱ {dur}\n"
            f"🤖 @{bot_name}"
        )

        await msg.edit_text(f"📤 Yuborilmoqda… ({size_mb:.1f} MB)")
        with open(path, "rb") as f:
            await ctx.bot.send_audio(
                update.effective_chat.id, f,
                caption=caption, parse_mode="HTML",
                title=title, performer=artist,
                duration=info.get("duration", 0),
            )
        await msg.delete()

    except Exception as e:
        log.error(f"Song search xato: {e}", exc_info=True)
        await msg.edit_text(
            f"❌ <b>«{query}»</b> topilmadi yoki yuklab bo'lmadi.\n\n"
            f"<i>💡 Maslahat: To'liqroq yozing, masalan:\n"
            f"«Xurshid Raximov Ayriliq» yoki «Dua Lipa Levitating»</i>",
            parse_mode="HTML",
        )
    finally:
        if "info" in locals():
            cleanup(info.get("path", ""))

# ══════════════════════════════════════════════
#  OVOZLI XABAR — qo'shiq qidirish
# ══════════════════════════════════════════════

async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi ovozli xabar yuborsa — qo'shiq deb qidiradi."""
    if not await gate(update, ctx):
        return

    msg = update.message
    voice = msg.voice

    # Ovozli xabarni text sifatida qidirish uchun caption tekshirish
    # (Telegram voice-to-text API yo'q, shuning uchun caption'dan olamiz)
    query = msg.caption if msg.caption else None

    if not query:
        await msg.reply_text(
            "🎤 Ovozli xabar qabul qilindi!\n\n"
            "❓ Qaysi qo'shiqni qidirmoqchisiz?\n"
            "<i>Qo'shiq nomini yozing yoki ovozli xabarga caption qo'shing.</i>",
            parse_mode="HTML",
        )
        # Keyingi xabarni kutish uchun state saqlash
        ctx.user_data["waiting_for_song_query"] = True
        return

    await _search_and_send_song(update, ctx, query)

# ══════════════════════════════════════════════
#  LYRICS COMMAND
# ══════════════════════════════════════════════

async def cmd_lyrics(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await gate(update, ctx):
        return
    query = " ".join(ctx.args).strip() if ctx.args else ""
    if not query:
        await update.message.reply_text(
            "📝 Ishlatish: <code>/lyrics ijrochi - qo'shiq nomi</code>\n\n"
            "Misol: <code>/lyrics Dua Lipa - Levitating</code>",
            parse_mode="HTML",
        )
        return
    await _send_lyrics(update, ctx, query)

async def _send_lyrics(update: Update, ctx: ContextTypes.DEFAULT_TYPE, query: str):
    msg = await update.effective_message.reply_text(
        f"🔍 Qo'shiq matni qidirilmoqda: <b>{query}</b>…",
        parse_mode="HTML",
    )
    lyrics = await fetch_lyrics(query)
    if lyrics:
        chunks = [lyrics[i:i+4000] for i in range(0, len(lyrics), 4000)]
        await msg.edit_text(
            f"📝 <b>{query}</b>\n\n{chunks[0]}",
            parse_mode="HTML",
        )
        for chunk in chunks[1:]:
            await update.effective_message.reply_text(chunk)
    else:
        await msg.edit_text(
            f"❌ <b>{query}</b> uchun matn topilmadi.\n\n"
            f"<i>Format: «ijrochi ismi - qo'shiq nomi»\n"
            f"Misol: /lyrics Shahzoda - Sevinch</i>",
            parse_mode="HTML",
        )

# ══════════════════════════════════════════════
#  MEDIA XABARLAR — audio, video, video_note, document
# ══════════════════════════════════════════════

async def handle_media(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi media yuborsa — qayta yuboradi."""
    if not await gate(update, ctx):
        return
    msg = update.message
    bot_name = (await ctx.bot.get_me()).username

    if msg.video_note:
        await ctx.bot.send_video_note(msg.chat_id, msg.video_note.file_id)
    elif msg.video:
        await ctx.bot.send_video(
            msg.chat_id, msg.video.file_id,
            caption=f"🎬 Video\n🤖 @{bot_name}",
        )
    elif msg.audio:
        await ctx.bot.send_audio(
            msg.chat_id, msg.audio.file_id,
            caption=f"🎵 Audio\n🤖 @{bot_name}",
        )
    elif msg.document:
        await ctx.bot.send_document(
            msg.chat_id, msg.document.file_id,
            caption=f"📄 Fayl\n🤖 @{bot_name}",
        )

# ══════════════════════════════════════════════
#  /help
# ══════════════════════════════════════════════

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await gate(update, ctx):
        return
    await update.message.reply_text(
        "📖 <b>Qo'llanma</b>\n\n"
        "<b>🔗 Havola yuborish:</b>\n"
        "YouTube, Instagram, TikTok, Facebook, Threads havolasini yuboring\n"
        "↳ Video yuborilgandan keyin <b>«🎵 Musiqasini yuklab olish»</b> tugmasi chiqadi\n\n"
        "<b>🎵 Qo'shiq qidirish:</b>\n"
        "Qo'shiq nomini yoki ijrochi ismini yozing\n"
        "<i>Misol: Xurshid Raximov Ayriliq</i>\n\n"
        "<b>🎤 Ovozli xabar:</b>\n"
        "Caption qo'shib ovozli xabar yuboring — bot qo'shiq qidiradi\n\n"
        "<b>📝 Qo'shiq matni:</b>\n"
        "<code>/lyrics ijrochi - qo'shiq</code>\n"
        "<i>Misol: /lyrics Dua Lipa - Levitating</i>\n\n"
        "<b>Qo'llab-quvvatlanadigan platformalar:</b>\n"
        "▸ YouTube (video va audio)\n"
        "▸ Instagram (post, Reels, Stories)\n"
        "▸ TikTok (suv belgisiz)\n"
        "▸ Facebook va Threads\n\n"
        "⚠️ Xususiy (private) kontentlar yuklanmaydi.",
        parse_mode="HTML",
    )

# ══════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Commandlar
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("lyrics", cmd_lyrics))

    # Callbacklar
    app.add_handler(CallbackQueryHandler(cb_check_sub,      pattern="^check_sub$"))
    app.add_handler(CallbackQueryHandler(cb_format,         pattern="^fmt_"))
    app.add_handler(CallbackQueryHandler(cb_download_audio, pattern="^dl_audio\\|"))

    # URL xabarlar
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Regex(r'https?://'),
        handle_url,
    ))

    # Ovozli xabarlar
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # Media xabarlar (voice emas)
    app.add_handler(MessageHandler(
        filters.VIDEO | filters.AUDIO | filters.VIDEO_NOTE | filters.Document.ALL,
        handle_media,
    ))

    # Matn (URL emas) → qo'shiq qidirish
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_text,
    ))

    log.info("✅ Bot ishga tushdi")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
