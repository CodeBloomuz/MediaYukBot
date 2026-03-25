import logging
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

from config import BOT_TOKEN, CHANNEL_ID, CHANNEL_LINK, CHANNEL_NAME, MAX_SIZE_MB
from downloader import (
    is_url, extract_url, is_supported, platform_name,
    download_media, cleanup, cleanup_list, duration_str,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


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
            f"🔥 Assalomu alaykum, <b>{user.first_name}</b>!\n\n"
            f"👉 Botdan foydalanish uchun avval kanalimizga obuna bo'ling 👇",
            parse_mode="HTML",
            reply_markup=sub_keyboard(),
        )
        return

    await update.message.reply_text(
        f"🔥 Assalomu alaykum, <b>{user.first_name}</b>. "
        f"<b>{CHANNEL_NAME}</b>ga Xush kelibsiz!\n\n"
        f"Bot orqali quyidagilarni yuklab olishingiz mumkin:\n\n"
        f"• <b>Instagram</b> — post, rasm, Reels va Stories\n"
        f"• <b>TikTok</b> — suv belgisiz video\n"
        f"• <b>YouTube</b> — video (1080p gacha)\n"
        f"• <b>Facebook</b> — video va Reels\n"
        f"• <b>Threads</b> — video\n\n"
        f"🚀 Media yuklashni boshlash uchun uning havolasini yuboring.",
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
            "✅ Ishlaydi: YouTube • Instagram • TikTok • Facebook • Threads"
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
                    media_group.append(
                        InputMediaVideo(data, caption=caption, parse_mode="HTML")
                    )
                else:
                    media_group.append(
                        InputMediaPhoto(data, caption=caption, parse_mode="HTML")
                    )
                sent_paths.append(str(p))

            if not media_group:
                await safe_edit(msg, "❌ Yuborish uchun fayl topilmadi.")
                return

            # Telegram max 10 ta media group
            for i in range(0, len(media_group), 10):
                await ctx.bot.send_media_group(chat_id, media_group[i:i+10])

            try:
                await msg.delete()
            except Exception:
                pass
            cleanup_list(sent_paths)
            return

        # ── BITTA MEDIA (video yoki rasm) ─────
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
            text = (
                "🔒 Bu xususiy (private) kontent yuklab bo'lmadi.\n\n"
                "<i>Faqat ochiq profil va postlar ishlaydi.</i>"
            )
        elif "not available" in err or "unavailable" in err or "removed" in err:
            text = "❌ Kontent mavjud emas yoki o'chirilgan."
        elif "429" in err or "too many" in err:
            text = "⏳ Juda ko'p so'rov. 1-2 daqiqa kutib qaytadan urinib ko'ring."
        elif "unsupported url" in err:
            text = "❌ Bu havola qo'llab-quvvatlanmaydi."
        elif "sign in" in err or "age" in err:
            text = "🔞 Bu kontent faqat tizimga kirganlar uchun."
        elif "copyright" in err or "blocked" in err:
            text = "🚫 Bu video mualliflik huquqi sababli bloklanган."
        else:
            short = str(e)[:250]
            text = f"❌ Yuklab bo'lmadi:\n<code>{short}</code>"
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
        "🔗 Iltimos, havola yuboring.\n\n"
        "<b>Misol:</b>\n"
        "<code>https://www.instagram.com/p/...</code>\n"
        "<code>https://www.tiktok.com/@user/video/...</code>\n"
        "<code>https://youtu.be/...</code>",
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
        "Havola yuboring — bot yuklab beradi.\n\n"
        "▶️ <b>YouTube</b> — 1080p gacha video\n"
        "🎬 <b>Instagram</b> — post (rasm/video), Reels, Stories\n"
        "🎵 <b>TikTok</b> — suv belgisiz video\n"
        "📘 <b>Facebook</b> — video, Reels\n"
        "🧵 <b>Threads</b> — video\n\n"
        "⚠️ Xususiy (private) profillar yuklanmaydi.\n"
        "⚠️ Fayl 50 MB dan katta bo'lsa yuklanmaydi.",
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

    # URL kelsa — yukla
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Regex(r'https?://'),
        handle_url,
    ))

    # Boshqa matn — yo'naltir
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_other,
    ))

    log.info("✅ Bot ishga tushdi")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
