import os
import re
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, Router, types
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command

# تنظیمات پیشرفته لاگ برای پیگیری وضعیت ربات و خطاهای احتمالی
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# دریافت توکن و آدرس وب‌هوک از متغیرهای محیطی Render
BOT_TOKEN = os.getenv("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

if not BOT_TOKEN:
    raise ValueError("خطا: متغیر BOT_TOKEN در تنظیمات Render ست نشده است!")

# تعریف ربات با موتور پردازش پیام aiogram
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

WEBHOOK_PATH = f"/bot/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}" if RENDER_EXTERNAL_URL else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """مدیریت چرخه حیات سرور و تنظیم اتصال وب‌هوک تلگرام"""
    if WEBHOOK_URL:
        logger.info(f"در حال تنظیم وب‌هوک روی آدرس: {WEBHOOK_URL}")
        # تنظیم وب‌هوک و پاک کردن پیام‌های در صف انتظار قبلی برای جلوگیری از تداخل
        await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    else:
        logger.warning("هشدار: متغیر RENDER_EXTERNAL_URL یافت نشد. وب‌هوک تنظیم نشد.")
    yield
    logger.info("در حال بستن سشن ارتباطی با تلگرام...")
    await bot.session.close()


# ایجاد فریم‌ورک وب FastAPI
app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    """تست سالم بودن سرور"""
    return {"status": "ok", "message": "Template Bot is running!"}


@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    """دریافت آپدیت‌ها از تلگرام و ارسال به دیسپچر ربات"""
    try:
        json_data = await request.json()
        update = types.Update.model_validate(json_data, context={"bot": bot})
        await dp.feed_update(bot, update)
    except Exception as e:
        logger.error(f"خطا در پردازش وب‌هوک دریافتی: {e}")
    return {"ok": True}


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """پاسخ به دستور استارت ربات"""
    await message.answer(
        "👋 به ربات تمپلت‌بات خوش آمدید!\n\n"
        "هر پستی (متن خالی، عکس‌دار، ویدیو، گیف، ویس و...) را برای من بفرستید تا قالب‌بندی آن "
        "(بولد، کج، لینک‌ها و...) را کاملاً حفظ کنم، جلوی آیدی‌های داخل متن کلمه «منبع» را اضافه کنم "
        "و امضای کانال شما را در انتها قرار دهم."
    )


def insert_source_next_to_usernames(html_text: str) -> str:
    """پیدا کردن آیدی‌ها در متن و قرار دادن کلمه «منبع» در کنار آن‌ها بدون خراب کردن تگ‌های HTML"""
    # لیست آیدی‌هایی که تبلیغاتی هستند و نباید کلمه منبع جلوی آن‌ها قرار بگیرد
    ignored_usernames = {"manhwalist_ir", "manhwa_list_ir", "eryuanovel"}

    # الگو برای تفکیک تگ‌های HTML از آیدی‌های ساده تلگرام
    pattern = re.compile(r"(<[^>]+>)|@([a-zA-Z0-9_]+)")

    def replace_match(match):
        if match.group(1):  # اگر تگ HTML باشد (بدون تغییر عبور بده)
            return match.group(1)
        else:  # اگر آیدی تلگرام باشد
            username = match.group(2)
            if username.lower() not in ignored_usernames:
                return f"@{username} منبع"
            return f"@{username}"

    return pattern.sub(replace_match, html_text)


async def process_text_and_add_template(message: types.Message) -> str:
    """دریافت متن پیام، پردازش آیدی‌ها و الحاق امضا در انتها"""
    original_html = ""

    if message.text:
        original_html = message.html_text
    elif message.caption:
        original_html = message.html_text

    # قرار دادن کلمه «منبع» در کنار آیدی‌های متن اصلی
    processed_html = (
        insert_source_next_to_usernames(original_html) if original_html else ""
    )

    # امضای نهایی و قالب ثابت شما
    template = """@Eryuanovel منبع 
🦂🦂🦂🦂🦂🦂🦂🦂🦂🦂🦂🦂
🔊@manhwalist_ir
🫂@manhwa_list_ir
♡ ㅤ    ❍ㅤ     ⎙ㅤ     ⌲
ˡᶦᵏᵉ  ᶜᵒᵐᵐᵉⁿᵗ    ˢᵃᵛᵉ     ˢʰᵃʳᵉ"""

    if processed_html:
        final_text = f"{processed_html}\n\n{template}"
    else:
        final_text = template

    return final_text


@router.message()
async def handle_all_messages(message: types.Message):
    """دریافت انواع پیام‌ها و رسانه‌ها و ارسال نسخه اصلاح‌شده به کاربر"""
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
            # ارسال متن برای سایر موارد ناشناخته
            await message.answer(
                text=final_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
    except Exception as e:
        logger.error(f"خطا در ارسال پیام اصلاح‌شده: {e}")
        await message.answer(
            "⚠️ متأسفانه خطایی در پردازش یا ارسال این پست رخ داد. حجم یا تعداد کلمات پیام را بررسی کنید."
        )


# ثبت مسیرهای پردازشی ربات در دیسپچر اصلی
dp.include_router(router)
