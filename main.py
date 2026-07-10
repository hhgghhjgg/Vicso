import os
import re
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, Router, types
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command

# تنظیمات لاگ سرور برای خطایابی دقیق
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# دریافت توکن و آدرس سرور از تنظیمات هاست (Environment Variables)
BOT_TOKEN = os.getenv("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

if not BOT_TOKEN:
    raise ValueError("خطا: توکن ربات (BOT_TOKEN) در متغیرهای محیطی یافت نشد!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

WEBHOOK_PATH = f"/bot/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}" if RENDER_EXTERNAL_URL else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """مدیریت فرآیند وب‌هوک هنگام روشن و خاموش شدن سرور"""
    if WEBHOOK_URL:
        logger.info(f"در حال اتصال وب‌هوک به: {WEBHOOK_URL}")
        await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    else:
        logger.warning("RENDER_EXTERNAL_URL تعریف نشده است؛ وب‌هوک ست نشد.")
    yield
    logger.info("در حال قطع اتصال سشن با تلگرام...")
    await bot.session.close()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "ok", "message": "ربات فعال است."}


@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    try:
        json_data = await request.json()
        update = types.Update.model_validate(json_data, context={"bot": bot})
        await dp.feed_update(bot, update)
    except Exception as e:
        logger.error(f"خطا در دریافت و ثبت آپدیت وب‌هوک: {e}")
    return {"ok": True}


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 سلام به ربات تمپلت‌بات خوش آمدید!\n\n"
        "هر پستی (متن خالی، عکس‌دار، ویدیو، گیف، ویس و...) را برام بفرست تا قالب‌بندی متنت "
        "(بولد، کج، لینک‌ها و...) رو کاملاً حفظ کنم، جلوی آیدی‌های داخل متن کلمه «منبع» رو بذارم "
        "و امضای کانال رو در انتهای اون قرار بدم."
    )


async def process_text_and_add_template(message: types.Message) -> str:
    """دریافت متن، پردازش آیدی‌های منبع و چسباندن امضای نهایی"""
    original_html = ""

    if message.text:
        original_html = message.html_text
    elif message.caption:
        original_html = message.html_text

    # آیدی‌های تبلیغاتی ثابت شما که نباید کلمه «منبع» جلوی آن‌ها قرار بگیرد
    ignored_usernames = {"manhwalist_ir", "manhwa_list_ir", "eryuanovel"}
    
    has_custom_source = False

    # الگوی رگکس برای تشخیص تگ‌های HTML یا آیدی‌ها به منظور حفظ لینک‌ها و استایل‌ها
    pattern = re.compile(r"(<[^>]+>)|@([a-zA-Z0-9_]+)")

    def replace_match(match):
        nonlocal has_custom_source
        if match.group(1):  # اگر تگ HTML باشد، آن را بدون دستکاری برگردان
            return match.group(1)
        else:  # اگر آیدی تلگرام باشد
            username = match.group(2)
            if username.lower() not in ignored_usernames:
                has_custom_source = True
                return f"@{username} منبع"
            return f"@{username}"

    processed_html = pattern.sub(replace_match, original_html) if original_html else ""

    # امضای ثابت و نهایی کانال شما شامل عقرب‌ها و آیکون‌ها
    base_promo = """🦂🦂🦂🦂🦂🦂🦂🦂🦂🦂🦂🦂
🔊@manhwalist_ir
🫂@manhwa_list_ir
♡ ㅤ    ❍ㅤ     ⎙ㅤ     ⌲
ˡᶦᵏᵉ  ᶜᵒᵐᵐᵉⁿᵗ    ˢᵃᵛᵉ     ˢʰᵃʳᵉ"""

    if has_custom_source:
        # اگر آیدی منبع در متن یافت شد، امضا بدون آیدی Eryuanovel در خط بعد شروع می‌شود
        template = base_promo
        if processed_html:
            final_text = f"{processed_html}\n{template}"
        else:
            final_text = template
    else:
        # اگر هیچ آیدی منبعی در متن یافت نشد، منبع پیش‌فرض اعمال می‌شود
        template = f"@Eryuanovel منبع\n{base_promo}"
        if processed_html:
            final_text = f"{processed_html}\n\n{template}"
        else:
            final_text = template

    return final_text


@router.message()
async def handle_all_messages(message: types.Message):
    if message.text and message.text.startswith("/"):
        return

    final_text = await process_text_and_add_template(message)

    try:
        if message.text:
            await message.answer(
                text=final_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        elif message.photo:
            await message.answer_photo(
                photo=message.photo[-1].file_id,
                caption=final_text,
                parse_mode=ParseMode.HTML,
            )
        elif message.video:
            await message.answer_video(
                video=message.video.file_id,
                caption=final_text,
                parse_mode=ParseMode.HTML,
            )
        elif message.document:
            await message.answer_document(
                document=message.document.file_id,
                caption=final_text,
                parse_mode=ParseMode.HTML,
            )
        elif message.animation:
            await message.answer_animation(
                animation=message.animation.file_id,
                caption=final_text,
                parse_mode=ParseMode.HTML,
            )
        elif message.audio:
            await message.answer_audio(
                audio=message.audio.file_id,
                caption=final_text,
                parse_mode=ParseMode.HTML,
            )
        elif message.voice:
            await message.answer_voice(
                voice=message.voice.file_id,
                caption=final_text,
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.answer(
                text=final_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
    except Exception as e:
        logger.error(f"Error sending processed post: {e}")
        await message.answer(
            "⚠️ خطایی در آماده‌سازی یا ارسال این پست رخ داد. لطفاً فرمت یا حجم متن را بررسی کنید."
        )


dp.include_router(router)
