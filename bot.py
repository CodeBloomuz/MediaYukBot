import logging
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)
from telegram.constants import ChatAction
import yt_dlp

from config import BOT_TOKEN, CHANNEL_ID, CHANNEL_LINK, CHANNEL_NAME, MAX_SIZE_MB
from downloader import (
    is_url, extract_url, is_supported, platform_name,
    download_media, cleanup, cleanup_list,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════
# YORDAMCHI FUNKSIYALAR
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

def duration_str(sec: int) -> str:
    if not sec:
        return "—"
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

async def gate(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    if await is_subscribed(update.effective_user.id, ctx):
        return True
    await update.effective_message.reply_text(
        "⛔ Botdan foydalanish uchun kanalimizga obuna bo'lishingiz kerak!",
        reply_markup=sub_keyboard(),
    )
    return False

# ══════════════════════════════════════════════
# /start
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

    await update.message.reply_text(
        f"🔥 Assalomu alaykum, <b>{user.first_name}</b>!\n"
        f"<b>{CHANNEL_NAME}</b>ga Xush kelibsiz 🎉\n\n"
        f"Bot orqali quyidagilarni yuklab olishingiz mumkin:\n\n"
        f"🎬 <b>Instagram</b> —  Reels, Stories\n"
        f"📘 <b>Facebook</b> — video, Stories\n"
        f"🚀 Boshlash uchun havola yuboring!",
        parse_mode="HTML",
    )

# ══════════════════════════════════════════════
# OBUNA CALLBACK
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
            "✅ Ishlaydi: YouTube • Instagram • TikTok • Facebook"
        )
        return

    platform = platform_name(url)
    msg = await update.message.reply_text(
        f"⏳ <b>{platform}</b> dan yuklanmoqda…",
        parse_mode="HTML",
    )

    await _process(msg, ctx, url, uid=update.effective_user.id)

# ══════════════════════════════════════════════
# YUKLAB OLISH ASOSIY LOGIKASI
# ══════════════════════════════════════════════

async def _process(msg, ctx, url: str, uid: int):
    chat_id = msg.chat_id

    try:
        await ctx.bot.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)

        info = await download_media(url, uid)
        media_type = info.get("type", "video")

        bot_name = (await ctx.bot.get_me()).username
        platform = platform_name(url)

        # ── RASM yoki CAROUSEL ────────────────────────────────────────────────
        if media_type == "photos":
            paths = info.get("paths", [])
            media_types = info.get("media_types", ["photo"] * len(paths))
            title = info.get("title", "")[:60]
            uploader = info.get("uploader", "")

            if not paths:
                await msg.edit_text("❌ Rasmlar topilmadi.")
                return

            await msg.edit_text(f"📤 {len(paths)} ta media yuborilmoqda…")
            await ctx.bot.send_chat_action(chat_id, ChatAction.UPLOAD_PHOTO)

            caption = (
                f"🖼 <b>{title}</b>\n"
                f"📌 {platform}"
                + (f" • 👤 {uploader}" if uploader else "")
                + f"\n🤖 @{bot_name}"
            )

            # Telegram media group (max 10 ta)
            from telegram import InputMediaPhoto, InputMediaVideo

            media_group = []
            for i, (path, mtype) in enumerate(zip(paths, media_types)):
                p = Path(path)
                if not p.exists():
                    continue

                size_mb = p.stat().st_size / (1024 * 1024)
                if size_mb > MAX_SIZE_MB:
                    log.warning(f"Fayl {size_mb:.1f}MB — o'tkazib yuborildi")
                    continue

                with open(p, "rb") as f:
                    file_data = f.read()

                cap = caption if i == 0 else None

                if mtype == "video":
                    media_group.append(
                        InputMediaVideo(file_data, caption=cap, parse_mode="HTML")
                    )
                else:
                    media_group.append(
                        InputMediaPhoto(file_data, caption=cap, parse_mode="HTML")
                    )

            if not media_group:
                await msg.edit_text("❌ Yuborish uchun fayl topilmadi.")
                cleanup_list(paths)
                return

            # Telegram 1 vaqtda max 10 ta media qabul qiladi
            for i in range(0, len(media_group), 10):
                chunk = media_group[i:i+10]
                await ctx.bot.send_media_group(chat_id, chunk)

            await msg.delete()
            cleanup_list(paths)
            return

        # ── VIDEO ─────────────────────────────────────────────────────────────
        path = Path(info["path"])
        if not path.exists():
            await msg.edit_text("❌ Fayl topilmadi. Qaytadan urinib ko'ring.")
            return

        size_mb = path.stat().st_size / (1024 * 1024)

        if size_mb > MAX_SIZE_MB:
            await msg.edit_text(
                f"⚠️ Fayl hajmi juda katta ({size_mb:.1f} MB).\n"
                f"Telegram {MAX_SIZE_MB} MB dan ortiqni qabul qilmaydi.\n"
                f"Qisqaroq video yuboring."
            )
            cleanup(str(path))
            return

        title = info.get("title", "")[:60]
        dur = duration_str(info.get("duration", 0))
        uploader = info.get("uploader", "")

        caption = (
            f"🎬 <b>{title}</b>\n"
            f"📌 {platform}"
            + (f" • 👤 {uploader}" if uploader else "")
            + (f" • ⏱ {dur}" if dur != "—" else "")
            + f"\n🤖 @{bot_name}"
        )

        await msg.edit_text(f"📤 Yuborilmoqda… ({size_mb:.1f} MB)")
        await ctx.bot.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO)

        with open(path, "rb") as f:
            await ctx.bot.send_video(
                chat_id, f,
                caption=caption,
                parse_mode="HTML",
                supports_streaming=True,
            )

        await msg.delete()

    except yt_dlp.utils.DownloadError as e:
        err = str(e)
        if "private" in err.lower() or "login" in err.lower():
            text = "🔒 Bu xususiy (private) kontent. Yuklab bo'lmaydi.\n\n<i>Faqat ochiq profillar ishlaydi.</i>"
        elif "not available" in err.lower() or "unavailable" in err.lower():
            text = "❌ Kontent mavjud emas yoki o'chirilgan."
        elif "sign in" in err.lower() or "confirm your age" in err.lower():
            text = "🔞 Bu kontent yoshga oid cheklangan. Yuklab bo'lmaydi."
        elif "format" in err.lower():
            text = "❌ Ushbu video formati mavjud emas."
        elif "blocked" in err.lower() or "copyright" in err.lower():
            text = "🚫 Bu video mualliflik huquqi sababli bloklanган."
        else:
            text = f"❌ Yuklab bo'lmadi:\n<code>{err[:200]}</code>"
        await msg.edit_text(text, parse_mode="HTML")

    except Exception as e:
        log.error(f"_process xato: {e}", exc_info=True)
        await msg.edit_text(
            f"❌ Xato yuz berdi:\n<code>{str(e)[:150]}</code>",
            parse_mode="HTML",
        )

    finally:
        if "info" in locals():
            t = info.get("type", "video")
            if t == "photos":
                cleanup_list(info.get("paths", []))
            else:
                cleanup(info.get("path", ""))

