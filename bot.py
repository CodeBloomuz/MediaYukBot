import logging
from pathlib import Path

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember,
    InputMediaAudio,
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
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 Video",  callback_data="fmt_video"),
            InlineKeyboardButton("🎵 Audio",  callback_data="fmt_audio"),
        ]
    ])

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
        f"🔥 Assalomu alaykum, <b>{name}</b>. "
        f"<b>{CHANNEL_NAME}</b>ga Xush kelibsiz.\n\n"
        f"Bot orqali quyidagilarni yuklab olishingiz mumkin:\n\n"
        f"• <b>Instagram</b> — post va Stories + audio bilan\n"
        f"• <b>TikTok</b> — suv belgisiz video\n"
        f"• <b>YouTube</b> — video + audio bilan birga\n"
        f"• <b>Facebook</b> va <b>Threads</b> — video\n"
        f"• 🎵 <b>Qo'shiq nomi</b> yoki <b>ijrochi ismi</b>\n"
        f"• 📝 <b>Qo'shiq matni</b> — /lyrics buyrug'i bilan\n"
        f"• 🎤 <b>Ovozli xabar</b>, <b>Video</b>, <b>Audio</b>, <b>Video xabar</b>\n\n"
        f"🚀 Media yuklashni boshlash uchun uning havolasini yuboring.",
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
#  FORMAT TANLASH CALLBACK
# ══════════════════════════════════════════════

async def cb_format(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if not await is_subscribed(q.from_user.id, ctx):
        await q.edit_message_text(
            "⛔ Obuna kerak!", reply_markup=sub_keyboard()
        )
        return

    fmt = q.data          # "fmt_video" yoki "fmt_audio"
    url = ctx.user_data.get("pending_url")
    if not url:
        await q.edit_message_text("⚠️ Havola topilmadi. Qaytadan yuboring.")
        return

    await q.edit_message_text(
        f"{'🎬 Video' if fmt == 'fmt_video' else '🎵 Audio'} yuklanmoqda…\nBiroz kuting ⏳"
    )
    await _process(q.message, ctx, url, fmt == "fmt_video", q.from_user.id)

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

    # YouTube uchun format tanlash, qolganlar uchun to'g'ridan video
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
        await ctx.bot.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO if video else ChatAction.UPLOAD_DOCUMENT)

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

        title    = info.get("title","")[:60]
        dur      = duration_str(info.get("duration", 0))
        platform = platform_name(url)

        caption = (
            f"{'🎬' if video else '🎵'} <b>{title}</b>\n"
            f"📌 {platform}  •  ⏱ {dur}\n"
            f"🤖 @{(await ctx.bot.get_me()).username}"
        )

        await msg.edit_text(f"📤 Yuborilmoqda… ({size_mb:.1f} MB)")

        with open(path, "rb") as f:
            if video:
                await ctx.bot.send_video(
                    chat_id, f,
                    caption=caption, parse_mode="HTML",
                    supports_streaming=True,
                )
            else:
                artist = info.get("artist","")
                await ctx.bot.send_audio(
                    chat_id, f,
                    caption=caption, parse_mode="HTML",
                    title=title, performer=artist,
                    duration=info.get("duration",0),
                )
        await msg.delete()

    except yt_dlp.utils.DownloadError as e:
        err = str(e)
        if "private" in err.lower() or "login" in err.lower():
            text = "🔒 Bu xususiy (private) kontent. Yuklab bo'lmaydi."
        elif "not available" in err.lower():
            text = "❌ Kontent mavjud emas yoki o'chirilgan."
        else:
            text = f"❌ Yuklab bo'lmadi:\n<code>{err[:200]}</code>"
        await msg.edit_text(text, parse_mode="HTML")
    except Exception as e:
        log.error(f"_process xato: {e}", exc_info=True)
        await msg.edit_text(f"❌ Xato: <code>{str(e)[:150]}</code>", parse_mode="HTML")
    finally:
        if "path" in locals():
            cleanup(info.get("path",""))

# ══════════════════════════════════════════════
#  QO'SHIQ QIDIRISH — matn yuborganda
# ══════════════════════════════════════════════

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # URL bo'lsa url handleri o'zi olib ketadi
    if is_url(text):
        return

    if not await gate(update, ctx):
        return

    # /lyrics triggeri matnda: "lyrics: Sarvinoz"
    lower = text.lower()
    if lower.startswith("lyrics:") or lower.startswith("matn:"):
        query = text.split(":", 1)[1].strip()
        await _send_lyrics(update, ctx, query)
        return

    # Qo'shiq qidirish
    msg = await update.message.reply_text(
        f"🔍 <b>{text}</b> qidirilmoqda…", parse_mode="HTML"
    )
    await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_DOCUMENT)

    try:
        info = await search_song(text, update.effective_user.id)
        path = Path(info["path"])

        if not path.exists():
            await msg.edit_text("❌ Qo'shiq topilmadi.")
            return

        size_mb = path.stat().st_size / (1024 * 1024)
        title  = info.get("title","")[:60]
        artist = info.get("artist","")
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
            f"❌ Qo'shiq topilmadi yoki yuklab bo'lmadi.\n\n"
            f"<i>Maslahat: To'liqroq nom kiriting, masalan: «Sarvinoz Muhabbat»</i>",
            parse_mode="HTML",
        )
    finally:
        if "info" in locals():
            cleanup(info.get("path",""))

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
            "Misol: <code>/lyrics Shahzoda - Sevinch</code>",
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
        # Telegramda 4096 belgi limit
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
            f"<i>Format: ijrochi ismi - qo'shiq nomi</i>",
            parse_mode="HTML",
        )

# ══════════════════════════════════════════════
#  MEDIA XABARLAR — voice, audio, video, video_note
# ══════════════════════════════════════════════

async def handle_media(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi media yuborsa — qayta yuboradi (forward o'rniga)."""
    if not await gate(update, ctx):
        return
    msg = update.message
    bot_name = (await ctx.bot.get_me()).username

    if msg.voice:
        await ctx.bot.send_voice(
            msg.chat_id, msg.voice.file_id,
            caption=f"🎤 Ovozli xabar\n🤖 @{bot_name}",
        )
    elif msg.video_note:
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
        "YouTube, Instagram, TikTok, Facebook, Threads havolasini yuboring\n\n"
        "<b>🎵 Qo'shiq qidirish:</b>\n"
        "Qo'shiq nomini yoki ijrochi ismini yozing\n"
        "<i>Misol: Xurshid Raximov Ayriliq</i>\n\n"
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
    app.add_handler(CallbackQueryHandler(cb_check_sub, pattern="^check_sub$"))
    app.add_handler(CallbackQueryHandler(cb_format,    pattern="^fmt_"))

    # URL xabarlar
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Regex(r'https?://'),
        handle_url,
    ))

    # Media xabarlar
    app.add_handler(MessageHandler(
        filters.VOICE | filters.VIDEO | filters.AUDIO |
        filters.VIDEO_NOTE | filters.Document.ALL,
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
