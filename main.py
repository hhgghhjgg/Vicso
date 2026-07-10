import os
import re
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, Router, types
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command

# تنظیمات لاگ برای خطایابی بهتر
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# خواندن متغیرهای محیطی
BOT_TOKEN = os.getenv("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

if not BOT_TOKEN:
    raise ValueError("متغیر BOT_TOKEN تنظیم نشده است!")

# تعریف ربات و دیسپچر
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

WEBHOOK_PATH = f"/bot/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}" if RENDER_EXTERNAL_URL else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # تنظیم وب‌هوک هنگام شروع برنامه روی سرور
    if WEBHOOK_URL:
        logger.info(f"Setting webhook to: {WEBHOOK_URL}")
        await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    else:
        logger.warning("RENDER_EXTERNAL_URL یافت نشد. وب‌هوک تنظیم نشد.")
    yield
    # بستن سشن ربات هنگام خاموش شدن سرور
    logger.info("Closing bot session...")
    await bot.session.close()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "running"}


@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    try:
        json_data = await request.json()
        update = types.Update.model_validate(json_data, context={"bot": bot})
        await dp.feed_update(bot, update)
    except Exception as e:
        logger.error(f"Error processing update: {e}")
    return {"ok": True}


# هندلر دستور /start
@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "سلام به ربات تمپلت‌بات خوش آمدید!\n\n"
        "هر پستی (متن خالی، عکس‌دار، ویدیو، گیف و...) را برای من بفرستید تا قالب‌بندی متن شما "
        "(بولد، کج، لینک‌ها و...) را حفظ کرده و امضای کانال شما را به انتهای آن اضافه کنم."
    )


# تابع کمکی برای پردازش متن و اضافه کردن قالب نهایی
async def process_text_and_add_template(message: types.Message) -> str:
    raw_text = ""
    original_html = ""

    # بررسی وجود متن یا کپشن
    if message.text:
        raw_text = message.text
        original_html = message.html_text
    elif message.caption:
        raw_text = message.caption
        original_html = message.html_text

    # استخراج تمام آیدی‌های دارای @ برای پیدا کردن منبع
    # آیدی‌های تبلیغاتی ثابت شما نادیده گرفته می‌شوند تا به عنوان منبع مجدد تکرار نشوند
    ignored_usernames = {"manhwalist_ir", "manhwa_list_ir", "eryuanovel"}
    found_usernames = re.findall(r"@([a-zA-Z0-9_]+)", raw_text)

    unique_sources = []
    for username in found_usernames:
        if username.lower() not in ignored_usernames:
            unique_sources.append(f"@{username} منبع")

    # انتخاب منبع بر اساس آیدی‌های یافت شده
    if unique_sources:
        source_line = "\n".join(unique_sources)
    else:
        source_line = "@Eryuanovel منبع"

    # قالب متنی نهایی ارسالی کاربر
    template = f"""{source_line} 
🦂🦂🦂🦂🦂🦂🦂🦂🦂🦂🦂🦂
🔊@manhwalist_ir
🫂@manhwa_list_ir
♡ ㅤ    ❍ㅤ     ⎙ㅤ     ⌲
ˡᶦᵏᵉ  ᶜᵒᵐᵐᵉⁿᵗ    ˢᵃᵛᵉ     ˢʰᵃʳᵉ"""

    if original_html:
        final_text = f"{original_html}\n\n{template}"
    else:
        final_text = template

    return final_text


# هندلر پردازش تمام پیام‌ها و انواع مدیا
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
        logger.error(f"Failed to send formatted message: {e}")
        await message.answer(
            "⚠️ خطایی در پردازش یا ارسال پست رخ داد. حجم یا فرمت فایل ارسالی را بررسی کنید."
        )


# ثبت هندلرها در دیسپچر
dp.include_router(router)
