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
        "من فرمت پست‌های شما را حفظ می‌کنم. آخرین آیدی یا لینک تلگرام موجود در انتهای متن را "
        "شناسایی کرده و کلمه «منبع» را در کنار آن قرار می‌دهم. تمام لینک‌های دیگر در بالای متن دست‌نخورده باقی می‌مانند."
    )


async def process_text_and_add_template(message: types.Message) -> str:
    original_html = ""

    if message.text:
        original_html = message.html_text
    elif message.caption:
        original_html = message.html_text

    # آیدی‌های تبلیغاتی ثابت شما که نباید به عنوان منبع علامت‌گذاری شوند
    ignored_usernames = {"manhwalist_ir", "manhwa_list_ir", "eryuanovel"}
    
    has_custom_source = False
    processed_html = original_html

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

    if original_html:
        # تعریف الگوها برای انواع لینک‌ها و آیدی‌ها در کل متن
        a_tag_pattern = r'(<a\s+href="([^"]+)"[^>]*>(.*?)</a>)(?:\s*منبع)?'
        tag_pattern = r"(<[^>]+>)"
        username_pattern = r"(@([a-zA-Z0-9_]+)(?:\s*منبع)?)"
        link_pattern = r"(((?:https?://)?(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/(?:joinchat/|\+)?([a-zA-Z0-9_]{5,32}|[a-zA-Z0-9_\-\+]+))(?:\s*منبع)?)"
        
        # ترکیب الگوها برای بررسی گام به گام متن از بالا به پایین
        combined_pattern = re.compile(
            f"{a_tag_pattern}|{tag_pattern}|{username_pattern}|{link_pattern}", 
            re.IGNORECASE | re.DOTALL
        )
        
        matches = list(combined_pattern.finditer(original_html))
        
        # گشتن به دنبال "آخرین" مورد منطبق معتبر از انتهای متن به سمت بالا
        last_valid_match = None
        for m in reversed(matches):
            if m.group(1):  # هایپرلینک تگ <a>
                url = m.group(2)
                if is_valid_tg_source(url):
                    last_valid_match = m
                    break
            elif m.group(4):  # تگ HTML معمولی (نادیده گرفته شود)
                continue
            elif m.group(5):  # آیدی ساده تلگرام با @
                username = m.group(6)
                if username.lower() not in ignored_usernames:
                    last_valid_match = m
                    break
            elif m.group(7):  # لینک مستقیم متنی تلگرام
                channel_name = m.group(9)
                if channel_name.lower() not in ignored_usernames:
                    last_valid_match = m
                    break
        
        # اعمال تغییر کلمه «منبع» فقط و فقط روی آخرین مورد یافت شده در کل متن
        if last_valid_match:
            has_custom_source = True
            start = last_valid_match.start()
            end = last_valid_match.end()
            matched_str = original_html[start:end]
            
            if last_valid_match.group(1):  # هایپرلینک تگ <a>
                full_tag = last_valid_match.group(1)
                inner_text = last_valid_match.group(3)
                # اگر از قبل کلمه منبع در متن تگ یا بعد از آن بود تکرار نشود
                if "منبع" in inner_text or "منبع" in matched_str:
                    new_sub = matched_str
                else:
                    new_sub = f"{full_tag} منبع"
            elif last_valid_match.group(5):  # آیدی ساده تلگرام
                username = last_valid_match.group(6)
                new_sub = f"@{username} منبع"
            elif last_valid_match.group(7):  # لینک متنی مستقیم
                link = last_valid_match.group(8)
                new_sub = f"{link} منبع"
            else:
                new_sub = matched_str
            
            # بازسازی متن نهایی با تغییر انحصاریِ آخرین آیدی/لینک
            processed_html = original_html[:start] + new_sub + original_html[end:]

    # امضای جدید و نهایی کانال شما (طبق درخواست آخر)
    base_promo = """🦂🦂🦂🦂🦂🦂🦂🦂🦂🦂🦂🦂
🔊@manhwalist_ir
🫂@manhwa_list_ir
⋆༺ 𝟏𝟖 ─ 𝟏𝟗 ༻⋆
♡ ㅤ    ❍ㅤ     ⎙ㅤ     ⌲
ˡᶦᵏᵉ  ᶜᵒᵐᵐᵉⁿᵗ    ˢᵃᵛᵉ     ˢʰᵃʳᵉ"""

    if has_custom_source:
        template = base_promo
        if processed_html:
            final_text = f"{processed_html}\n{template}"
        else:
            final_text = template
    else:
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
        logger.error(f"Error sending message: {e}")
        await message.answer(
            "⚠️ مشکلی در پردازش یا ارسال این پیام پیش آمد. فرمت پیام یا حجم آن را بررسی کنید."
        )


dp.include_router(router)