# ══════════════════════════════════════════════
# /help
# ══════════════════════════════════════════════

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await gate(update, ctx):
        return

    await update.message.reply_text(
        "📖 <b>Qo'llanma</b>\n\n"
        "<b>Qo'llab-quvvatlanadigan platformalar:</b>\n\n"
        "▶️ <b>YouTube</b>\n"
        "└ Har qanday YouTube video havolasi\n"
        "└ Barcha formatlar (1080p gacha)\n\n"
        "🎬 <b>Instagram</b>\n"
        "└ Post (rasm va carousel)\n"
        "└ Reels va Stories (faqat ochiq profil)\n\n"
        "📘 <b>Facebook</b>\n"
        "└ Video va Stories (faqat ochiq)\n\n"
        "🎵 <b>TikTok</b>\n"
        "└ Suv belgisiz video\n\n"
        "⚠️ <b>Eslatma:</b> Xususiy (private) profillar yuklanmaydi.",
        parse_mode="HTML",
    )

# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CallbackQueryHandler(cb_check_sub, pattern="^check_sub$"))

    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Regex(r'https?://'),
        handle_url,
    ))

    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        lambda u, c: u.message.reply_text(
            "🔗 Iltimos, havola yuboring.\n\n"
            "Misol: <code>https://www.instagram.com/p/...</code>",
            parse_mode="HTML",
        )
    ))

    log.info("✅ Bot ishga tushdi")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
