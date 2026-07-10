import os
import re
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, Router, types
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command

# تنظیمات لاگ سرور
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# دریافت توکن و آدرس سرور از Render
BOT_TOKEN = os.getenv("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

if not BOT_TOKEN:
    raise ValueError("خطا: متغیر BOT_TOKEN ست نشده است!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

WEBHOOK_PATH = f"/bot/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}" if RENDER_EXTERNAL_URL else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    if WEBHOOK_URL:
        logger.info(f"Setting webhook to: {WEBHOOK_URL}")
        await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    else:
        logger.warning("RENDER_EXTERNAL_URL یافت نشد.")
    yield
    logger.info("Closing bot session...")
    await bot.session.close()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "ok", "message": "Template Bot is running!"}


@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    try:
        json_data = await request.json()
        update = types.Update.model_validate(json_data, context={"bot": bot})
        await dp.feed_update(bot, update)
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
    return {"ok": True}


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 به ربات تمپلت‌بات خوش آمدید!\n\n"
        "من فرمت پست‌های شما را حفظ می‌کنم. جلوی آیدی‌های منبع داخل متن کلمه «منبع» را اضافه کرده "
        "و امضای کانال را در انتهای آن قرار می‌دهم."
    )


def insert_source_next_to_usernames(html_text: str) -> str:
    """پیدا کردن آیدی‌ها و نوشتن کلمه منبع جلوی آن‌ها (بدون تکرار و بدون خراب کردن تگ‌های HTML)"""
    # لیست آیدی‌هایی که نباید کلمه منبع جلوی آن‌ها قرار بگیرد
    ignored_usernames = {"manhwalist_ir", "manhwa_list_ir"}

    # رگکس هوشمند برای تطبیق تگ‌های HTML یا آیدی‌هایی که ممکن است از قبل کلمه منبع جلویشان باشد
    pattern = re.compile(r"(<[^>]+>)|@([a-zA-Z0-9_]+)(?:\s*منبع)?")

    def replace_match(match):
        if match.group(1):  # تگ HTML است، بدون تغییر عبور کند
            return match.group(1)
        else:  # آیدی تلگرام است
            username = match.group(2)
            if username.lower() not in ignored_usernames:
                return f"@{username} منبع"
            return f"@{username}"

    return pattern.sub(replace_match, html_text)


async def process_text_and_add_template(message: types.Message) -> str:
    original_html = ""

    if message.text:
        original_html = message.html_text
    elif message.caption:
        original_html = message.html_text

    # پردازش آیدی‌های داخل متن
    processed_html = (
        insert_source_next_to_usernames(original_html) if original_html else ""
    )

    # امضای نهایی و اصلی کانال (بدون هیچ آیدی متفرقه یا اضافی)
    template = """🦂🦂🦂🦂🦂🦂🦂🦂🦂🦂🦂🦂
🔊@manhwalist_ir
🫂@manhwa_list_ir
♡ ㅤ    ❍ㅤ     ⎙ㅤ     ⌲
ˡᶦᵏᵉ  ᶜᵒᵐᵐᵉⁿᵗ    ˢᵃᵛᵉ     ˢʰᵃʳᵉ"""

    if processed_html:
        final_text = f"{processed_html}\n{template}"
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
        logger.error(f"Error sending message: {e}")
        await message.answer(
            "⚠️ خطایی رخ داد. فرمت یا حجم متن را بررسی کنید."
        )


dp.include_router(router)
