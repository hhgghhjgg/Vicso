import os
import re
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, Router, types
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command

# تنظیمات لاگ برای ثبت رویدادهای ربات
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# دریافت توکن ربات و آدرس وب‌هوک از متغیرهای محیطی هاست
BOT_TOKEN = os.getenv("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

if not BOT_TOKEN:
    raise ValueError("خطا: توکن ربات (BOT_TOKEN) یافت نشد!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

WEBHOOK_PATH = f"/bot/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}" if RENDER_EXTERNAL_URL else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """تنظیم فرآیند ثبت و بستن وب‌هوک تلگرام در سرور"""
    if WEBHOOK_URL:
        logger.info(f"در حال تنظیم وب‌هوک روی: {WEBHOOK_URL}")
        await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    else:
        logger.warning("RENDER_EXTERNAL_URL تعریف نشده است؛ فرآیند وب‌هوک ثبت نشد.")
    yield
    logger.info("در حال اتمام سشن ارتباطی با سرورهای تلگرام...")
    await bot.session.close()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "ok", "message": "ربات تمپلت‌بات فعال است."}


@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    """دریافت به‌روزرسانی‌های تلگرام و هدایت به دیسپچر اصلی"""
    try:
        json_data = await request.json()
        update = types.Update.model_validate(json_data, context={"bot": bot})
        await dp.feed_update(bot, update)
    except Exception as e:
        logger.error(f"خطا در پردازش وب‌هوک: {e}")
    return {"ok": True}


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 به ربات تمپلت‌بات خوش آمدید!\n\n"
        "هر پستی را برای من ارسال کنید تا فرمت آن را کاملاً حفظ کنم، کلمه «منبع» را در جای درست در "
        "کنار لینک‌ها یا آیدی‌های موجود در متن قرار دهم و امضای انتهای پست شما را اضافه کنم."
    )


async def process_text_and_add_template(message: types.Message) -> str:
    """تحلیل هوشمند متن و لینک‌ها و الحاق امضای بهینه‌شده به انتها"""
    original_html = ""

    if message.text:
        original_html = message.html_text
    elif message.caption:
        original_html = message.html_text

    # تعریف آیدی‌های تبلیغاتی که نباید به عنوان منبع علامت‌گذاری شوند
    ignored_usernames = {"manhwalist_ir", "manhwa_list_ir", "eryuanovel"}
    
    has_custom_source = False

    def is_valid_tg_source(url_or_text: str) -> bool:
        """بررسی اینکه آیا لینک وارد شده یک منبع تلگرامی و غیرتبلیغاتی است"""
        url_lower = url_or_text.lower()
        for ignored in ignored_usernames:
            if ignored in url_lower:
                return False
        if "t.me/" in url_lower or "telegram.me" in url_lower or "telegram.dog" in url_lower or "tg://" in url_lower:
            return True
        if url_or_text.startswith("@"):
            return True
        return False

    # مرحله اول: جستجو و پردازش هایپرلینک‌های مخفی HTML (تگ‌های <a>)
    def process_a_tags(html_text: str) -> str:
        nonlocal has_custom_source
        pattern = re.compile(r'(<a\s+href="([^"]+)"[^>]*>(.*?)</a>)(?:\s*منبع)?', re.IGNORECASE | re.DOTALL)
        
        def replace(match):
            nonlocal has_custom_source
            full_tag = match.group(1)
            url = match.group(2)
            inner_text = match.group(3)
            
            if is_valid_tg_source(url):
                has_custom_source = True
                # اگر کلمه منبع از قبل وجود داشت، مجدداً تکرار نشود
                if "منبع" in inner_text or "منبع" in full_tag:
                    return full_tag
                return f"{full_tag} منبع"
            return match.group(0)
        
        return pattern.sub(replace, html_text)

    processed_html = process_a_tags(original_html) if original_html else ""

    # مرحله دوم: پردازش آیدی‌های ساده (@) و لینک‌های متنی تلگرام (بدون تگ HTML)
    tag_pattern = r"(<[^>]+>)"
    username_pattern = r"(@([a-zA-Z0-9_]+)(?:\s*منبع)?)"
    link_pattern = r"(((?:https?://)?(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/(?:joinchat/|\+)?([a-zA-Z0-9_]{5,32}|[a-zA-Z0-9_\-\+]+))(?:\s*منبع)?)"
    
    combined_pattern = re.compile(f"{tag_pattern}|{username_pattern}|{link_pattern}", re.IGNORECASE)
    
    def replace_plain(match):
        nonlocal has_custom_source
        if match.group(1):  # اگر تگ HTML خام باشد، بدون تغییر عبور کند
            return match.group(1)
        
        elif match.group(2):  # آیدی تلگرام ساده مثل @username
            username = match.group(3)
            if username.lower() not in ignored_usernames:
                has_custom_source = True
                return f"@{username} منبع"
            return f"@{username}"
            
        elif match.group(4):  # لینک متنی تلگرام مثل https://t.me/username
            link_without_source = match.group(5)
            channel_name = match.group(6)
            if channel_name.lower() not in ignored_usernames:
                has_custom_source = True
                return f"{link_without_source} منبع"
            return link_without_source
        
        return match.group(0)

    if processed_html:
        processed_html = combined_pattern.sub(replace_plain, processed_html)

    # امضای نهایی کانال (عقرب‌ها و دکمه‌های ری‌اکشن شبیه‌سازی‌شده)
    base_promo = """🦂🦂🦂🦂🦂🦂🦂🦂🦂🦂🦂🦂
🔊@manhwalist_ir
🫂@manhwa_list_ir
♡ ㅤ    ❍ㅤ     ⎙ㅤ     ⌲
ˡᶦᵏᵉ  ᶜᵒᵐᵐᵉⁿᵗ    ˢᵃᵛᵉ     ˢʰᵃʳᵉ"""

    if has_custom_source:
        # اگر منبع داخل متن شناسایی شد، امضای کانال بلافاصله در خط بعد درج می‌شود
        template = base_promo
        if processed_html:
            final_text = f"{processed_html}\n{template}"
        else:
            final_text = template
    else:
        # اگر هیچ منبعی در متن یافت نشد، منبع پیش‌فرض اعمال می‌شود
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
        logger.error(f"Error sending formatted message: {e}")
        await message.answer(
            "⚠️ مشکلی در پردازش یا ارسال مجدد پیام پیش آمد. متن یا کپشن پیام را بررسی کنید."
        )


# ثبت کدهای روتر در دیسپچر اصلی
dp.include_router(router)
